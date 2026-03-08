from __future__ import annotations

import pytest

from src.services.grader_feedback_fixer import fix_feedback_message_property


class TestFixFeedbackMessageProperty:

    def test_empty_source_unchanged(self):
        assert fix_feedback_message_property("") == ""

    def test_whitespace_only_unchanged(self):
        src = "   \n  "
        assert fix_feedback_message_property(src) == src

    def test_no_feedback_message_unchanged(self):
        src = "feedback['content'] = 'ok'\nresult = feedback['score']\n"
        assert fix_feedback_message_property(src) == src

    def test_single_quote_replaced(self):
        src = "feedback['message'] = 'Bravo'\n"
        result = fix_feedback_message_property(src)
        assert "feedback['content']" in result
        assert "feedback['message']" not in result

    def test_double_quote_replaced(self):
        src = 'feedback["message"] = "Correct"\n'
        result = fix_feedback_message_property(src)
        assert 'feedback["content"]' in result
        assert 'feedback["message"]' not in result

    def test_read_access_replaced(self):
        src = "msg = feedback['message']\n"
        result = fix_feedback_message_property(src)
        assert "feedback['content']" in result
        assert "feedback['message']" not in result

    def test_multiple_occurrences_all_replaced(self):
        src = (
            "feedback['message'] = 'Bravo'\n"
            "x = feedback['score']\n"
            'if feedback["message"]:\n'
            "    pass\n"
        )
        result = fix_feedback_message_property(src)
        assert "feedback['message']" not in result
        assert 'feedback["message"]' not in result
        assert result.count("content") == 2
        assert "feedback['score']" in result

    def test_other_variable_named_message_not_replaced(self):
        src = "other['message'] = 'hello'\nfeedback['message'] = 'ok'\n"
        result = fix_feedback_message_property(src)
        assert "other['message']" in result
        assert "feedback['content']" in result
        assert "feedback['message']" not in result

    def test_string_literal_containing_pattern_not_replaced(self):
        src = "x = \"feedback['message']\"\nfeedback['message'] = 'real'\n"
        result = fix_feedback_message_property(src)
        assert result.count("content") == 1
        assert "\"feedback['message']\"" in result

    def test_syntax_error_returns_original_unchanged(self):
        src = "def broken(:\n    feedback['message'] = 'x'\n"
        assert fix_feedback_message_property(src) == src

    def test_no_message_key_present_early_exit(self):
        src = "feedback['score'] = 1\nfeedback['content'] = 'ok'\n"
        result = fix_feedback_message_property(src)
        assert result == src

    def test_realistic_grader_snippet(self):
        src = (
            "expected = nb_questions\n"
            "score = sum(1 for a, b in zip(answers, correct) if a == b)\n"
            "feedback['score'] = score\n"
            "feedback['max_score'] = expected\n"
            "feedback['message'] = 'Correct !' if score == expected else f'{score}/{expected}'\n"
        )
        result = fix_feedback_message_property(src)
        assert "feedback['content']" in result
        assert "feedback['message']" not in result
        assert "feedback['score']" in result
        assert "feedback['max_score']" in result

    def test_quote_style_preserved_single(self):
        src = "feedback['message'] = 'ok'\n"
        result = fix_feedback_message_property(src)
        assert "'content'" in result

    def test_quote_style_preserved_double(self):
        src = 'feedback["message"] = "ok"\n'
        result = fix_feedback_message_property(src)
        assert '"content"' in result

    def test_result_is_valid_python(self):
        src = (
            "feedback['score'] = 1\n"
            "feedback['message'] = 'Good'\n"
            'feedback["message"] = "Also good"\n'
        )
        result = fix_feedback_message_property(src)
        try:
            compile(result, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Result is not valid Python: {exc}")

