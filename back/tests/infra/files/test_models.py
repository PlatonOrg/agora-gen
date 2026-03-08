"""
Tests for src.infra.files.models.

Covers:
- FileSummaryResult dataclass: field storage, no defaults
"""
from __future__ import annotations

from src.infra.files.models import FileSummaryResult


class TestFileSummaryResult:
    def test_stores_all_fields(self):
        result = FileSummaryResult(
            file_id="f1",
            filename="doc.pdf",
            extracted_text="Hello world",
            summary="A document.",
        )
        assert result.file_id == "f1"
        assert result.filename == "doc.pdf"
        assert result.extracted_text == "Hello world"
        assert result.summary == "A document."

    def test_is_dataclass(self):
        import dataclasses
        assert dataclasses.is_dataclass(FileSummaryResult)

    def test_two_equal_instances(self):
        a = FileSummaryResult("f1", "f.txt", "text", "summary")
        b = FileSummaryResult("f1", "f.txt", "text", "summary")
        assert a == b

    def test_two_different_instances(self):
        a = FileSummaryResult("f1", "f.txt", "text", "summary A")
        b = FileSummaryResult("f1", "f.txt", "text", "summary B")
        assert a != b

