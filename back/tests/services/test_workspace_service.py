"""
Tests for src.services.workspace_service.

Covers:
- truncate_string_value
- truncate_compiled_variables (strings, dicts, lists, author exclusion)
- WorkspaceService._format_value
- WorkspaceService._variables_dict_to_ple
- WorkspaceService.from_json_to_ple (field mapping, component instances)
- WorkspaceService.parse_component_instances_from_sandbox
- WorkspaceService.sanitise_exercise_data
- WorkspaceService.transform_compil_variables_to_ple
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.services.workspace_service import (
    WorkspaceService,
    truncate_string_value,
    truncate_compiled_variables,
    REQUIRED_FIELDS_MAX_LENGTH,
    OTHER_FIELDS_MAX_LENGTH,
)
from src.services.models.api import ComponentInstance, ExerciseData


# ---------------------------------------------------------------------------
# truncate_string_value
# ---------------------------------------------------------------------------

class TestTruncateStringValue:
    def test_short_string_unchanged(self):
        assert truncate_string_value("hello", 100) == "hello"

    def test_exact_length_unchanged(self):
        s = "a" * 100
        assert truncate_string_value(s, 100) == s

    def test_long_string_is_truncated(self):
        s = "a" * 200
        result = truncate_string_value(s, 100)
        assert len(result) == 103  # 100 + len("...")
        assert result.endswith("...")

    def test_empty_string(self):
        assert truncate_string_value("", 10) == ""


# ---------------------------------------------------------------------------
# truncate_compiled_variables
# ---------------------------------------------------------------------------

class TestTruncateCompiledVariables:
    def test_author_field_is_excluded(self):
        data = {"author": "John", "title": "My Exercise"}
        result = truncate_compiled_variables(data)
        assert "author" not in result
        assert "title" in result

    def test_required_field_uses_long_limit(self):
        long_value = "x" * (REQUIRED_FIELDS_MAX_LENGTH + 50)
        data = {"title": long_value}
        result = truncate_compiled_variables(data)
        assert len(result["title"]) == REQUIRED_FIELDS_MAX_LENGTH + 3  # + "..."

    def test_other_field_uses_short_limit(self):
        long_value = "x" * (OTHER_FIELDS_MAX_LENGTH + 50)
        data = {"custom_field": long_value}
        result = truncate_compiled_variables(data)
        assert len(result["custom_field"]) == OTHER_FIELDS_MAX_LENGTH + 3

    def test_nested_dict_is_truncated(self):
        # Nested dicts exclude "author" key and truncate long strings.
        # "desc" is not in STANDARD_REQUIRED_FIELDS so uses OTHER_FIELDS_MAX_LENGTH (500).
        data = {"nested": {"author": "skip", "desc": "a" * 600}}
        result = truncate_compiled_variables(data)
        assert "author" not in result["nested"]
        assert len(result["nested"]["desc"]) == OTHER_FIELDS_MAX_LENGTH + 3

    def test_list_of_strings(self):
        # "hint" IS a required field so max_length = REQUIRED_FIELDS_MAX_LENGTH (1000).
        # Use a string over 1000 chars to trigger truncation.
        data = {"hint": ["a" * 1100, "short"]}
        result = truncate_compiled_variables(data)
        assert len(result["hint"][0]) == REQUIRED_FIELDS_MAX_LENGTH + 3
        assert result["hint"][1] == "short"

    def test_list_of_dicts(self):
        # "theories" IS a required field, but dict items inside the list are processed
        # with truncate_value(v, k) where k is the sub-key — "url" is not required.
        # So "url" uses OTHER_FIELDS_MAX_LENGTH (500).
        data = {"theories": [{"title": "T", "url": "u" * 600}]}
        result = truncate_compiled_variables(data)
        assert result["theories"][0]["title"] == "T"
        assert len(result["theories"][0]["url"]) == OTHER_FIELDS_MAX_LENGTH + 3

    def test_integer_value_preserved(self):
        data = {"count": 42}
        result = truncate_compiled_variables(data)
        assert result["count"] == 42

    def test_empty_dict(self):
        assert truncate_compiled_variables({}) == {}


# ---------------------------------------------------------------------------
# WorkspaceService._format_value
# ---------------------------------------------------------------------------

class TestFormatValue:
    def setup_method(self):
        self.service = WorkspaceService()

    def test_string_value_is_quoted(self):
        assert self.service._format_value("hello") == '"hello"'

    def test_integer_value_is_str(self):
        assert self.service._format_value(42) == "42"

    def test_empty_list(self):
        assert self.service._format_value([]) == "[]"

    def test_list_of_strings(self):
        result = self.service._format_value(["a", "b"])
        assert '"a"' in result
        assert '"b"' in result

    def test_list_of_dicts(self):
        result = self.service._format_value([{"key": "val"}])
        assert "key" in result
        assert '"val"' in result

    def test_dict_value(self):
        result = self.service._format_value({"x": "y"})
        assert "x" in result
        assert '"y"' in result

    def test_none_becomes_none_string(self):
        assert self.service._format_value(None) == "None"


# ---------------------------------------------------------------------------
# WorkspaceService._variables_dict_to_ple
# ---------------------------------------------------------------------------

class TestVariablesDictToPle:
    def setup_method(self):
        self.service = WorkspaceService()

    def test_sandbox_uses_inline_assignment(self):
        result = self.service._variables_dict_to_ple({"sandbox": "python"})
        assert 'sandbox = "python"' in result

    def test_title_uses_inline_assignment(self):
        result = self.service._variables_dict_to_ple({"title": "My Title"})
        assert 'title = "My Title"' in result

    def test_non_special_field_uses_block_assignment(self):
        result = self.service._variables_dict_to_ple({"statement": "Do this."})
        assert "statement ==\nDo this.\n==" in result

    def test_empty_hint_list_is_skipped(self):
        result = self.service._variables_dict_to_ple({"hint": []})
        assert "hint" not in result

    def test_none_hint_is_skipped(self):
        result = self.service._variables_dict_to_ple({"hint": None})
        assert "hint" not in result

    def test_non_empty_hint_is_included(self):
        result = self.service._variables_dict_to_ple({"hint": ["tip1"]})
        assert "hint" in result

    def test_author_field_is_skipped(self):
        result = self.service._variables_dict_to_ple({"author": "John", "title": "T"})
        assert "author" not in result
        assert "title" in result

    def test_empty_dict_returns_empty_string(self):
        result = self.service._variables_dict_to_ple({})
        assert result == ""

    def test_multiple_fields_each_on_separate_line(self):
        result = self.service._variables_dict_to_ple({
            "title": "T",
            "sandbox": "node",
        })
        lines = result.split("\n")
        assert any("title" in line for line in lines)
        assert any("sandbox" in line for line in lines)


# ---------------------------------------------------------------------------
# WorkspaceService.from_json_to_ple
# ---------------------------------------------------------------------------

class TestFromJsonToPle:
    def setup_method(self):
        self.service = WorkspaceService()

    def _make_exercise(self, **kwargs) -> ExerciseData:
        return ExerciseData(**kwargs)

    @patch("src.services.workspace_service.save_ple_output")
    def test_titre_maps_to_title(self, mock_save):
        ex = self._make_exercise(titre="My Title")
        result = self.service.from_json_to_ple(ex)
        assert "title" in result
        assert '"My Title"' in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_enonce_maps_to_statement(self, mock_save):
        ex = self._make_exercise(enonce="Do this.")
        result = self.service.from_json_to_ple(ex)
        assert "statement" in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_construction_maps_to_builder(self, mock_save):
        ex = self._make_exercise(construction="def b(): pass")
        result = self.service.from_json_to_ple(ex)
        assert "builder" in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_evaluation_maps_to_grader(self, mock_save):
        ex = self._make_exercise(evaluation="def g(): pass")
        result = self.service.from_json_to_ple(ex)
        assert "grader" in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_empty_exercise_returns_empty_ple(self, mock_save):
        ex = ExerciseData()
        result = self.service.from_json_to_ple(ex)
        assert result == ""

    @patch("src.services.workspace_service.save_ple_output")
    def test_sandbox_variables_are_included(self, mock_save):
        ex = self._make_exercise(sandbox_variables={"custom_var": "custom_val"})
        result = self.service.from_json_to_ple(ex)
        assert "custom_var" in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_component_instances_are_appended(self, mock_save):
        ci = ComponentInstance(
            id="inst-abc",
            selector="wc-quiz",
            componentName="Quiz",
            instanceName="q1",
            category="Widget",
            properties={"question": "What?"},
        )
        ex = self._make_exercise(component_instances=[ci])
        result = self.service.from_json_to_ple(ex)
        assert "q1 = :wc-quiz" in result
        assert "q1.question" in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_component_list_property_is_formatted(self, mock_save):
        ci = ComponentInstance(
            id="inst-abc",
            selector="wc-quiz",
            componentName="Quiz",
            instanceName="q1",
            category="Widget",
            properties={"choices": ["A", "B", "C"]},
        )
        ex = self._make_exercise(component_instances=[ci])
        result = self.service.from_json_to_ple(ex)
        assert "q1.choices" in result

    @patch("src.services.workspace_service.save_ple_output")
    def test_save_ple_output_is_called(self, mock_save):
        ex = self._make_exercise(titre="T")
        self.service.from_json_to_ple(ex)
        mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# WorkspaceService.parse_component_instances_from_sandbox
# ---------------------------------------------------------------------------

class TestParseComponentInstancesFromSandbox:
    def setup_method(self):
        self.service = WorkspaceService()

    @patch("src.services.workspace_service.load_components_metadata")
    def test_empty_sandbox_variables_returns_empty_list(self, mock_meta):
        result = self.service.parse_component_instances_from_sandbox({})
        assert result == []

    @patch("src.services.workspace_service.load_components_metadata")
    def test_none_sandbox_variables_returns_empty_list(self, mock_meta):
        result = self.service.parse_component_instances_from_sandbox(None)
        assert result == []

    @patch("src.services.workspace_service.load_components_metadata")
    def test_variable_without_selector_is_skipped(self, mock_meta):
        mock_meta.return_value = []
        result = self.service.parse_component_instances_from_sandbox({"x": {"cid": "1"}})
        assert result == []

    @patch("src.services.workspace_service.load_components_metadata")
    def test_unknown_selector_is_skipped_with_warning(self, mock_meta):
        mock_meta.return_value = []
        result = self.service.parse_component_instances_from_sandbox(
            {"q1": {"cid": "1", "selector": "tag-unknown"}}
        )
        assert result == []

    @patch("src.services.workspace_service.load_components_metadata")
    def test_known_selector_produces_component_instance(self, mock_meta):
        mock_meta.return_value = [{
            "tag": "tag-quiz",
            "name": "Quiz",
            "category": "Widget",
        }]
        result = self.service.parse_component_instances_from_sandbox({
            "q1": {"cid": "1", "selector": "tag-quiz", "question": "What?"}
        })
        assert len(result) == 1
        ci = result[0]
        assert ci.instanceName == "q1"
        assert ci.selector == "tag-quiz"
        assert ci.id != "tag-quiz"
        assert len(ci.id) > 0
        assert ci.componentName == "Quiz"
        assert "question" in ci.properties
        assert "cid" not in ci.properties
        assert "selector" not in ci.properties

    @patch("src.services.workspace_service.load_components_metadata")
    def test_non_component_dict_is_skipped(self, mock_meta):
        mock_meta.return_value = []
        result = self.service.parse_component_instances_from_sandbox({"x": "not-a-dict"})
        assert result == []

    @patch("src.services.workspace_service.load_components_metadata")
    def test_multiple_components_parsed(self, mock_meta):
        mock_meta.return_value = [
            {"tag": "tag-a", "name": "A", "category": "C"},
            {"tag": "tag-b", "name": "B", "category": "C"},
        ]
        result = self.service.parse_component_instances_from_sandbox({
            "inst_a": {"cid": "1", "selector": "tag-a"},
            "inst_b": {"cid": "2", "selector": "tag-b"},
        })
        assert len(result) == 2


# ---------------------------------------------------------------------------
# WorkspaceService.sanitise_exercise_data
# ---------------------------------------------------------------------------

class TestSanitiseExerciseData:
    def setup_method(self):
        self.service = WorkspaceService()

    @patch("src.services.workspace_service.load_components_metadata")
    def test_no_sandbox_variables_is_noop(self, mock_meta):
        ex = ExerciseData()
        self.service.sanitise_exercise_data(ex)
        assert ex.component_instances == []

    @patch("src.services.workspace_service.load_components_metadata")
    def test_component_dicts_moved_to_instances(self, mock_meta):
        mock_meta.return_value = [{"tag": "tag-q", "name": "Q", "category": "C"}]
        ex = ExerciseData(sandbox_variables={"q1": {"cid": "1", "selector": "tag-q"}})
        self.service.sanitise_exercise_data(ex)
        assert len(ex.component_instances) == 1
        assert ex.component_instances[0].instanceName == "q1"
        # Component dict removed from sandbox_variables
        assert "q1" not in ex.sandbox_variables

    @patch("src.services.workspace_service.load_components_metadata")
    def test_no_duplicate_instances_added(self, mock_meta):
        mock_meta.return_value = [{"tag": "tag-q", "name": "Q", "category": "C"}]
        existing = ComponentInstance(
            id="inst-abc", selector="tag-q", componentName="Q", instanceName="q1",
            category="C", properties={}
        )
        ex = ExerciseData(
            component_instances=[existing],
            sandbox_variables={"q1": {"cid": "1", "selector": "tag-q"}},
        )
        self.service.sanitise_exercise_data(ex)
        # Should not add a duplicate
        assert len(ex.component_instances) == 1

    @patch("src.services.workspace_service.load_components_metadata")
    def test_non_component_sandbox_vars_are_preserved(self, mock_meta):
        mock_meta.return_value = []
        ex = ExerciseData(sandbox_variables={"plain_var": "some value"})
        self.service.sanitise_exercise_data(ex)
        assert ex.sandbox_variables.get("plain_var") == "some value"


# ---------------------------------------------------------------------------
# WorkspaceService.transform_compil_variables_to_ple
# ---------------------------------------------------------------------------

class TestTransformCompilVariablesToPle:
    def setup_method(self):
        self.service = WorkspaceService()

    def test_delegates_to_variables_dict_to_ple(self):
        result = self.service.transform_compil_variables_to_ple({"title": "T"})
        assert "title" in result
        assert '"T"' in result

    def test_empty_dict_returns_empty_string(self):
        result = self.service.transform_compil_variables_to_ple({})
        assert result == ""

