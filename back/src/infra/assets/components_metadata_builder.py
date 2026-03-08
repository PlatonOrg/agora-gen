"""
Component metadata builder.

Parses all .mdx component pages from the local Platon documentation corpus
and produces the components/metadata.json file.  The parser extracts:

  - name        : from the frontmatter ``title`` field
  - tag         : the first backtick-wrapped identifier after the H1 title
  - category    : derived from the parent directory name (forms -> Formulaire, widgets -> Widget)
  - description : from the frontmatter ``description`` field
  - documentation: the text of the ## Documentation section
  - properties  : the JSON schema object extracted from the ## API section
  - doc_path    : relative path to the .mdx file for full-context injection

This module is intentionally free of runtime dependencies beyond the stdlib.
It is called at startup by asset_setup_service.py only when a rebuild is needed.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.path_constants import COMPONENT_DOCS_DIR, COMPONENT_METADATA_PATH

logger = logging.getLogger(__name__)

_CATEGORY_MAP: Dict[str, str] = {
    "forms": "Formulaire",
    "widgets": "Widget",
}


# ---------------------------------------------------------------------------
# MDX parsing helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_FRONTMATTER_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)
_TAG_RE = re.compile(r"^`(wc-[a-z0-9-]+)`", re.MULTILINE)
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_JSON_SCHEMA_IN_COMPONENT_PROPERTIES = re.compile(
    r"<ComponentProperties\s+schema=\{([\s\S]+?)\}\s*/?>",
    re.MULTILINE,
)
_JSON_BLOCK_RE = re.compile(r"```json\s*\n([\s\S]*?)```", re.MULTILINE)


def _parse_frontmatter(text: str) -> Dict[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    block = match.group(1)
    result: Dict[str, str] = {}
    for m in _FRONTMATTER_FIELD_RE.finditer(block):
        key, value = m.group(1), m.group(2).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        result[key] = value
    return result


def _extract_tag(text: str) -> Optional[str]:
    match = _TAG_RE.search(text)
    return match.group(1) if match else None


def _extract_section_text(text: str, section_title: str) -> str:
    """Return the text content of a ## section, stopping at the next ## heading."""
    pattern = re.compile(
        r"^##\s+" + re.escape(section_title) + r"\s*\n([\s\S]*?)(?=\n##\s|\Z)",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    raw = match.group(1).strip()
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"\{[^}]+\}", "", raw)
    return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _extract_schema(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the JSON schema from the ## API section.

    Tries two strategies in order:
    1. Inline JSX prop: <ComponentProperties schema={{ … }} />
    2. Fenced JSON block inside a Tab inside the ## API section.
    """
    api_pattern = re.compile(
        r"^##\s+API\s*\n([\s\S]*?)(?=\n##\s|\Z)",
        re.MULTILINE | re.IGNORECASE,
    )
    api_match = api_pattern.search(text)
    if not api_match:
        return None

    api_block = api_match.group(1)

    jsx_match = _JSON_SCHEMA_IN_COMPONENT_PROPERTIES.search(api_block)
    if jsx_match:
        raw_js = jsx_match.group(1).strip()
        try:
            return json.loads(raw_js)
        except json.JSONDecodeError:
            pass

    json_blocks = _JSON_BLOCK_RE.findall(api_block)
    for block in json_blocks:
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict) and "properties" in parsed:
                return parsed
        except json.JSONDecodeError:
            continue

    return None


def _extract_properties(schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not schema:
        return {}
    return schema.get("properties", {})


# ---------------------------------------------------------------------------
# Per-file builder
# ---------------------------------------------------------------------------

def _build_entry(mdx_path: Path, category_dir: str) -> Optional[Dict[str, Any]]:
    try:
        text = mdx_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", mdx_path, exc)
        return None

    frontmatter = _parse_frontmatter(text)
    name = frontmatter.get("title", "").strip()
    description = frontmatter.get("description", "").strip()

    if not name or not description:
        logger.debug("Skipping %s: missing title or description in frontmatter", mdx_path.name)
        return None

    tag = _extract_tag(text)
    if not tag:
        logger.debug("Skipping %s: no wc-* tag found", mdx_path.name)
        return None

    category = _CATEGORY_MAP.get(category_dir, "Widget")
    documentation = _extract_section_text(text, "Documentation")
    schema = _extract_schema(text)
    properties = _extract_properties(schema)

    doc_path = f"components/{category_dir}/{mdx_path.name}"

    return {
        "name": name,
        "tag": tag,
        "category": category,
        "description": description,
        "documentation": documentation,
        "properties": properties,
        "doc_path": doc_path,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_components_metadata() -> List[Dict[str, Any]]:
    """
    Parse all component .mdx files and return the metadata list.

    The result is sorted: Formulaire entries first, then Widget, then alphabetically
    by tag within each category.
    """
    entries: List[Dict[str, Any]] = []

    for category_dir in ("forms", "widgets"):
        dir_path = COMPONENT_DOCS_DIR / category_dir
        if not dir_path.exists():
            logger.warning("Component docs directory not found: %s", dir_path)
            continue
        for mdx_file in sorted(dir_path.glob("*.mdx")):
            entry = _build_entry(mdx_file, category_dir)
            if entry:
                entries.append(entry)

    entries.sort(key=lambda e: (0 if e["category"] == "Formulaire" else 1, e["tag"]))
    return entries


def write_components_metadata(entries: List[Dict[str, Any]]) -> None:
    """Serialise *entries* to the canonical metadata.json path."""
    COMPONENT_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPONENT_METADATA_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "Wrote %d component metadata entries to %s", len(entries), COMPONENT_METADATA_PATH
    )


def rebuild_components_metadata() -> List[Dict[str, Any]]:
    """Build and persist the metadata.json in a single call."""
    entries = build_components_metadata()
    write_components_metadata(entries)
    return entries


def is_metadata_present() -> bool:
    """Return True when metadata.json exists and contains at least one entry."""
    if not COMPONENT_METADATA_PATH.exists():
        return False
    try:
        data = json.loads(COMPONENT_METADATA_PATH.read_text(encoding="utf-8"))
        return isinstance(data, list) and len(data) > 0
    except (json.JSONDecodeError, OSError):
        return False

