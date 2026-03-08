"""
Tests for src.infra.llm.json_facility.

Covers:
- build_fixed_exercise_json_schema: full schema, filtered schema, additionalProperties logic
- build_json_schema_from_config: TYPE_MAP usage, list/select/number/code special cases,
  include_properties filtering, malformed inputs, empty config
"""
from __future__ import annotations

import pytest
from src.infra.llm.json_facility import (
    build_fixed_exercise_json_schema,
    build_json_schema_from_config,
)


# ---------------------------------------------------------------------------
# build_fixed_exercise_json_schema
# ---------------------------------------------------------------------------

class TestBuildFixedExerciseJsonSchema:
    def test_returns_object_type(self):
        schema = build_fixed_exercise_json_schema()
        assert schema["type"] == "object"

    def test_all_core_properties_present(self):
        schema = build_fixed_exercise_json_schema()
        expected = {"name", "description", "title", "sandbox", "builder",
                    "grader", "statement", "form", "solution", "hint", "theories",
                    "metadata"}
        assert expected.issubset(schema["properties"].keys())

    def test_required_fields_all_present(self):
        schema = build_fixed_exercise_json_schema()
        required = set(schema["required"])
        assert "name" in required
        assert "title" in required
        assert "sandbox" in required
        assert "grader" in required
        assert "metadata" in required

    def test_sandbox_has_enum(self):
        schema = build_fixed_exercise_json_schema()
        sandbox = schema["properties"]["sandbox"]
        assert "enum" in sandbox
        assert "python" in sandbox["enum"]
        assert "node" in sandbox["enum"]

    def test_metadata_contains_levels_and_topics(self):
        schema = build_fixed_exercise_json_schema()
        metadata = schema["properties"]["metadata"]
        assert metadata["type"] == "object"
        levels = metadata["properties"]["levels"]
        assert levels["type"] == "array"
        assert levels["items"]["type"] == "string"
        topics = metadata["properties"]["topics"]
        assert topics["type"] == "array"
        assert topics["items"]["type"] == "string"

    def test_metadata_contains_pedagogical_fields(self):
        schema = build_fixed_exercise_json_schema()
        meta_props = schema["properties"]["metadata"]["properties"]
        assert meta_props["objectifs_pedagogiques"]["type"] == "string"
        assert meta_props["public_vise"]["type"] == "string"
        assert meta_props["prerequis"]["type"] == "string"
        assert meta_props["consignes"]["type"] == "string"

    def test_metadata_requires_levels_and_topics(self):
        schema = build_fixed_exercise_json_schema()
        metadata = schema["properties"]["metadata"]
        assert "levels" in metadata["required"]
        assert "topics" in metadata["required"]

    def test_hint_is_array_of_strings(self):
        schema = build_fixed_exercise_json_schema()
        hint = schema["properties"]["hint"]
        assert hint["type"] == "array"
        assert hint["items"]["type"] == "string"

    def test_theories_is_array_of_objects(self):
        schema = build_fixed_exercise_json_schema()
        theories = schema["properties"]["theories"]
        assert theories["type"] == "array"
        assert "title" in theories["items"]["properties"]
        assert "url" in theories["items"]["properties"]

    def test_additional_properties_true_when_no_filter(self):
        schema = build_fixed_exercise_json_schema()
        assert schema.get("additionalProperties") is True

    def test_filter_keeps_only_specified_properties(self):
        schema = build_fixed_exercise_json_schema(include_properties=["name", "title"])
        assert set(schema["properties"].keys()) == {"name", "title"}

    def test_filter_adjusts_required_list(self):
        schema = build_fixed_exercise_json_schema(include_properties=["name", "sandbox"])
        assert "name" in schema["required"]
        assert "sandbox" in schema["required"]
        assert "title" not in schema["required"]

    def test_additional_properties_false_when_filtered_without_sandbox_variables(self):
        schema = build_fixed_exercise_json_schema(include_properties=["name", "title"])
        assert schema.get("additionalProperties") is not True

    def test_additional_properties_true_when_sandbox_variables_in_filter(self):
        schema = build_fixed_exercise_json_schema(include_properties=["name", "sandbox_variables"])
        assert schema.get("additionalProperties") is True

    def test_empty_include_properties_produces_empty_schema(self):
        schema = build_fixed_exercise_json_schema(include_properties=[])
        assert schema["properties"] == {}
        assert schema["required"] == []


# ---------------------------------------------------------------------------
# build_json_schema_from_config
# ---------------------------------------------------------------------------

