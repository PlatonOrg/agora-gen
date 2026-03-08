"""
Tests for src.core.path_constants.

Covers:
- resolve_path: None input, absolute path, relative path resolution
- Constant coherence: RESOURCES_DIR is a child of CONTAINER_ROOT
"""
from __future__ import annotations

from pathlib import Path

from src.core.path_constants import (
    CONTAINER_ROOT,
    RESOURCES_DIR,
    PROMPTS_DIR,
    COMPONENT_METADATA_PATH,
    resolve_path,
)


class TestResolvePathFunction:
    def test_none_returns_none(self):
        assert resolve_path(None) is None

    def test_absolute_path_returned_unchanged(self):
        p = Path("/opt/models/some-model")
        result = resolve_path(p)
        assert result == p

    def test_absolute_string_returned_as_path(self):
        result = resolve_path("/opt/models/some-model")
        assert result == Path("/opt/models/some-model")

    def test_relative_string_anchored_to_container_root(self):
        result = resolve_path("resources/docs")
        assert result == CONTAINER_ROOT / "resources" / "docs"

    def test_relative_path_object_anchored_to_container_root(self):
        result = resolve_path(Path("resources/docs"))
        assert result == CONTAINER_ROOT / "resources" / "docs"

    def test_returns_path_instance(self):
        result = resolve_path("some/relative")
        assert isinstance(result, Path)


class TestPathConstantCoherence:
    def test_resources_dir_is_child_of_container_root(self):
        assert RESOURCES_DIR.parts[:len(CONTAINER_ROOT.parts)] == CONTAINER_ROOT.parts

    def test_prompts_dir_is_under_resources(self):
        assert str(PROMPTS_DIR).startswith(str(RESOURCES_DIR))

    def test_component_metadata_path_ends_with_json(self):
        assert COMPONENT_METADATA_PATH.suffix == ".json"

    def test_container_root_is_absolute(self):
        assert CONTAINER_ROOT.is_absolute()

