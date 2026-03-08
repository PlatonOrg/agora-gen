"""
Embedding model downloader.

Ensures the HuggingFace sentence-embedding model required by the RAG and
Platon-docs pipelines is present on disk before the application attempts to
load it.

If the model directory already contains the expected weight files the function
returns immediately.  Otherwise it downloads the model from the HuggingFace
Hub into the path declared by ``EMBED_MODEL_PATH`` in ``path_constants``.

This module is called at server startup via ``asset_setup_service``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.core.config_app import settings
from src.core.path_constants import EMBED_MODEL_PATH

logger = logging.getLogger(__name__)

_REQUIRED_SENTINEL_FILES = {"config.json", "tokenizer_config.json"}
_WEIGHT_EXTENSIONS = {".bin", ".safetensors", ".pt"}
_ONNX_IGNORE_PATTERNS = ["onnx/"]
_PROGRESS_INTERVAL_SECONDS = 5


def is_model_present(model_path: Path = EMBED_MODEL_PATH) -> bool:
    """
    Return True when *model_path* contains a complete-looking checkpoint.

    A checkpoint is considered complete when:
    - The directory exists.
    - All sentinel config files are present.
    - At least one weight file (.bin / .safetensors / .pt) is present.
    """
    if not model_path.is_dir():
        return False

    existing = {f.name for f in model_path.iterdir() if f.is_file()}

    if not _REQUIRED_SENTINEL_FILES.issubset(existing):
        return False

    return any(
        f.suffix in _WEIGHT_EXTENSIONS
        for f in model_path.iterdir()
        if f.is_file()
    )


def _format_bytes(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes //= 1024
    return f"{num_bytes:.1f} TB"


def _download_file_with_progress(
    url: str,
    dest: Path,
    label: str,
    headers: dict,
) -> int:
    """
    Stream *url* to *dest*, printing a progress line every
    ``_PROGRESS_INTERVAL_SECONDS`` seconds.

    Returns the number of bytes written.
    """
    import urllib.request

    request = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(request) as response:
        total_raw = response.headers.get("Content-Length")
        total = int(total_raw) if total_raw else None

        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB
        last_print = time.monotonic()
        start = time.monotonic()

        with dest.open("wb") as fh:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)

                now = time.monotonic()
                if now - last_print >= _PROGRESS_INTERVAL_SECONDS:
                    elapsed = now - start
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    if total:
                        pct = downloaded / total * 100
                        eta = (total - downloaded) / speed if speed > 0 else 0
                        print(
                            f"  {label}  {_format_bytes(downloaded)} / {_format_bytes(total)}"
                            f"  ({pct:.1f}%)  {_format_bytes(int(speed))}/s"
                            f"  ETA {eta:.0f}s",
                            flush=True,
                        )
                    else:
                        print(
                            f"  {label}  {_format_bytes(downloaded)}"
                            f"  {_format_bytes(int(speed))}/s",
                            flush=True,
                        )
                    last_print = now

    return downloaded


def _resolve_download_url(repo_id: str, filename: str, revision: str = "main") -> str:
    return f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"


def download_embedding_model(
    model_path: Path = EMBED_MODEL_PATH,
    hf_repo_id: str | None = None,
) -> None:
    """
    Download the embedding model from the HuggingFace Hub into *model_path*.

    Each file is streamed with real-time progress printed every
    ``_PROGRESS_INTERVAL_SECONDS`` seconds, so large weight files (≥ 1 GB)
    remain fully visible in Docker logs during the transfer.

    ONNX variants are skipped to reduce download size.

    Args:
        model_path: Local destination directory for the downloaded checkpoint.
        hf_repo_id: Fully-qualified HuggingFace repo ID
                    (e.g. ``intfloat/multilingual-e5-large-instruct``).
                    Defaults to ``settings.EMBED_MODEL_HF_REPO_ID``.

    Raises:
        RuntimeError: If the download fails for any reason.
    """
    try:
        from huggingface_hub import list_repo_files
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is not installed — add it to requirements.txt"
        ) from exc

    repo_id = hf_repo_id or settings.EMBED_MODEL_HF_REPO_ID
    hf_token: str | None = getattr(settings, "HF_TOKEN", None)

    model_path.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading '%s' → %s", repo_id, model_path)
    print(f"\n[Model Download] Repository : {repo_id}", flush=True)
    print(f"[Model Download] Destination: {model_path}", flush=True)

    try:
        all_files = [
            f for f in list_repo_files(repo_id)
            if not any(f.startswith(pat) for pat in _ONNX_IGNORE_PATTERNS)
        ]
    except Exception as exc:
        raise RuntimeError(f"Failed to list files for '{repo_id}': {exc}") from exc

    total = len(all_files)
    print(f"[Model Download] {total} files to download (ONNX variants excluded)\n", flush=True)

    request_headers: dict = {}
    if hf_token:
        request_headers["Authorization"] = f"Bearer {hf_token}"

    wall_start = time.monotonic()
    failed: list[str] = []

    for idx, filename in enumerate(all_files, start=1):
        dest = model_path / filename
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[{idx:>2}/{total}] SKIP  {filename}  (already present)", flush=True)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        url = _resolve_download_url(repo_id, filename)
        label = f"[{idx:>2}/{total}] {filename}"

        print(f"[{idx:>2}/{total}] START {filename}", flush=True)
        file_start = time.monotonic()

        try:
            bytes_written = _download_file_with_progress(url, dest, label, request_headers)
            elapsed = time.monotonic() - file_start
            speed = bytes_written / elapsed if elapsed > 0 else 0
            print(
                f"[{idx:>2}/{total}] DONE  {_format_bytes(bytes_written)}"
                f"  {elapsed:.1f}s  avg {_format_bytes(int(speed))}/s  {filename}",
                flush=True,
            )
            logger.info(
                "Downloaded [%d/%d] %s (%s in %.1fs)",
                idx, total, filename, _format_bytes(bytes_written), elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - file_start
            print(f"[{idx:>2}/{total}] FAIL  {elapsed:.1f}s  {filename} — {exc}", flush=True)
            logger.error("Failed to download %s: %s", filename, exc)
            if dest.exists():
                dest.unlink(missing_ok=True)
            failed.append(filename)

    wall_elapsed = time.monotonic() - wall_start
    succeeded = total - len(failed)

    print(
        f"\n[Model Download] Complete — {succeeded}/{total} files"
        f"  total time {wall_elapsed:.1f}s",
        flush=True,
    )

    if failed:
        raise RuntimeError(
            f"Embedding model download incomplete — {len(failed)} file(s) failed: "
            + ", ".join(failed)
        )

    if not is_model_present(model_path):
        raise RuntimeError(
            f"Embedding model download appeared to succeed but required sentinel "
            f"files are missing from {model_path}."
        )

    logger.info("Embedding model '%s' ready at %s.", repo_id, model_path)
    print(f"[Model Download] Model ready at {model_path}\n", flush=True)
