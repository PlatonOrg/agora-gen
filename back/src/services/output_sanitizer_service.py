from __future__ import annotations

import io
import logging
import re
import tokenize
from typing import Optional

from src.services.models.api import GeneratedExercise
from src.services.builder_component_extractor import extract_components_from_builder
from src.services.grader_feedback_fixer import fix_feedback_message_property

logger = logging.getLogger(__name__)

_TEXT_FIELDS = ("statement", "form", "solution")
_CODE_FIELDS = ("builder", "grader")

_BARE_ESCAPE_RE = re.compile(r'\\n|\\\"')


def _string_literal_ranges(source: str) -> list[tuple[int, int]]:
    """Return a list of (start, end) byte-offset pairs covering every string
    token in *source*.  Offsets are into the UTF-8 encoded bytes of the
    source so they align with what the tokenizer reports.

    Falls back to an empty list on any tokenization error so callers remain
    safe even on partially broken input.
    """
    try:
        encoded = source.encode("utf-8")
        ranges: list[tuple[int, int]] = []
        lines = source.splitlines(keepends=True)
        # Build a mapping: (line_no 1-based, col 0-based) → byte offset
        line_byte_offsets: list[int] = []
        offset = 0
        for line in lines:
            line_byte_offsets.append(offset)
            offset += len(line.encode("utf-8"))

        def pos_to_byte(line_no: int, col: int) -> int:
            return line_byte_offsets[line_no - 1] + len(
                lines[line_no - 1][:col].encode("utf-8")
            )

        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok_type, tok_str, tok_start, tok_end, _ in tokens:
            if tok_type == tokenize.STRING:
                start_byte = pos_to_byte(*tok_start)
                end_byte = pos_to_byte(*tok_end)
                ranges.append((start_byte, end_byte))
        return ranges
    except Exception:
        return []


def _unescape_outside_strings(source: str) -> str:
    """Replace bare ``\\n`` and ``\\"`` escape sequences that appear outside
    of string literals.  Sequences inside string literals are preserved
    verbatim because they are intentional (e.g. ``"\\n".join(...)``).
    """
    encoded = source.encode("utf-8")
    string_ranges = _string_literal_ranges(source)

    def _in_string(pos: int) -> bool:
        for start, end in string_ranges:
            if start <= pos < end:
                return True
        return False

    result = bytearray()
    i = 0
    while i < len(encoded):
        # Look for the two-byte sequence backslash + n, or backslash + "
        if encoded[i] == ord("\\") and i + 1 < len(encoded):
            next_byte = encoded[i + 1]
            if next_byte in (ord("n"), ord('"')):
                if not _in_string(i):
                    replacement = b"\n" if next_byte == ord("n") else b'"'
                    result.extend(replacement)
                    i += 2
                    continue
        result.append(encoded[i])
        i += 1
    return result.decode("utf-8")


def _unescape_text(value: str) -> str:
    """Unescape ``\\n`` and ``\\"`` in plain text (non-code) fields.

    For text fields (statement, form, solution) there are no string literals
    to protect, so a simple replacement is correct.
    """
    return value.replace("\\n", "\n").replace('\\"', '"')


def _try_compile_python(source: str, field_name: str) -> Optional[SyntaxError]:
    try:
        compile(source, f"<{field_name}>", "exec")
        return None
    except SyntaxError as exc:
        return exc


def _needs_unescape(source: str) -> bool:
    return "\\n" in source or '\\"' in source


def _fix_code_field(value: str, field_name: str) -> str:
    if not value:
        return value

    syntax_error = _try_compile_python(value, field_name)
    if syntax_error is None:
        if _needs_unescape(value):
            logger.warning(
                "Field '%s' compiled successfully but contains escape artifacts — unescaping.",
                field_name,
            )
            unescaped = _unescape_outside_strings(value)
            retry_error = _try_compile_python(unescaped, field_name)
            if retry_error is not None:
                logger.error(
                    "Field '%s' failed to compile after unescaping (unexpected): %s — keeping original.",
                    field_name,
                    retry_error,
                )
                return value
            return unescaped
        return value

    logger.warning(
        "Field '%s' has a syntax error: %s — attempting to fix escape artifacts.",
        field_name,
        syntax_error,
    )

    if not _needs_unescape(value):
        logger.error(
            "Field '%s' has a syntax error but no escape artifacts found — cannot auto-fix.",
            field_name,
        )
        return value

    unescaped = _unescape_outside_strings(value)
    retry_error = _try_compile_python(unescaped, field_name)
    if retry_error is not None:
        logger.error(
            "Field '%s' still has a syntax error after unescaping: %s — keeping original.",
            field_name,
            retry_error,
        )
        return value

    logger.info("Field '%s' fixed successfully after unescaping.", field_name)
    return unescaped


def _fix_text_field(value: str, field_name: str) -> str:
    if not value or not _needs_unescape(value):
        return value
    logger.info("Field '%s' contains escape artifacts — unescaping.", field_name)
    return _unescape_text(value)


_MAX_TOPICS = 8
_MAX_LEVELS = 3
_MAX_HINTS = 5
_MAX_THEORIES = 5


def _sanitize_metadata_arrays(exercise: GeneratedExercise) -> None:
    if exercise.topics is not None:
        seen: dict[str, None] = {}
        for t in exercise.topics:
            if isinstance(t, str) and t.strip():
                seen[t.strip()] = None
        exercise.topics = list(seen.keys())[:_MAX_TOPICS]

    if exercise.levels is not None:
        seen_levels: dict[str, None] = {}
        for lv in exercise.levels:
            if isinstance(lv, str) and lv.strip():
                seen_levels[lv.strip()] = None
        exercise.levels = list(seen_levels.keys())[:_MAX_LEVELS]

    if exercise.hint is not None and len(exercise.hint) > _MAX_HINTS:
        exercise.hint = exercise.hint[:_MAX_HINTS]

    if exercise.theories is not None and len(exercise.theories) > _MAX_THEORIES:
        exercise.theories = exercise.theories[:_MAX_THEORIES]


def sanitize_generated_exercise(exercise: GeneratedExercise) -> GeneratedExercise:
    _sanitize_metadata_arrays(exercise)
    is_python = exercise.sandbox == "python"

    for field_name in _CODE_FIELDS:
        raw = getattr(exercise, field_name, None)
        if not isinstance(raw, str):
            continue
        if is_python:
            fixed = _fix_code_field(raw, field_name)
        else:
            fixed = _fix_text_field(raw, field_name)
        if fixed is not raw:
            setattr(exercise, field_name, fixed)

    for field_name in _TEXT_FIELDS:
        raw = getattr(exercise, field_name, None)
        if not isinstance(raw, str):
            continue
        fixed = _fix_text_field(raw, field_name)
        if fixed is not raw:
            setattr(exercise, field_name, fixed)

    if is_python and isinstance(exercise.grader, str) and exercise.grader.strip():
        fixed_grader = fix_feedback_message_property(exercise.grader)
        if fixed_grader is not exercise.grader:
            exercise.grader = fixed_grader

    if is_python and isinstance(exercise.builder, str) and exercise.builder.strip():
        result = extract_components_from_builder(exercise.builder)
        if result.extracted_components:
            exercise.builder = result.cleaned_builder
            for comp_name, comp_value in result.extracted_components.items():
                exercise.extra_fields[comp_name] = comp_value
            logger.info(
                "Extracted %d component(s) from builder into extra_fields: %s",
                len(result.extracted_components),
                list(result.extracted_components.keys()),
            )

    return exercise

