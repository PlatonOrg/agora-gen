from __future__ import annotations

import pytest

from src.services.builder_component_extractor import (
    ExtractionResult,
    extract_components_from_builder,
)


# ---------------------------------------------------------------------------
# extract_components_from_builder
# ---------------------------------------------------------------------------

class TestExtractComponentsFromBuilder:

    def test_empty_builder_returns_unchanged(self):
        result = extract_components_from_builder("")
        assert result.cleaned_builder == ""
        assert result.extracted_components == {}

    def test_whitespace_only_builder_returns_unchanged(self):
        result = extract_components_from_builder("   \n  ")
        assert result.extracted_components == {}

    def test_builder_without_components_unchanged(self):
        source = "x = 42\ny = x + 1\n"
        result = extract_components_from_builder(source)
        assert result.extracted_components == {}
        assert "x = 42" in result.cleaned_builder
        assert "y = x + 1" in result.cleaned_builder

    def test_single_component_extracted(self):
        source = (
            "x = 1\n"
            "my_input = {\n"
            "    'selector': 'wc-input-box',\n"
            "    'placeholder': 'Enter answer',\n"
            "}\n"
            "y = x + 1\n"
        )
        result = extract_components_from_builder(source)
        assert "my_input" in result.extracted_components
        assert result.extracted_components["my_input"]["selector"] == "wc-input-box"
        assert result.extracted_components["my_input"]["placeholder"] == "Enter answer"
        assert "my_input" not in result.cleaned_builder
        assert "x = 1" in result.cleaned_builder
        assert "y = x + 1" in result.cleaned_builder

    def test_multiple_components_extracted(self):
        source = (
            "question = {'selector': 'wc-text-block', 'content': 'What is 2+2?'}\n"
            "answer_input = {'selector': 'wc-input-box', 'placeholder': '?'}\n"
            "expected = 4\n"
        )
        result = extract_components_from_builder(source)
        assert "question" in result.extracted_components
        assert "answer_input" in result.extracted_components
        assert result.extracted_components["question"]["selector"] == "wc-text-block"
        assert result.extracted_components["answer_input"]["selector"] == "wc-input-box"
        assert "question" not in result.cleaned_builder
        assert "answer_input" not in result.cleaned_builder
        assert "expected = 4" in result.cleaned_builder

    def test_dict_without_selector_not_extracted(self):
        source = (
            "config = {'key': 'value', 'other': 123}\n"
            "real_comp = {'selector': 'wc-input-box'}\n"
        )
        result = extract_components_from_builder(source)
        assert "config" not in result.extracted_components
        assert "real_comp" in result.extracted_components
        assert "config" in result.cleaned_builder

    def test_multiline_component_dict_fully_removed(self):
        source = (
            "import random\n"
            "a = random.randint(1, 10)\n"
            "b = random.randint(1, 10)\n"
            "answer_field = {\n"
            "    'selector': 'wc-input-box',\n"
            "    'placeholder': 'Votre réponse',\n"
            "    'type': 'number',\n"
            "}\n"
            "result = a + b\n"
        )
        result = extract_components_from_builder(source)
        assert "answer_field" in result.extracted_components
        assert result.extracted_components["answer_field"]["selector"] == "wc-input-box"
        assert result.extracted_components["answer_field"]["type"] == "number"
        assert "answer_field" not in result.cleaned_builder
        assert "selector" not in result.cleaned_builder
        assert "import random" in result.cleaned_builder
        assert "result = a + b" in result.cleaned_builder

    def test_component_at_start_of_builder(self):
        source = (
            "my_comp = {'selector': 'wc-radio', 'choices': ['a', 'b']}\n"
            "x = 10\n"
        )
        result = extract_components_from_builder(source)
        assert "my_comp" in result.extracted_components
        assert "x = 10" in result.cleaned_builder

    def test_component_at_end_of_builder(self):
        source = (
            "x = 10\n"
            "my_comp = {'selector': 'wc-radio', 'choices': ['a', 'b']}\n"
        )
        result = extract_components_from_builder(source)
        assert "my_comp" in result.extracted_components
        assert "x = 10" in result.cleaned_builder

    def test_syntax_error_returns_original_unchanged(self):
        source = "def broken(:\n    pass\n"
        result = extract_components_from_builder(source)
        assert result.cleaned_builder == source
        assert result.extracted_components == {}

    def test_non_name_target_not_extracted(self):
        source = (
            "obj.attr = {'selector': 'wc-input-box'}\n"
            "real = {'selector': 'wc-input-box'}\n"
        )
        result = extract_components_from_builder(source)
        assert "real" in result.extracted_components
        assert "obj" not in result.extracted_components
        assert "obj.attr" in result.cleaned_builder

    def test_multi_target_assignment_not_extracted(self):
        source = "a = b = {'selector': 'wc-input-box'}\n"
        result = extract_components_from_builder(source)
        assert result.extracted_components == {}
        assert "a = b" in result.cleaned_builder

    def test_cleaned_builder_is_valid_python(self):
        source = (
            "import random\n"
            "n = random.randint(1, 5)\n"
            "comp = {\n"
            "    'selector': 'wc-input-box',\n"
            "    'label': 'Answer',\n"
            "}\n"
            "answer = n * 2\n"
        )
        result = extract_components_from_builder(source)
        assert result.extracted_components
        try:
            compile(result.cleaned_builder, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Cleaned builder is not valid Python: {exc}")

    def test_extracted_component_has_all_properties(self):
        source = (
            "widget = {\n"
            "    'selector': 'wc-code-editor',\n"
            "    'language': 'python',\n"
            "    'height': '300px',\n"
            "    'readonly': False,\n"
            "}\n"
        )
        result = extract_components_from_builder(source)
        comp = result.extracted_components.get("widget")
        assert comp is not None
        assert comp["selector"] == "wc-code-editor"
        assert comp["language"] == "python"
        assert comp["height"] == "300px"
        assert comp["readonly"] is False

    def test_returns_extraction_result_type(self):
        result = extract_components_from_builder("x = 1\n")
        assert isinstance(result, ExtractionResult)

    def test_builder_only_components_becomes_empty_string(self):
        source = "comp = {'selector': 'wc-input-box'}\n"
        result = extract_components_from_builder(source)
        assert "comp" in result.extracted_components
        assert result.cleaned_builder == ""

    def test_indented_builder_handled(self):
        source = (
            "    import random\n"
            "    n = random.randint(1, 10)\n"
            "    comp = {'selector': 'wc-input-box', 'placeholder': 'ans'}\n"
            "    expected = n\n"
        )
        result = extract_components_from_builder(source)
        assert "comp" in result.extracted_components
        assert "expected" in result.cleaned_builder

    def test_all_consecutive_components_extracted(self):
        source = (
            "import random\n"
            "n = random.randint(1, 10)\n"
            "comp_a = {'selector': 'wc-input-box', 'placeholder': 'a'}\n"
            "comp_b = {'selector': 'wc-radio', 'choices': ['x', 'y']}\n"
            "comp_c = {'selector': 'wc-feedback', 'type': 'info', 'content': ''}\n"
            "expected = n * 2\n"
        )
        result = extract_components_from_builder(source)
        assert set(result.extracted_components.keys()) == {"comp_a", "comp_b", "comp_c"}
        assert result.extracted_components["comp_a"]["selector"] == "wc-input-box"
        assert result.extracted_components["comp_b"]["selector"] == "wc-radio"
        assert result.extracted_components["comp_c"]["selector"] == "wc-feedback"
        assert "comp_a" not in result.cleaned_builder
        assert "comp_b" not in result.cleaned_builder
        assert "comp_c" not in result.cleaned_builder
        assert "import random" in result.cleaned_builder
        assert "expected = n * 2" in result.cleaned_builder

    def test_components_interspersed_with_code_all_extracted(self):
        source = (
            "a = 1\n"
            "first = {'selector': 'wc-text-block', 'content': 'Q1'}\n"
            "b = 2\n"
            "second = {'selector': 'wc-input-box', 'placeholder': '?'}\n"
            "c = a + b\n"
            "third = {'selector': 'wc-radio', 'choices': ['yes', 'no']}\n"
        )
        result = extract_components_from_builder(source)
        assert set(result.extracted_components.keys()) == {"first", "second", "third"}
        assert "a = 1" in result.cleaned_builder
        assert "b = 2" in result.cleaned_builder
        assert "c = a + b" in result.cleaned_builder
        assert "first" not in result.cleaned_builder
        assert "second" not in result.cleaned_builder
        assert "third" not in result.cleaned_builder

