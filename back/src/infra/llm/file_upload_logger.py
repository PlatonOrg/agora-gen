from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.core.path_constants import UPLOAD_LOG_PATH

_upload_log_path = UPLOAD_LOG_PATH
_logger = logging.getLogger(__name__)


def _append(record: dict) -> None:
    try:
        _upload_log_path.parent.mkdir(parents=True, exist_ok=True)
        with _upload_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        _logger.warning("Could not write to file upload log: %s", exc)


def log_file_uploaded(original_name: str, file_id: str) -> None:
    record = {
        "event": "uploaded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original_name": original_name,
        "file_id": file_id,
    }
    _append(record)
    _logger.info("FILE_UPLOAD: name=%s id=%s", original_name, file_id)


def log_file_deleted(original_name: str, file_id: str) -> None:
    record = {
        "event": "deleted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original_name": original_name,
        "file_id": file_id,
    }
    _append(record)
    _logger.info("FILE_DELETE: name=%s id=%s", original_name, file_id)


def log_temp_file_deleted(tmp_path: Path) -> None:
    record = {
        "event": "temp_deleted",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tmp_path": str(tmp_path),
    }
    _append(record)
    _logger.info("TEMP_FILE_DELETE: path=%s", tmp_path)

