import logging
import asyncpg

logger = logging.getLogger("uvicorn")


async def init_db(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> None:
    """
    Initializes the database connection and ensures pgvector extension is available.
    Since LlamaIndex handles its own connection, this function mainly verifies connectivity.
    """
    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )

        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.close()

        logger.info("Database connection verified and pgvector extension enabled.")
    except Exception as e:
        logger.warning("Database initialization warning: %s", e)
