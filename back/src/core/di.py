from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from src.core.config_app import settings
from src.infra.llm.llm import LLMProviderRegistry

logger = logging.getLogger(__name__)


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)}")


def _expand_env_vars(raw_text: str) -> str:
    """Replace ``${VAR_NAME}`` placeholders with environment variable values.

    Raises:
        ValueError: If a referenced variable is not set.
    """
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(
                f"Environment variable '{var_name}' referenced in "
                f"llm_providers.json is not set."
            )
        return value

    return _ENV_VAR_PATTERN.sub(_replace, raw_text)


def _load_providers_config() -> List[Dict[str, Any]]:
    """Load the provider configuration list.

    Resolution order:
      1. JSON file at ``settings.LLM_PROVIDERS_FILE`` (relative paths
         resolved against the container root).  ``${VAR}`` placeholders
         in the file are expanded from environment variables.
      2. Inline ``LLM_PROVIDERS`` env var (backward compatibility).

    Raises:
        RuntimeError: If neither source provides a valid configuration.
    """
    from src.core.path_constants import CONTAINER_ROOT

    file_path = Path(settings.LLM_PROVIDERS_FILE)
    if not file_path.is_absolute():
        file_path = CONTAINER_ROOT / file_path

    if file_path.is_file():
        logger.info("Loading LLM providers from file: %s", file_path)
        raw_text = file_path.read_text(encoding="utf-8")
        expanded_text = _expand_env_vars(raw_text)
        entries = json.loads(expanded_text)
        if isinstance(entries, list) and entries:
            return entries
        logger.warning("LLM providers file is empty or invalid: %s", file_path)

    if settings.LLM_PROVIDERS:
        logger.info("Loading LLM providers from LLM_PROVIDERS env var (fallback)")
        return settings.LLM_PROVIDERS

    raise RuntimeError(
        f"No LLM provider configuration found. "
        f"Expected JSON file at '{file_path}' or LLM_PROVIDERS env var."
    )


def _build_providers_from_config(
    entries: List[Dict[str, Any]],
) -> LLMProviderRegistry:
    """Construct the registry from a list of provider config dicts."""
    from src.infra.llm.providers import (
        CerebrasProvider,
        GeminiProvider,
        OllamaProvider,
        OpenAICompatibleProvider,
        OpenRouterProvider,
        RagustaveProvider,
    )

    registry = LLMProviderRegistry()

    kind_map = {
        "openai_compatible": lambda entry: OpenAICompatibleProvider(
            provider_name=entry["name"],
            base_url=entry["base_url"],
            api_key=entry.get("api_key", ""),
            timeout_seconds=float(entry.get("timeout_seconds", 300)),
        ),
        "ragustave": lambda entry: RagustaveProvider(
            base_url=entry["base_url"],
            api_key=entry.get("api_key", ""),
            timeout_seconds=float(entry.get("timeout_seconds", 300)),
        ),
        "gemini": lambda entry: GeminiProvider(
            api_key=entry["api_key"],
            timeout_seconds=float(entry.get("timeout_seconds", 300)),
        ),
        "ollama": lambda entry: OllamaProvider(
            base_url=entry["base_url"],
            timeout_seconds=float(entry.get("timeout_seconds", 300)),
        ),
        "openrouter": lambda entry: OpenRouterProvider(
            provider_name=entry["name"],
            api_key=entry["api_key"],
            timeout_seconds=float(entry.get("timeout_seconds", 300)),
        ),
        "cerebras": lambda entry: CerebrasProvider(
            provider_name=entry["name"],
            api_key=entry["api_key"],
        ),
    }

    for entry in entries:
        kind = entry.get("kind", "openai_compatible")
        name = entry["name"]

        factory = kind_map.get(kind)
        if factory is None:
            logger.warning("Unknown provider kind '%s' -- skipping entry: %s", kind, name)
            continue

        provider = factory(entry)
        is_default = entry.get("default", False) is True
        registry.register(
            provider,
            default_model=entry.get("default_model", ""),
            models=entry.get("models"),
            is_default=is_default,
        )
        logger.info(
            "Registered LLM provider '%s' (kind=%s, default=%s)",
            name, kind, is_default,
        )

    return registry


@lru_cache(maxsize=1)
def get_llm_registry() -> LLMProviderRegistry:
    """Return the application-wide ``LLMProviderRegistry`` singleton.

    Built from ``resources/llm_providers.json`` (preferred) or the
    ``LLM_PROVIDERS`` env var (fallback).

    Raises:
        RuntimeError: If no provider configuration is available.
    """
    entries = _load_providers_config()
    registry = _build_providers_from_config(entries)

    logger.info(
        "LLM registry ready -- providers: %s, default: %s",
        registry.registered_names,
        registry.default_provider_name,
    )
    return registry
