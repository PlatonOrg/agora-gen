"""
Tests for pure helper functions in src.api.v1.endpoints.context.

These functions contain business logic but have zero I/O — they are ideal
unit-test targets. The HTTP route handlers themselves are integration-level
and are tested in test_endpoints_auth.py / test_endpoints_exercises.py.

Covers:
- _transform_platon_tree_to_frontend_format: normal tree, empty dict, None
- _extract_circles_from_tree: flat and nested trees, missing id/name skipped
- _transform_platon_topics_to_frontend_format: normal, non-list input, non-dict item
- _transform_platon_levels_to_frontend_format: normal, non-list input
"""
from __future__ import annotations

from src.api.v1.endpoints.context import (
    _transform_platon_tree_to_frontend_format,
    _extract_circles_from_tree,
    _transform_platon_topics_to_frontend_format,
    _transform_platon_levels_to_frontend_format,
)
from src.services.models.api import TreeNode


# ---------------------------------------------------------------------------
# _transform_platon_tree_to_frontend_format
# ---------------------------------------------------------------------------

class TestTransformPlatonTreeToFrontendFormat:
    def test_empty_dict_returns_platon_root(self):
        result = _transform_platon_tree_to_frontend_format({})
        assert isinstance(result, TreeNode)
        assert result.name == "PLaTon"

    def test_none_returns_platon_root(self):
        result = _transform_platon_tree_to_frontend_format(None)
        assert result.name == "PLaTon"

    def test_single_node(self):
        result = _transform_platon_tree_to_frontend_format({"name": "Root", "children": []})
        assert result.name == "Root"
        assert result.children == []

    def test_nested_children(self):
        tree = {
            "name": "Root",
            "children": [
                {"name": "Child A", "children": []},
                {"name": "Child B", "children": [
                    {"name": "Grandchild", "children": []}
                ]},
            ],
        }
        result = _transform_platon_tree_to_frontend_format(tree)
        assert len(result.children) == 2
        assert result.children[1].children[0].name == "Grandchild"

    def test_none_children_in_list_are_skipped(self):
        tree = {"name": "Root", "children": [None, {"name": "Valid", "children": []}]}
        result = _transform_platon_tree_to_frontend_format(tree)
        assert len(result.children) == 1
        assert result.children[0].name == "Valid"

    def test_missing_name_defaults_to_empty_string(self):
        result = _transform_platon_tree_to_frontend_format({"children": []})
        assert result.name == ""


# ---------------------------------------------------------------------------
# _extract_circles_from_tree
# ---------------------------------------------------------------------------

class TestExtractCirclesFromTree:
    def test_empty_dict_returns_empty_list(self):
        assert _extract_circles_from_tree({}) == []

    def test_none_returns_empty_list(self):
        assert _extract_circles_from_tree(None) == []

    def test_single_node_with_id_and_name(self):
        tree = {"id": "c1", "name": "Circle One", "children": []}
        result = _extract_circles_from_tree(tree)
        assert len(result) == 1
        assert result[0].id == "c1"
        assert result[0].name == "Circle One"

    def test_node_without_id_is_skipped(self):
        tree = {"name": "No ID", "children": []}
        result = _extract_circles_from_tree(tree)
        assert result == []

    def test_node_without_name_is_skipped(self):
        tree = {"id": "c1", "children": []}
        result = _extract_circles_from_tree(tree)
        assert result == []

    def test_nested_children_extracted_recursively(self):
        tree = {
            "id": "root", "name": "Root", "children": [
                {"id": "child1", "name": "Child 1", "children": []},
            ],
        }
        result = _extract_circles_from_tree(tree)
        assert len(result) == 2
        ids = {r.id for r in result}
        assert ids == {"root", "child1"}

    def test_parent_id_set_on_children(self):
        tree = {
            "id": "parent", "name": "Parent", "children": [
                {"id": "child", "name": "Child", "children": []},
            ],
        }
        result = _extract_circles_from_tree(tree)
        child = next(r for r in result if r.id == "child")
        assert child.parentId == "parent"

    def test_has_children_flag_set_correctly(self):
        tree = {
            "id": "root", "name": "Root", "children": [
                {"id": "leaf", "name": "Leaf", "children": []},
            ],
        }
        result = _extract_circles_from_tree(tree)
        root = next(r for r in result if r.id == "root")
        leaf = next(r for r in result if r.id == "leaf")
        assert root.hasChildren is True
        assert leaf.hasChildren is False


# ---------------------------------------------------------------------------
# _transform_platon_topics_to_frontend_format
# ---------------------------------------------------------------------------

class TestTransformPlatonTopicsToFrontendFormat:
    def test_valid_list_returns_topics(self):
        topics = [{"id": "t1", "name": "Algebra"}, {"id": "t2", "name": "Geometry"}]
        result = _transform_platon_topics_to_frontend_format(topics)
        assert len(result) == 2
        assert result[0].id == "t1"
        assert result[1].name == "Geometry"

    def test_non_list_returns_empty_list(self):
        assert _transform_platon_topics_to_frontend_format("not-a-list") == []
        assert _transform_platon_topics_to_frontend_format(None) == []
        assert _transform_platon_topics_to_frontend_format(42) == []

    def test_non_dict_item_is_skipped(self):
        topics = ["not-a-dict", {"id": "t1", "name": "Valid"}]
        result = _transform_platon_topics_to_frontend_format(topics)
        assert len(result) == 1
        assert result[0].id == "t1"

    def test_item_without_id_is_skipped(self):
        topics = [{"name": "No ID"}]
        result = _transform_platon_topics_to_frontend_format(topics)
        assert result == []

    def test_description_is_generated(self):
        topics = [{"id": "t1", "name": "Algebra"}]
        result = _transform_platon_topics_to_frontend_format(topics)
        assert "Algebra" in result[0].description

    def test_empty_list_returns_empty_list(self):
        assert _transform_platon_topics_to_frontend_format([]) == []


# ---------------------------------------------------------------------------
# _transform_platon_levels_to_frontend_format
# ---------------------------------------------------------------------------

class TestTransformPlatonLevelsToFrontendFormat:
    def test_valid_list_returns_levels(self):
        levels = [{"id": "l1", "name": "Grade 5"}]
        result = _transform_platon_levels_to_frontend_format(levels)
        assert len(result) == 1
        assert result[0].id == "l1"

    def test_non_list_returns_empty_list(self):
        assert _transform_platon_levels_to_frontend_format({}) == []
        assert _transform_platon_levels_to_frontend_format(None) == []

    def test_item_without_id_is_skipped(self):
        levels = [{"name": "No ID"}]
        assert _transform_platon_levels_to_frontend_format(levels) == []

    def test_non_dict_item_is_skipped(self):
        levels = ["bad", {"id": "l1", "name": "Good"}]
        result = _transform_platon_levels_to_frontend_format(levels)
        assert len(result) == 1

    def test_description_is_generated(self):
        levels = [{"id": "l1", "name": "Grade 5"}]
        result = _transform_platon_levels_to_frontend_format(levels)
        assert "Grade 5" in result[0].description

    def test_empty_list(self):
        assert _transform_platon_levels_to_frontend_format([]) == []

