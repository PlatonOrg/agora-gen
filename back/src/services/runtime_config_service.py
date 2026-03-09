"""
Runtime configuration service.

Manages an in-memory cache of admin-tuneable settings backed by the
``app_setting`` database table.  Only settings declared in
``SETTINGS_REGISTRY`` are exposed -- secrets and infrastructure
values are never included.

Usage from other services::

    from src.services.runtime_config_service import runtime_config, SettingKey

    temperature = runtime_config.get_float(SettingKey.TEMP_GENERATION)
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.db.app_settings_repo import AppSettingsRepository

logger = logging.getLogger(__name__)


class SettingKey(str, enum.Enum):
    """Canonical identifiers for every admin-tuneable setting.

    Using an enum eliminates magic strings, enables IDE autocomplete,
    and guarantees a compile-time error on typos.
    """

    TEMP_GENERATION = "TEMP_GENERATION"
    NUM_EXAMPLE_EXERCISES = "NUM_EXAMPLE_EXERCISES"
    RAG_LOG_TOP_K = "RAG_LOG_TOP_K"
    PLATON_DOCS_TOP_K = "PLATON_DOCS_TOP_K"
    SANDBOX_RETRY_MAX_ATTEMPTS = "SANDBOX_RETRY_MAX_ATTEMPTS"
    SANDBOX_RETRY_TIMEOUT_SECONDS = "SANDBOX_RETRY_TIMEOUT_SECONDS"
    FILE_UPLOAD_MAX_COUNT = "FILE_UPLOAD_MAX_COUNT"
    LOG_LEVEL = "LOG_LEVEL"
    TEMPLATE_SCORE_THRESHOLD = "TEMPLATE_SCORE_THRESHOLD"


@dataclass(frozen=True)
class SettingDefinition:
    """Declarative schema for one admin-tuneable setting."""

    key: SettingKey
    value_type: str          # "float", "int", "str", "bool"
    default: str             # always stored/transmitted as string
    description: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None  # for enum-style constraints


# --- Allowlist of safe, admin-tuneable settings ---
# Infrastructure, secrets, paths, and connection strings are excluded.

SETTINGS_REGISTRY: Dict[str, SettingDefinition] = {
    entry.key.value: entry for entry in [
        SettingDefinition(
            key=SettingKey.TEMP_GENERATION,
            value_type="float",
            default="0.0",
            description="Temperature de generation LLM (0.0 = deterministe, 1.0+ = creatif).",
            min_value=0.0,
            max_value=2.0,
        ),
        SettingDefinition(
            key=SettingKey.NUM_EXAMPLE_EXERCISES,
            value_type="int",
            default="10",
            description="Nombre d'exercices exemples utilises par le RAG lors de la generation.",
            min_value=0,
            max_value=50,
        ),
        SettingDefinition(
            key=SettingKey.RAG_LOG_TOP_K,
            value_type="int",
            default="10",
            description="Nombre de resultats RAG enregistres dans les journaux.",
            min_value=1,
            max_value=50,
        ),
        SettingDefinition(
            key=SettingKey.PLATON_DOCS_TOP_K,
            value_type="int",
            default="8",
            description="Nombre de chunks documentaires recuperes pour la recherche documentaire.",
            min_value=1,
            max_value=50,
        ),
        SettingDefinition(
            key=SettingKey.SANDBOX_RETRY_MAX_ATTEMPTS,
            value_type="int",
            default="3",
            description="Nombre maximum de tentatives de compilation/execution dans le sandbox.",
            min_value=1,
            max_value=10,
        ),
        SettingDefinition(
            key=SettingKey.SANDBOX_RETRY_TIMEOUT_SECONDS,
            value_type="float",
            default="120.0",
            description="Timeout global (en secondes) pour les tentatives de correction sandbox.",
            min_value=10.0,
            max_value=600.0,
        ),
        SettingDefinition(
            key=SettingKey.FILE_UPLOAD_MAX_COUNT,
            value_type="int",
            default="5",
            description="Nombre maximum de fichiers pouvant etre joints a une requete.",
            min_value=1,
            max_value=20,
        ),
        SettingDefinition(
            key=SettingKey.LOG_LEVEL,
            value_type="str",
            default="INFO",
            description="Niveau de journalisation de l'application.",
            options=["DEBUG", "INFO", "WARNING", "ERROR"],
        ),
        SettingDefinition(
            key=SettingKey.TEMPLATE_SCORE_THRESHOLD,
            value_type="float",
            default="0.85",
            description="Score minimum de similarite RAG pour selectionner un template (0.0-1.0).",
            min_value=0.0,
            max_value=1.0,
        ),
    ]
}


class RuntimeConfigService:
    """In-memory cache for admin-tuneable settings, synced to the database.

    On startup the cache is populated from the ``app_setting`` table.
    On first run (empty table), it seeds from ``SETTINGS_REGISTRY``
    defaults, with environment variable overrides where present.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # -- Bootstrap / Seed -------------------------------------------------

    async def load_from_db(self, session: AsyncSession) -> None:
        """Populate the in-memory cache from the database.

        Called once during application startup.  If the table is empty,
        seed it from ``SETTINGS_REGISTRY`` defaults (env vars override).
        """
        repo = AppSettingsRepository(session)
        rows = await repo.get_all()

        if rows:
            for row in rows:
                self._cache[row.key] = row.value
            logger.info(
                "Runtime config loaded from database: %d setting(s).",
                len(rows),
            )
        else:
            await self._seed_defaults(repo, session)

        # Ensure any new registry entries added after initial seed are present
        for key, definition in SETTINGS_REGISTRY.items():
            if key not in self._cache:
                seed_value = self._resolve_seed_value(key, definition.default)
                await repo.upsert(
                    key=key,
                    value=seed_value,
                    value_type=definition.value_type,
                    description=definition.description,
                    updated_by="system",
                )
                await session.commit()
                self._cache[key] = seed_value

        self._loaded = True

    async def _seed_defaults(
        self,
        repo: AppSettingsRepository,
        session: AsyncSession,
    ) -> None:
        """First run: write seed defaults into the database."""
        for key, definition in SETTINGS_REGISTRY.items():
            seed_value = self._resolve_seed_value(key, definition.default)
            await repo.upsert(
                key=key,
                value=seed_value,
                value_type=definition.value_type,
                description=definition.description,
                updated_by="system",
            )
            self._cache[key] = seed_value
        await session.commit()
        logger.info(
            "Seeded %d runtime setting(s) from environment/defaults.",
            len(SETTINGS_REGISTRY),
        )

    @staticmethod
    def _resolve_seed_value(key: str, fallback: str) -> str:
        """Determine the initial value for a setting on first-run seeding.

        Priority: environment variable > ``SETTINGS_REGISTRY`` default.
        """
        import os
        return os.environ.get(key, fallback)

    # -- Read API ----------------------------------------------------------

    def get_all_with_metadata(self) -> List[Dict[str, Any]]:
        """Return all settings with their metadata for the admin UI."""
        result: List[Dict[str, Any]] = []
        for key, definition in SETTINGS_REGISTRY.items():
            result.append({
                "key": key,
                "value": self._cache.get(key, definition.default),
                "value_type": definition.value_type,
                "description": definition.description,
                "default": definition.default,
                "min_value": definition.min_value,
                "max_value": definition.max_value,
                "options": definition.options,
            })
        return result

    def get(self, key: Union[SettingKey, str]) -> str:
        """Return the current value for a setting, falling back to default."""
        resolved = key.value if isinstance(key, SettingKey) else key
        definition = SETTINGS_REGISTRY.get(resolved)
        default = definition.default if definition else ""
        return self._cache.get(resolved, default)

    def get_float(self, key: Union[SettingKey, str]) -> float:
        return float(self.get(key))

    def get_int(self, key: Union[SettingKey, str]) -> int:
        return int(float(self.get(key)))

    def get_bool(self, key: Union[SettingKey, str]) -> bool:
        return self.get(key).lower() in ("true", "1", "yes")

    # -- Write API ---------------------------------------------------------

    async def update_settings(
        self,
        updates: Dict[str, str],
        session: AsyncSession,
        updated_by: Optional[str] = None,
    ) -> Dict[str, str]:
        """Validate, persist, and cache a batch of setting updates.

        Returns the final values for all updated keys.

        Raises:
            ValueError: If any key is not in the allowlist or a value
                        fails validation.
        """
        validated: Dict[str, str] = {}
        for key, raw_value in updates.items():
            definition = SETTINGS_REGISTRY.get(key)
            if definition is None:
                raise ValueError(
                    f"Setting '{key}' is not in the allowed configuration list."
                )
            validated[key] = self._validate(definition, raw_value)

        repo = AppSettingsRepository(session)
        await repo.upsert_many(validated, SETTINGS_REGISTRY, updated_by=updated_by)
        await session.commit()

        for key, value in validated.items():
            self._cache[key] = value

        self._apply_side_effects(validated)

        logger.info(
            "Admin '%s' updated runtime settings: %s",
            updated_by or "unknown",
            list(validated.keys()),
        )
        return validated

    # -- Validation --------------------------------------------------------

    @staticmethod
    def _validate(definition: SettingDefinition, raw_value: str) -> str:
        """Coerce and range-check a raw string value against its definition."""
        vtype = definition.value_type
        key_name = definition.key.value

        if vtype == "float":
            try:
                val = float(raw_value)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"'{key_name}' must be a number. Got: '{raw_value}'."
                ) from exc
            if definition.min_value is not None and val < definition.min_value:
                raise ValueError(
                    f"'{key_name}' must be >= {definition.min_value}."
                )
            if definition.max_value is not None and val > definition.max_value:
                raise ValueError(
                    f"'{key_name}' must be <= {definition.max_value}."
                )
            return str(val)

        if vtype == "int":
            try:
                val = int(float(raw_value))
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"'{key_name}' must be an integer. Got: '{raw_value}'."
                ) from exc
            if definition.min_value is not None and val < int(definition.min_value):
                raise ValueError(
                    f"'{key_name}' must be >= {int(definition.min_value)}."
                )
            if definition.max_value is not None and val > int(definition.max_value):
                raise ValueError(
                    f"'{key_name}' must be <= {int(definition.max_value)}."
                )
            return str(val)

        if vtype == "bool":
            if raw_value.lower() in ("true", "1", "yes"):
                return "true"
            if raw_value.lower() in ("false", "0", "no"):
                return "false"
            raise ValueError(
                f"'{key_name}' must be a boolean. Got: '{raw_value}'."
            )

        if vtype == "str":
            if definition.options and raw_value not in definition.options:
                raise ValueError(
                    f"'{key_name}' must be one of {definition.options}. "
                    f"Got: '{raw_value}'."
                )
            return raw_value

        return raw_value

    # -- Side Effects ------------------------------------------------------

    @staticmethod
    def _apply_side_effects(updated: Dict[str, str]) -> None:
        """Apply immediate runtime effects for specific settings."""
        if SettingKey.LOG_LEVEL.value in updated:
            import logging as _logging
            level_str = updated[SettingKey.LOG_LEVEL.value]
            level = getattr(_logging, level_str.upper(), _logging.INFO)
            _logging.getLogger().setLevel(level)
            logger.info("Root log level changed to %s.", level_str)


# -- Module-level singleton ------------------------------------------------

runtime_config = RuntimeConfigService()


