class TestBuildJsonSchemaFromConfig:
    def test_always_includes_name_and_description(self):
        schema = build_json_schema_from_config([])
        assert "name" in schema["properties"]
        assert "description" in schema["properties"]

    def test_always_includes_metadata(self):
        schema = build_json_schema_from_config([])
        assert "metadata" in schema["properties"]
        meta_props = schema["properties"]["metadata"]["properties"]
        assert "levels" in meta_props
        assert "topics" in meta_props
        assert "objectifs_pedagogiques" in meta_props
        assert "public_vise" in meta_props
        assert "prerequis" in meta_props
        assert "consignes" in meta_props

    def test_text_type_maps_to_string(self):
        config = [{"name": "question", "type": "text", "description": "d", "value": ""}]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["question"]["type"] == "string"

    def test_number_type_maps_to_integer(self):
        config = [{"name": "count", "type": "number", "description": "d", "value": "5"}]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["count"]["type"] == "integer"

    def test_boolean_type_maps_to_boolean(self):
        config = [{"name": "flag", "type": "boolean", "description": "d", "value": "true"}]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["flag"]["type"] == "boolean"

    def test_list_type_produces_array_with_string_items(self):
        config = [{"name": "items", "type": "list", "description": "d", "value": ""}]
        schema = build_json_schema_from_config(config)
        prop = schema["properties"]["items"]
        assert prop["type"] == "array"
        assert prop["items"]["type"] == "string"

    def test_select_type_produces_enum(self):
        config = [{
            "name": "difficulty",
            "type": "select",
            "description": "d",
            "value": "easy",
            "options": {"choices": ["easy", "medium", "hard"]},
        }]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["difficulty"]["enum"] == ["easy", "medium", "hard"]

    def test_select_type_without_choices_has_no_enum(self):
        config = [{"name": "x", "type": "select", "description": "d", "value": "a"}]
        schema = build_json_schema_from_config(config)
        assert "enum" not in schema["properties"]["x"]

    def test_number_type_with_min_max_options(self):
        config = [{
            "name": "n",
            "type": "number",
            "description": "d",
            "value": "0",
            "options": {"min": 1, "max": 10},
        }]
        schema = build_json_schema_from_config(config)
        prop = schema["properties"]["n"]
        assert prop["minimum"] == 1
        assert prop["maximum"] == 10

    def test_code_type_with_numeric_value_becomes_number(self):
        config = [{"name": "x", "type": "code", "description": "d", "value": "3.14"}]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["x"]["type"] == "number"

    def test_code_type_with_string_value_stays_string(self):
        config = [{"name": "x", "type": "code", "description": "d", "value": "not_a_number"}]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["x"]["type"] == "string"

    def test_code_type_with_none_value_defaults_string(self):
        config = [{"name": "x", "type": "code", "description": "d", "value": None}]
        schema = build_json_schema_from_config(config)
        assert schema["properties"]["x"]["type"] == "string"

    def test_unknown_type_is_skipped(self):
        config = [{"name": "x", "type": "UNKNOWN_TYPE", "description": "d", "value": "v"}]
        schema = build_json_schema_from_config(config)
        assert "x" not in schema["properties"]

    def test_missing_name_is_skipped(self):
        config = [{"type": "text", "description": "d", "value": "v"}]
        schema = build_json_schema_from_config(config)
        assert set(schema["properties"].keys()) == {"name", "description", "metadata"}

    def test_non_dict_entry_is_skipped(self):
        config = ["not-a-dict", {"name": "q", "type": "text", "description": "d", "value": ""}]
        schema = build_json_schema_from_config(config)
        assert "q" in schema["properties"]

    def test_required_includes_all_variable_names(self):
        config = [
            {"name": "a", "type": "text", "description": "d", "value": ""},
            {"name": "b", "type": "number", "description": "d", "value": "1"},
        ]
        schema = build_json_schema_from_config(config)
        assert "a" in schema["required"]
        assert "b" in schema["required"]

    def test_additional_properties_false(self):
        schema = build_json_schema_from_config([])
        assert schema["additionalProperties"] is False

    def test_include_properties_filters_variables(self):
        config = [
            {"name": "a", "type": "text", "description": "d", "value": ""},
            {"name": "b", "type": "text", "description": "d", "value": ""},
        ]
        schema = build_json_schema_from_config(config, include_properties=["a"])
        assert "a" in schema["properties"]
        assert "b" not in schema["properties"]

    def test_include_properties_empty_excludes_all_vars(self):
        config = [{"name": "a", "type": "text", "description": "d", "value": ""}]
        schema = build_json_schema_from_config(config, include_properties=[])
        assert "a" not in schema["properties"]

    def test_empty_config_produces_minimal_schema(self):
        schema = build_json_schema_from_config([])
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "description" in schema["properties"]

