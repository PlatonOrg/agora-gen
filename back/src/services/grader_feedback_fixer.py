from __future__ import annotations

import ast
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

_WRONG_KEY = "message"
_RIGHT_KEY = "content"


def _find_feedback_message_locations(tree: ast.AST) -> List[Tuple[int, int, int, int]]:
    locations: List[Tuple[int, int, int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        value_node = node.value
        if not isinstance(value_node, ast.Name) or value_node.id != "feedback":
            continue
        slice_node = node.slice
        if not isinstance(slice_node, ast.Constant) or slice_node.value != _WRONG_KEY:
            continue
        locations.append((
            slice_node.lineno,
            slice_node.col_offset,
            slice_node.end_lineno,
            slice_node.end_col_offset,
        ))
    return locations


def _apply_replacements(source: str, locations: List[Tuple[int, int, int, int]]) -> str:
    lines = source.splitlines(keepends=True)

    for lineno, col_offset, end_lineno, end_col_offset in reversed(locations):
        if lineno != end_lineno:
            logger.warning(
                "Skipping multi-line feedback['message'] slice at line %d — unexpected shape.",
                lineno,
            )
            continue
        line_idx = lineno - 1
        line = lines[line_idx]
        original_slice = line[col_offset:end_col_offset]
        quote_char = original_slice[0] if original_slice and original_slice[0] in ('"', "'") else "'"
        replacement = f"{quote_char}{_RIGHT_KEY}{quote_char}"
        lines[line_idx] = line[:col_offset] + replacement + line[end_col_offset:]
        logger.info(
            "Replaced feedback['message'] → feedback['content'] at line %d, col %d.",
            lineno,
            col_offset,
        )

    return "".join(lines)


def fix_feedback_message_property(source: str) -> str:
    if not source or not source.strip():
        return source
    if _WRONG_KEY not in source:
        return source

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning(
            "Cannot parse grader for feedback.message fix (SyntaxError): %s — skipping.",
            exc,
        )
        return source

    locations = _find_feedback_message_locations(tree)
    if not locations:
        return source

    logger.warning(
        "Found %d occurrence(s) of feedback['message'] in grader — replacing with feedback['content'].",
        len(locations),
    )
    return _apply_replacements(source, locations)

