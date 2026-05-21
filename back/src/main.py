import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# --- Internal Imports ---
from src.core.config_app import settings
from src.core.logging_config import setup_root_logging
from src.api.v1.api import api_router
from src.services.rag.retrieval_service import initialize_rag_service, initialize_bm25_index
from src.services.rag.platon_docs_qa_service import initialize_platon_docs_qa_service
from src.services.platon_service import platon_service
from src.infra.db.database import init_db
from src.infra.db.redis import init_redis, close_redis, get_redis
from src.infra.db.setup_service import run_startup_setup
from src.infra.log.models import LogBase
from src.infra.db.resource_sync_service import run_resource_sync
from src.infra.platon import platon_admin_auth, PlatonCache, CachedPlatonClient
from src.infra.vector import ensure_exercise_vectors_populated
from src.infra.assets import run_asset_setup

# --- Logging Configuration ---
setup_root_logging()
logger = logging.getLogger("api")

_SYNC_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours


async def _run_sync_with_auth(engine, startup: bool = False) -> None:
    """Authenticate admin then run resource sync (which includes vector sync)."""
    try:
        admin_token = await platon_admin_auth.authenticate()
    except Exception as exc:
        logger.error("Platon admin authentication failed — sync aborted: %s", exc)
        return

    redis = await get_redis()
    client = CachedPlatonClient(
        platon=platon_service,
        cache=PlatonCache(redis, ttl_seconds=settings.PLATON_CACHE_TTL_SECONDS),
    )

    if startup:
        # Step 1 — Populate the resource DB tables first (cache is written here).
        # Vectors cannot be built from an empty DB.  sync_vectors=False because
        # the vector pass below reads from the DB once it is populated.
        try:
            await run_resource_sync(engine, client, admin_token=admin_token, sync_vectors=False)
        except Exception as exc:
            logger.error("Startup resource sync failed: %s", exc, exc_info=True)

        # Step 2 — Build/update the vector table.  All Platon calls are served
        # from the Redis cache that was populated in Step 1.
        try:
            await ensure_exercise_vectors_populated(engine, client, admin_token=admin_token)
        except Exception as exc:
            logger.error("Startup vector population failed: %s", exc, exc_info=True)
    else:
        # Daily path: DB sync and vector sync for delta resources in one pass.
        try:
            await run_resource_sync(engine, client, admin_token=admin_token, sync_vectors=True)
        except Exception as exc:
            logger.error("Resource + vector sync failed: %s", exc, exc_info=True)


async def _daily_resource_sync_loop(engine) -> None:
    """Background task: resource + vector sync, once per day."""
    while True:
        await asyncio.sleep(_SYNC_INTERVAL_SECONDS)
        await _run_sync_with_auth(engine, startup=False)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Application lifecycle handler.

    Critical path (blocks yield — must complete in a few seconds):
      - Database + Redis connection
      - Log table creation
      - Core DB setup (sync_tracker, resource tables)
      - RAG service initialisation

    Background path (non-blocking — starts after yield):
      - Asset setup (Platon docs download, embedding model)
      - Resource sync + vector population
      - Daily sync loop

    This split ensures the /health endpoint responds immediately so that
    Docker healthchecks and CI/CD dependency conditions never time out.
    """
    logger.info("Starting Agora Backend server (env=%s)...", settings.AGORA_ENV)

    background_task = None
    app_engine = None

    try:
        # ------------------------------------------------------------------
        # Critical path — fast, deterministic, must not fail silently
        # ------------------------------------------------------------------
        await init_db(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )
        await init_redis(settings.REDIS_URL)
        logger.info("Database and Redis initialized.")

        from src.core.sqlalchemy import engine as app_engine
        async with app_engine.begin() as conn:
            from src.infra.db.app_settings_repo import AppSetting  # noqa: F401
            await conn.run_sync(LogBase.metadata.create_all, checkfirst=True)
        logger.info("Log tables verified / created.")

        await run_startup_setup(app_engine)

        from src.services.runtime_config_service import runtime_config
        from src.core.sqlalchemy import AsyncSessionLocal
        async with AsyncSessionLocal() as settings_session:
            await runtime_config.load_from_db(settings_session)
        logger.info("Runtime configuration loaded.")

        # ------------------------------------------------------------------
        # Background path — heavy, slow, must not block yield
        # ------------------------------------------------------------------
        _captured_engine = app_engine

        async def _background_init() -> None:
            logger.info("Background init: starting asset setup and resource sync…")
            embedding_ready = False
            try:
                embedding_ready = await run_asset_setup()
            except Exception as exc:
                logger.error("Background init: asset setup failed: %s", exc, exc_info=True)

            if embedding_ready:
                try:
                    initialize_rag_service(
                        db_host=settings.POSTGRES_HOST,
                        db_port=settings.POSTGRES_PORT,
                        db_user=settings.POSTGRES_USER,
                        db_password=settings.POSTGRES_PASSWORD,
                        db_name=settings.POSTGRES_DB,
                        table_name=settings.RAG_TABLE_NAME,
                    )
                    initialize_platon_docs_qa_service()
                    await initialize_bm25_index()
                    logger.info("RAG services initialized.")
                except Exception as exc:
                    logger.error("Background init: RAG service initialization failed: %s", exc, exc_info=True)
            else:
                logger.warning(
                    "Background init: embedding model unavailable — "
                    "RAG services will not be initialized. "
                    "Restart the container once the model is accessible."
                )

            try:
                await _run_sync_with_auth(_captured_engine, startup=True)
            except Exception as exc:
                logger.error("Background init: startup sync failed: %s", exc, exc_info=True)

            logger.info("Background init: complete. Starting daily sync loop.")
            await _daily_resource_sync_loop(_captured_engine)

        background_task = asyncio.create_task(_background_init())

    except Exception as startup_error:
        logger.error("Critical startup error: %s", startup_error, exc_info=True)

    # Server is ready — /health responds from this point forward
    yield

    logger.info("Stopping Agora Backend server...")
    if background_task is not None and not background_task.done():
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    await close_redis()
    await platon_service.close()


def create_application() -> FastAPI:
    """
    Application factory.

    Keeps app creation testable and environment-aware.
    OpenAPI/Swagger docs are disabled in production.
    """
    openapi_url: Optional[str] = (
        None if settings.is_production
        else f"{settings.API_V1_STR}/openapi.json"
    )
    docs_url: Optional[str] = None if settings.is_production else "/docs"
    redoc_url: Optional[str] = None if settings.is_production else "/redoc"

    application = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )

    # --- Middleware (order matters: last added = first executed) ---

    # CORS — must execute before routing
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=settings.cors_allowed_methods,
        allow_headers=settings.cors_allowed_headers,
    )

    # Proxy headers — outermost so client IP is set before anything else
    application.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=[settings.TRUSTED_PROXY_HOST],
    )

    # --- Routes ---
    application.include_router(api_router, prefix=settings.API_V1_STR)

    return application


app = create_application()


@app.get("/health")
def health_check():
    """Simple health endpoint used by Docker / load balancer probes."""
    return {"status": "ok", "service": settings.PROJECT_NAME}

