from __future__ import annotations

import ast
import logging
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    cleaned_builder: str
    extracted_components: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def _get_selector(node: ast.Dict) -> Optional[str]:
    """Return the selector string if this dict looks like a PLaTon component, else None."""
    for key, val in zip(node.keys, node.values):
        if (
            isinstance(key, ast.Constant)
            and key.value == "selector"
            and isinstance(val, ast.Constant)
            and isinstance(val.value, str)
        ):
            return val.value
    return None


def _build_property_assignments(var_name: str, node: ast.Dict, indent: str) -> str:
    """Produce individual property-assignment lines for all non-selector keys.

    Each line has the form:
        <indent>var_name["key"] = <original expression as source>

    This preserves runtime expressions (subscripts, names, calls, arithmetic…)
    exactly as the LLM wrote them, without any evaluation.
    """
    lines: List[str] = []
    for key_node, val_node in zip(node.keys, node.values):
        if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
            # Non-string key — cannot safely turn into a bracket assignment; skip.
            logger.warning(
                "Skipping non-string key in component dict for '%s': %s",
                var_name,
                ast.dump(key_node),
            )
            continue
        key: str = key_node.value
        if key == "selector":
            # selector is already captured in the outer definition; skip.
            continue
        value_src: str = ast.unparse(val_node)
        lines.append(f"{indent}{var_name}[{key_node.value!r}] = {value_src}")
    return "\n".join(lines)


def _find_component_assignments(
    tree: ast.Module,
) -> List[Tuple[str, str, ast.Dict, int, int]]:
    """Return (var_name, selector, dict_node, start_line, end_line) for each component assignment."""
    results = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        selector = _get_selector(node.value)
        if selector is None:
            continue
        results.append((target.id, selector, node.value, node.lineno, node.end_lineno))
    return results


def _detect_indentation(source: str, lineno: int) -> str:
    """Return the leading whitespace of the given 1-based line number."""
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        raw = lines[lineno - 1]
        return raw[: len(raw) - len(raw.lstrip())]
    return ""


def extract_components_from_builder(builder_source: str) -> ExtractionResult:
    """Promote component dict assignments out of the builder.

    For every statement of the form:
        my_comp = {"selector": "wc-something", "prop": value, ...}

    this function:
    1. Records {"selector": "wc-something"} as the outer component definition.
    2. Replaces the original assignment in the builder with individual property
       assignments that preserve runtime expressions verbatim:
           my_comp["prop"] = value
           ...

    This is fully generic — no hardcoded property names, no evaluation of
    runtime expressions.
    """
    if not builder_source or not builder_source.strip():
        return ExtractionResult(cleaned_builder=builder_source, extracted_components={})

    try:
        tree = ast.parse(textwrap.dedent(builder_source))
    except SyntaxError as exc:
        logger.warning("Cannot parse builder for component extraction (SyntaxError): %s", exc)
        return ExtractionResult(cleaned_builder=builder_source, extracted_components={})

    assignments = _find_component_assignments(tree)
    if not assignments:
        return ExtractionResult(cleaned_builder=builder_source, extracted_components={})

    # Work on the source lines (1-based indexing).
    source_lines = builder_source.splitlines(keepends=True)

    # Process replacements from bottom to top so line numbers stay valid.
    extracted: Dict[str, Dict[str, Any]] = {}
    replacements: List[Tuple[int, int, str]] = []  # (start_line, end_line, replacement_text)

    for var_name, selector, dict_node, start_line, end_line in assignments:
        extracted[var_name] = {"selector": selector}

        indent = _detect_indentation(builder_source, start_line)
        prop_lines = _build_property_assignments(var_name, dict_node, indent)

        # prop_lines may be empty if the dict had only a selector key.
        replacement = prop_lines if prop_lines else ""

        replacements.append((start_line, end_line, replacement))
        logger.info(
            "Extracted component '%s' (selector='%s') from builder (lines %d–%d).",
            var_name,
            selector,
            start_line,
            end_line,
        )

    # Apply replacements from last to first to preserve line numbers.
    replacements.sort(key=lambda r: r[0], reverse=True)
    for start_line, end_line, replacement in replacements:
        # Convert to 0-based slice indices.
        del source_lines[start_line - 1 : end_line]
        if replacement:
            # Re-add trailing newline so the file stays well-formed.
            insert_lines = [
                (ln if ln.endswith("\n") else ln + "\n")
                for ln in replacement.splitlines()
            ]
            source_lines[start_line - 1 : start_line - 1] = insert_lines

    cleaned = "".join(source_lines).rstrip("\n")
    return ExtractionResult(
        cleaned_builder=cleaned if cleaned else "",
        extracted_components=extracted,
    )
