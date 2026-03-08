"""
Tests for src.infra.files.parsers.

Covers:
- supported_extensions: returns only dedicated-parser extensions
- is_extension_accepted: rejects known binary extensions, accepts everything else
- extract_text: dedicated parsers (csv, html), generic text probe, binary rejection
- _is_binary: null-byte detection, non-text byte ratio
- extract_text: pdf/docx/xlsx raise on missing dependency
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.infra.files.parsers import (
    extract_text,
    is_extension_accepted,
    supported_extensions,
)


# ---------------------------------------------------------------------------
# supported_extensions — only dedicated parsers
# ---------------------------------------------------------------------------

class TestSupportedExtensions:
    def test_returns_frozenset(self):
        assert isinstance(supported_extensions(), frozenset)

    def test_contains_dedicated_parser_formats(self):
        exts = supported_extensions()
        for ext in [".pdf", ".docx", ".xlsx", ".csv", ".html", ".htm"]:
            assert ext in exts

    def test_does_not_contain_plain_text_extensions(self):
        # Plain-text formats are handled generically — not in the dedicated registry.
        exts = supported_extensions()
        for ext in [".py", ".js", ".ts", ".java", ".c", ".go", ".rs", ".yaml", ".json"]:
            assert ext not in exts

    def test_all_lowercase(self):
        for ext in supported_extensions():
            assert ext == ext.lower()

    def test_all_start_with_dot(self):
        for ext in supported_extensions():
            assert ext.startswith(".")


# ---------------------------------------------------------------------------
# is_extension_accepted
# ---------------------------------------------------------------------------

class TestIsExtensionAccepted:
    @pytest.mark.parametrize("ext", [
        ".py", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".ts", ".js",
        ".sh", ".sql", ".yaml", ".yml", ".json", ".toml", ".ini", ".xml",
        ".css", ".scss", ".graphql", ".rst", ".tex", ".lua", ".r",
        ".txt", ".md", ".csv", ".html", ".pdf", ".docx", ".xlsx",
        ".somebrandnewextension",  # unknown extensions are accepted; content decides
    ])
    def test_accepts_text_and_document_extensions(self, ext: str):
        assert is_extension_accepted(ext) is True

    @pytest.mark.parametrize("ext", [
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
        ".mp3", ".mp4", ".avi", ".mov", ".wav",
        ".zip", ".tar", ".gz", ".7z", ".rar",
        ".exe", ".dll", ".so", ".bin",
        ".pyc", ".class", ".jar", ".wasm",
        ".db", ".sqlite",
        ".psd",
    ])
    def test_rejects_known_binary_extensions(self, ext: str):
        assert is_extension_accepted(ext) is False

    def test_case_insensitive(self):
        assert is_extension_accepted(".PNG") is False
        assert is_extension_accepted(".PY") is True


# ---------------------------------------------------------------------------
# extract_text — dedicated parsers
# ---------------------------------------------------------------------------

class TestExtractCsv:
    def test_parses_csv_rows(self, tmp_path):
        f = tmp_path / "file.csv"
        f.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")
        result = extract_text(f, "file.csv")
        assert "Alice" in result
        assert "Bob" in result

    def test_skips_empty_rows(self, tmp_path):
        f = tmp_path / "file.csv"
        f.write_text("a,b\n,\nc,d", encoding="utf-8")
        result = extract_text(f, "file.csv")
        lines = [line for line in result.splitlines() if line.strip()]
        assert len(lines) == 2  # header + one data row

    def test_tab_separated_output(self, tmp_path):
        f = tmp_path / "file.csv"
        f.write_text("col1,col2\nval1,val2", encoding="utf-8")
        assert "\t" in extract_text(f, "file.csv")


class TestExtractHtml:
    def test_strips_html_tags(self, tmp_path):
        f = tmp_path / "file.html"
        f.write_text("<html><body><p>Hello world</p></body></html>", encoding="utf-8")
        result = extract_text(f, "file.html")
        assert "Hello world" in result
        assert "<" not in result

    def test_normalises_whitespace(self, tmp_path):
        f = tmp_path / "file.html"
        f.write_text("<p>  Hello   world  </p>", encoding="utf-8")
        assert "  " not in extract_text(f, "file.html")

    def test_htm_extension_works(self, tmp_path):
        f = tmp_path / "file.htm"
        f.write_text("<p>Content</p>", encoding="utf-8")
        assert "Content" in extract_text(f, "file.htm")


# ---------------------------------------------------------------------------
# extract_text — generic text probe
# ---------------------------------------------------------------------------

class TestExtractGenericText:
    """Any extension with plain-text content is accepted without being in a list."""

    @pytest.mark.parametrize("extension,content", [
        (".txt",     "Hello world"),
        (".md",      "# Title\n\nSome content."),
        (".py",      "def hello():\n    return 'world'\n"),
        (".java",    "public class Hello {}"),
        (".c",       "#include <stdio.h>\nint main() { return 0; }"),
        (".cpp",     "#include <iostream>\nint main() { return 0; }"),
        (".cs",      "namespace App { class Program {} }"),
        (".js",      "function hello() { return 'world'; }"),
        (".ts",      "const x: string = 'hello';"),
        (".go",      "package main\nfunc main() {}"),
        (".rs",      "fn main() {}"),
        (".rb",      "def hello\n  'world'\nend"),
        (".sh",      "#!/bin/bash\necho hello"),
        (".sql",     "SELECT id FROM users;"),
        (".yaml",    "key: value"),
        (".json",    '{"key": "value"}'),
        (".toml",    "[section]\nkey = \"value\""),
        (".ini",     "[section]\nkey=value"),
        (".xml",     "<root><child/></root>"),
        (".css",     "body { margin: 0; }"),
        (".scss",    "$primary: #333;"),
        (".graphql", "query { user { name } }"),
        (".rst",     "Title\n=====\n\nParagraph."),
        (".tex",     "\\begin{document}Hello\\end{document}"),
        (".lua",     "function hello() end"),
        (".r",       "x <- 1"),
        (".brandnew", "any text content"),  # unknown extension — content decides
    ])
    def test_extracts_plain_text_file(self, tmp_path: Path, extension: str, content: str):
        filename = f"file{extension}"
        f = tmp_path / filename
        f.write_text(content, encoding="utf-8")
        assert extract_text(f, filename) == content

    def test_preserves_unicode(self, tmp_path):
        content = "# -*- coding: utf-8 -*-\nname = 'André'\n"
        f = tmp_path / "file.py"
        f.write_text(content, encoding="utf-8")
        assert extract_text(f, "file.py") == content

    def test_falls_back_to_latin1(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes("café".encode("latin-1"))
        assert "caf" in extract_text(f, "file.txt")


# ---------------------------------------------------------------------------
# extract_text — binary rejection
# ---------------------------------------------------------------------------

class TestBinaryRejection:
    def test_rejects_known_binary_extension(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with pytest.raises(ValueError, match="known binary format"):
            extract_text(f, "image.png")

    def test_rejects_file_with_null_bytes(self, tmp_path):
        # Use an extension not in _KNOWN_BINARY_EXTENSIONS so the content probe runs.
        f = tmp_path / "file.unknownext"
        f.write_bytes(b"some\x00binary\x00content")
        with pytest.raises(ValueError, match="binary content"):
            extract_text(f, "file.unknownext")

    def test_rejects_file_with_high_non_text_ratio(self, tmp_path):
        f = tmp_path / "compiled.unknownext"
        # Fill with control characters well above the 30% threshold.
        f.write_bytes(bytes([0x01, 0x02, 0x03, 0x04] * 200) + b"text" * 10)
        with pytest.raises(ValueError, match="binary content"):
            extract_text(f, "compiled.unknownext")

    def test_accepts_file_with_low_non_text_ratio(self, tmp_path):
        # A few stray bytes mixed into mostly-text content should still pass.
        f = tmp_path / "file.log"
        content = b"Normal log line\n" * 100 + b"\x1b[32mColored\x1b[0m\n"
        f.write_bytes(content)
        result = extract_text(f, "file.log")
        assert "Normal log line" in result


# ---------------------------------------------------------------------------
# extract_text — import guards for dedicated parsers
# ---------------------------------------------------------------------------

class TestExtractPdf:
    def test_raises_on_invalid_pdf(self, tmp_path):
        f = tmp_path / "file.pdf"
        f.write_bytes(b"%PDF fake")
        with pytest.raises((ImportError, Exception)):
            extract_text(f, "file.pdf")


class TestExtractDocx:
    def test_raises_on_invalid_docx(self, tmp_path):
        f = tmp_path / "file.docx"
        f.write_bytes(b"PK fake docx")
        with pytest.raises((ImportError, Exception)):
            extract_text(f, "file.docx")


class TestExtractXlsx:
    def test_raises_on_invalid_xlsx(self, tmp_path):
        f = tmp_path / "file.xlsx"
        f.write_bytes(b"PK fake xlsx")
        with pytest.raises((ImportError, Exception)):
            extract_text(f, "file.xlsx")


