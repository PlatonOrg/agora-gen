import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from src.core.config_app import settings as _settings
from src.core import path_constants


def _resolve_log_level(level_name: str) -> int:
    """Convert a level name string ('DEBUG', 'INFO', ...) to a logging int."""
    return getattr(logging, level_name.upper(), logging.INFO)


def setup_logging(
    service_name: str,
    log_dir: Optional[Path] = None,
    max_bytes: Optional[int] = None,
    backup_count: Optional[int] = None,
    level: Optional[int] = None,
) -> logging.Logger:
    if log_dir is None:
        log_dir = path_constants.LOG_DIR
    if max_bytes is None:
        max_bytes = _settings.LOG_MAX_BYTES
    if backup_count is None:
        backup_count = _settings.LOG_BACKUP_COUNT
    if level is None:
        level = _resolve_log_level(_settings.LOG_LEVEL)

    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(service_name)
    logger.setLevel(level)

    # Disable propagation to avoid duplicate log lines when root logger is configured
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    log_file = log_dir / f"{service_name}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def setup_root_logging(
    log_dir: Optional[Path] = None,
    max_bytes: Optional[int] = None,
    backup_count: Optional[int] = None,
    level: Optional[int] = None,
) -> None:
    if log_dir is None:
        log_dir = path_constants.LOG_DIR
    if max_bytes is None:
        max_bytes = _settings.LOG_MAX_BYTES
    if backup_count is None:
        backup_count = _settings.LOG_BACKUP_COUNT
    if level is None:
        level = _resolve_log_level(_settings.LOG_LEVEL)

    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        return

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    log_file = log_dir / "app.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress chatty third-party loggers that emit one line per HTTP request.
    for noisy in ("httpx", "httpcore", "huggingface_hub.utils._http", "huggingface_hub.file_download"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

