"""
Derived path constants.

All tuneable base paths come from ``Settings`` (backed by env vars).
This module resolves them into absolute ``Path`` objects so the rest
of the codebase never has to worry about relative-vs-absolute logic.

Rule: every filesystem path used by the application must be declared
here.  No raw path strings are permitted anywhere else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from src.core.config_app import settings as _settings

CONTAINER_ROOT = Path(__file__).resolve().parents[2]

_MODELS_DIR_RAW = "/opt/models"


def _resolve(value: str) -> Path:
    """Return *value* as an absolute path, resolving relative paths against CONTAINER_ROOT."""
    path = Path(value)
    if path.is_absolute():
        return path
    return CONTAINER_ROOT / path


def _repo_id_to_dirname(repo_id: str) -> str:
    """
    Convert a HuggingFace repo ID to a safe local directory name.

    The ``/`` separator is replaced with ``_`` so the org prefix is preserved
    and the directory name remains unambiguous on any filesystem.

    Example::

        ``intfloat/multilingual-e5-large-instruct``
        → ``intfloat_multilingual-e5-large-instruct``
    """
    return repo_id.replace("/", "_")


RESOURCES_DIR = _resolve(_settings.RESOURCES_BASE_PATH)

PROMPTS_DIR = RESOURCES_DIR / "prompts" / "system_prompts"
TESTS_DIR = RESOURCES_DIR / "prompts" / "test_prompts"

LOG_DIR = _resolve(_settings.LOG_DIR)
UPLOAD_LOG_PATH = LOG_DIR / "file_uploads.log"
DEBUG_LOG_DIR = LOG_DIR

COMPONENT_METADATA_PATH = RESOURCES_DIR / "docs" / "components" / "metadata.json"
PLATON_DOCS_DIR = RESOURCES_DIR / "docs" / "platon_docs" / "pages"
COMPONENT_DOCS_DIR = PLATON_DOCS_DIR / "components"

BACKUP_DIR = RESOURCES_DIR / "backup"

MODELS_DIR = Path(_MODELS_DIR_RAW)

EMBED_MODEL_PATH = MODELS_DIR / _repo_id_to_dirname(_settings.EMBED_MODEL_HF_REPO_ID)
RERANKER_MODEL_PATH = MODELS_DIR / _repo_id_to_dirname(_settings.RERANKER_HF_REPO_ID)

PLATON_DOCS_EMBED_MODEL = EMBED_MODEL_PATH


def resolve_path(value: Union[str, Path, None]) -> Path | None:
    """Resolve an arbitrary path string against CONTAINER_ROOT."""
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return CONTAINER_ROOT / path
