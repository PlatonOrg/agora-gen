from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Binary-content detection
#
# Reads the first PROBE_SIZE bytes of a file and rejects it if the ratio of
# non-text bytes exceeds BINARY_THRESHOLD. This prevents us from having a big allowlist
# ---------------------------------------------------------------------------

_PROBE_SIZE = 8_000
_BINARY_THRESHOLD = 0.30  # >30 % non-text bytes → treat as binary


def _is_binary(file_path: Path) -> bool:
    """Return True if the file appears to be binary content."""
    try:
        sample = file_path.read_bytes()[:_PROBE_SIZE]
    except OSError:
        return True

    if not sample:
        return False

    # Null bytes are a reliable binary signal on their own.
    if b"\x00" in sample:
        return True

    non_text = sum(
        1 for byte in sample
        if byte < 0x08 or (0x0E <= byte <= 0x1F and byte not in (0x1B,))
    )
    return (non_text / len(sample)) > _BINARY_THRESHOLD


# ---------------------------------------------------------------------------
# Extractor implementations
# ---------------------------------------------------------------------------

def _extract_txt(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="latin-1")


def _extract_pdf(file_path: Path) -> str:
    try:
        import pypdf
    except ImportError as exc:
        raise ImportError("pypdf is required to parse PDF files: pip install pypdf") from exc

    reader = pypdf.PdfReader(str(file_path))
    parts: list[str] = [page.extract_text() for page in reader.pages if page.extract_text()]
    return "\n".join(parts)


def _extract_docx(file_path: Path) -> str:
    try:
        import docx
    except ImportError as exc:
        raise ImportError(
            "python-docx is required to parse DOCX files: pip install python-docx"
        ) from exc

    document = docx.Document(str(file_path))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def _extract_xlsx(file_path: Path) -> str:
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError(
            "openpyxl is required to parse XLSX files: pip install openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    rows: list[str] = []
    for sheet in wb.worksheets:
        rows.append(f"[Sheet: {sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                rows.append("\t".join(cells))
    wb.close()
    return "\n".join(rows)


def _extract_csv(file_path: Path) -> str:
    try:
        raw = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = file_path.read_text(encoding="latin-1")

    reader = csv.reader(io.StringIO(raw))
    return "\n".join("\t".join(row) for row in reader if any(cell.strip() for cell in row))


def _extract_html(file_path: Path) -> str:
    try:
        raw = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = file_path.read_text(encoding="latin-1")

    text = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Dedicated-parser registry
#
# Only formats that require a parser beyond plain-text reading belong here.
# Every other extension is handled generically by the binary probe below.
# To add a new dedicated format, add exactly one line here.
# ---------------------------------------------------------------------------

_Extractor = Callable[[Path], str]

_DEDICATED_PARSERS: dict[str, _Extractor] = {
    ".pdf":  _extract_pdf,
    ".docx": _extract_docx,
    ".xlsx": _extract_xlsx,
    ".csv":  _extract_csv,
    ".html": _extract_html,
    ".htm":  _extract_html,
}

# Extensions that are known to be binary regardless of content
# (e.g. image, audio, video, compiled artefacts).  Files with these
# extensions are rejected early without even reading their content.
_KNOWN_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav", ".flac", ".ogg",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o",
    ".pyc", ".class", ".jar", ".wasm",
    ".db", ".sqlite", ".sqlite3",
    ".psd", ".ai", ".sketch",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def supported_extensions() -> frozenset[str]:
    """Return extensions that have a dedicated parser.

    An empty frozenset is NOT returned here — callers that previously used
    this to build an allowlist should note that any extension NOT in the
    known-binary list is now accepted generically if its content is plain
    text.  Use ``is_extension_accepted`` for per-file decisions.
    """
    return frozenset(_DEDICATED_PARSERS)


def is_extension_accepted(extension: str) -> bool:
    """Return whether files with this extension may be submitted.

    Dedicated-parser formats and all non-binary extensions are accepted.
    Known binary-only extensions (images, archives, compiled artefacts) are
    rejected without reading the file.
    """
    return extension.lower() not in _KNOWN_BINARY_EXTENSIONS


def extract_text(file_path: Path, filename: str) -> str:
    """Extract plain text from *file_path*.

    Raises:
        ValueError: If the file has a known-binary extension or its content
            fails the binary-probe check.
    """
    suffix = Path(filename).suffix.lower()

    if not is_extension_accepted(suffix):
        raise ValueError(
            f"File type '{suffix}' is a known binary format and cannot be extracted as text."
        )

    dedicated = _DEDICATED_PARSERS.get(suffix)
    if dedicated is not None:
        return dedicated(file_path)

    # Generic path: accept any file whose content is plain text.
    if _is_binary(file_path):
        raise ValueError(
            f"File '{filename}' appears to contain binary content and cannot be extracted as text."
        )

    return _extract_txt(file_path)
