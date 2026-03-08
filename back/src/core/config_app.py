"""
Centralized infrastructure configuration.

Contains secrets, connection strings, filesystem paths, and other
values that require a restart or redeployment to change.

Admin-tuneable operational parameters (temperature, retry limits,
etc.) are managed by ``RuntimeConfigService`` and the admin UI.
They are NOT declared here.

Services receive their configuration via DI (``di.py``) -- they
should **never** import ``settings`` directly.

Naming convention: ``SECTION_FIELD`` (e.g. ``PLATON_BASE_URL``).
"""

from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional

from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # ==================================================================
    # General
    # ==================================================================
    PROJECT_NAME: str = "Agora AI Agent"
    AGORA_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    TRUSTED_PROXY_HOST: str = "127.0.0.1"

    # Optional GitHub personal access token used during startup to download
    # Platon documentation from GitHub.  Without it, anonymous requests are
    # used (rate-limited to 60 req/h).  Set in .env for production deployments.
    GITHUB_TOKEN: Optional[str] = None

    @property
    def is_production(self) -> bool:
        """Determine if the application is running in production mode."""
        return self.AGORA_ENV == "production"

    # ==================================================================
    # CORS
    # ==================================================================
    CORS_ORIGINS: str = "http://localhost:4200,http://localhost:80,http://localhost"

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ==================================================================
    # Logging
    #
    # LOG_LEVEL is read at import time by ``logging_config.py`` before
    # the database is available.  At runtime, ``RuntimeConfigService``
    # takes over and the admin UI manages the effective level.
    # This declaration is the pre-DB bootstrap fallback only.
    # ==================================================================
    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # ==================================================================
    # Database (PostgreSQL + PGVector)
    # ==================================================================
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_DB: str = "agora_db"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    SQL_ECHO: bool = False

    @property
    def DATABASE_URL(self) -> str:
        encoded_password = quote(self.POSTGRES_PASSWORD or "", safe="")
        return (
            f"postgresql://{self.POSTGRES_USER}:{encoded_password}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ==================================================================
    # Redis (Sessions & Cache)
    # ==================================================================
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    PLATON_CACHE_TTL_SECONDS: int = 86_400

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            encoded_password = quote(self.REDIS_PASSWORD, safe="")
            return f"redis://:{encoded_password}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # ==================================================================
    # Session / Auth
    # ==================================================================
    SESSION_COOKIE_NAME: str = "agora_session_id"
    SESSION_TTL_SECONDS: int = 86400
    OAUTH_STATE_TTL_SECONDS: int = 600
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"

    # ==================================================================
    # Platon API
    # ==================================================================
    PLATON_BASE_URL: str = "https://platon.univ-eiffel.fr/api/v1"
    PLATON_PLAYER_URL: str = "https://platon.univ-eiffel.fr/player/preview"
    PLATON_LOGIN_BASE_URL: str = "https://platon.univ-eiffel.fr/login"
    PLATON_API_TOKEN: str | None = None
    PLATON_PUBLIC_KEY: str | None = None
    PLATON_CALLBACK_URL: str = "http://localhost:80/auth/callback"
    PLATON_CALLBACK_TITLE: str = "Agora AI Agent"
    PLATON_TIMEOUT_SECONDS: float = 30.0
    TEMP_PLATON_API_TOKEN: str | None = None

    # Credentials used exclusively for background synchronisation tasks
    # (resource sync, vector population).  Never used for user requests.
    PLATON_ADMIN_USERNAME: str | None = None
    PLATON_ADMIN_PASSWORD: str | None = None

    # ==================================================================
    # Paths
    # ==================================================================
    RESOURCES_BASE_PATH: str = "resources"
    LOG_DIR: str = "resources/logs"
    EMBED_MODEL_HF_REPO_ID: str = "intfloat/multilingual-e5-large-instruct"
    HF_TOKEN: Optional[str] = None

    # ==================================================================
    # Embedding / RAG
    # ==================================================================
    RAG_TABLE_NAME: str = "agora_rag_embeddings"

    PLATON_DOCS_VECTOR_TABLE: str = "platon_docs_fr_chunks"
    PLATON_DOCS_QA_ENABLED: bool = True

    # Non-tuneable generation constants
    FILE_CONTENT_MAX_TOKENS: int = 3000
    FILE_SUMMARY_MAX_TOKENS: int = 500

    # ==================================================================
    # Component selection
    #
    # Tags listed here are excluded from every component-selection step.
    # They will never be proposed to the LLM nor injected into generation
    # prompts.  Use this list to hide experimental, broken, or
    # non-pedagogically-relevant components.
    # ==================================================================
    BANNED_COMPONENTS: List[str] = [
        "wc-markdown",
        "wc-confetti",
        "wc-presenter",
    ]

    # ==================================================================
    # Component documentation mode
    #
    # Controls how much component documentation is injected into the
    # generation prompt for each selected component.
    #
    # "schema"  — inject only the JSON property schema extracted from
    #             metadata.json, plus the dedicated instructions file
    #             (e.g. wc_match_list.txt).  Cheaper and faster.
    #
    # "full"    — inject the entire raw .mdx documentation file for the
    #             component, plus the dedicated instructions file.
    #             More verbose; useful for diagnosing generation issues.
    # ==================================================================
    COMPONENT_DOC_MODE: str = "schema"

    # ==================================================================
    # Repair prompt configuration
    #
    # "true"  — inject langage.mdx (~3 570 tokens) and workflow.mdx
    #           (~1 130 tokens) into the exercise repair prompt.
    #           Useful for diagnosing complex PLE syntax errors.
    #
    # "false" — omit those docs from the repair prompt (saves ~4 700
    #           tokens per repair call). The critical PLE rules are
    #           already summarized inside exercise_repair.txt itself.
    # ==================================================================
    REPAIR_INJECT_PLE_DOCS: bool = False

    # ==================================================================
    # Template and Workspace Constants
    # ==================================================================
    TEMPLATE_SCORE_THRESHOLD: float = 0.9
    REQUIRED_FIELDS_MAX_LENGTH: int = 700
    OTHER_FIELDS_MAX_LENGTH: int = 200

    # ==================================================================
    # LLM Provider Configuration
    #
    # ``LLM_PROVIDERS_FILE`` points to a JSON file that declares *all*
    # available providers and their default models.  One entry must
    # have ``"default": true`` to designate the system-wide default.
    #
    # ``LLM_PROVIDERS`` (inline JSON string env var) is kept as a
    # backward-compatible fallback.  If the file exists it takes
    # precedence.
    #
    # Supported kinds: openai_compatible, ragustave, gemini, ollama,
    #                  openrouter, cerebras
    # ==================================================================
    LLM_PROVIDERS_FILE: str = "resources/llm_providers.json"
    LLM_PROVIDERS: Optional[List[Dict[str, Any]]] = None

    @field_validator("LLM_PROVIDERS", mode="before")
    @classmethod
    def _parse_llm_providers_json(cls, value: Any) -> Any:
        """Accept a raw JSON string from an env var and parse it."""
        if isinstance(value, str):
            try:
                return _json.loads(value)
            except _json.JSONDecodeError:
                return None
        return value

    # CORS
    # Explicit list of HTTP methods your API actually exposes
    CORS_ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

    CORS_ALLOWED_HEADERS: List[str] = [
        "Content-Type",
        "Accept",
    ]

    @property
    def cors_allowed_methods(self) -> List[str]:
        """Accessor kept for backward compatibility with main.py middleware setup."""
        return self.CORS_ALLOWED_METHODS

    @property
    def cors_allowed_headers(self) -> List[str]:
        """Accessor kept for backward compatibility with main.py middleware setup."""
        return self.CORS_ALLOWED_HEADERS

settings = Settings()

