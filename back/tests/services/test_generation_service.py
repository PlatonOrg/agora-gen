"""
Tests for src.services.generation_service.GenerationService.

Covers:
- _format_schema_for_prompt
- _format_conversation_history (empty, user messages, ChatMessage models and dicts)
- _format_current_exercise_state (pure and config modes, empty state)
- _format_components_for_prompt
- generate_config_variables (schema filtering by fields_to_modify, LLM result handling)
- generate_pure_exercise_with_examples (field construction, file_ids passthrough)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from src.services.generation_service import GenerationService
from src.services.models.api import (
    ChatMessage,
    ExerciseData,
    GeneratedExercise,
    LLMResult,
    ConfigVariablesGenerationResult,
    PureExerciseGenerationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DUMMY_PROMPT = "You are an expert exercise creator."
DUMMY_SCHEMA = [
    {"name": "question", "type": "text", "description": "The question", "value": ""},
    {"name": "difficulty", "type": "select", "description": "Difficulty level", "value": "easy",
     "options": {"choices": ["easy", "medium", "hard"]}},
]

DUMMY_METADATA = [
    {
        "tag": "tag-quiz",
        "name": "Quiz",
        "category": "Widget",
        "description": "A quiz widget",
        "usage": "For MCQ",
        "properties": {"question": {"type": "string"}},
    }
]


def _make_service() -> GenerationService:
    return GenerationService(None)


def _make_exercise(**kwargs) -> ExerciseData:
    return ExerciseData(**kwargs)


def _make_llm_result(parsed: dict) -> LLMResult:
    return LLMResult(parsed=parsed, provider="groq", model="llama3")


# ---------------------------------------------------------------------------
# _format_schema_for_prompt
# ---------------------------------------------------------------------------

class TestFormatSchemaForPrompt:
    def setup_method(self):
        self.service = _make_service()

    def test_includes_variable_name(self):
        result = self.service._format_schema_for_prompt(DUMMY_SCHEMA)
        assert "question" in result
        assert "difficulty" in result

    def test_includes_type(self):
        result = self.service._format_schema_for_prompt(DUMMY_SCHEMA)
        assert "text" in result
        assert "select" in result

    def test_includes_description(self):
        result = self.service._format_schema_for_prompt(DUMMY_SCHEMA)
        assert "The question" in result

    def test_skips_non_dict_entries(self):
        result = self.service._format_schema_for_prompt(["not-a-dict"])
        # Should not crash; returns a string (possibly empty)
        assert isinstance(result, str)

    def test_empty_schema_returns_string(self):
        result = self.service._format_schema_for_prompt([])
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _format_conversation_history
# ---------------------------------------------------------------------------

class TestFormatConversationHistory:
    def setup_method(self):
        self.service = _make_service()

    def test_empty_history_returns_empty_string(self):
        result = self.service._format_conversation_history([])
        assert result == ""

    def test_none_history_returns_empty_string(self):
        result = self.service._format_conversation_history(None)
        assert result == ""

    def test_user_message_included(self):
        msg = ChatMessage(role="user", content="Make an exercise about fractions")
        result = self.service._format_conversation_history([msg])
        assert "fractions" in result
        assert "utilisateur" in result.lower()

    def test_user_message_from_dict(self):
        msg = {"role": "user", "content": "Hello from dict", "components": []}
        result = self.service._format_conversation_history([msg])
        assert "Hello from dict" in result

    def test_components_appended_to_message(self):
        msg = ChatMessage(role="user", content="Use components", components=["tag-quiz"])
        result = self.service._format_conversation_history([msg])
        assert "tag-quiz" in result

    def test_non_user_messages_are_handled(self):
        msg = ChatMessage(role="ai", content="AI response")
        result = self.service._format_conversation_history([msg])
        # Should not crash; AI messages may or may not appear
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _format_current_exercise_state
# ---------------------------------------------------------------------------

class TestFormatCurrentExerciseState:
    def setup_method(self):
        self.service = _make_service()

    def test_empty_exercise_returns_empty_string(self):
        ex = ExerciseData()
        result = self.service._format_current_exercise_state(ex, for_pure=True)
        assert result == ""

    def test_titre_included_in_pure_mode(self):
        ex = _make_exercise(titre="Fractions")
        result = self.service._format_current_exercise_state(ex, for_pure=True)
        assert "Fractions" in result

    def test_enonce_included_in_pure_mode(self):
        ex = _make_exercise(enonce="Solve for x.")
        result = self.service._format_current_exercise_state(ex, for_pure=True)
        assert "Solve for x." in result

    def test_config_variables_included_in_config_mode(self):
        ex = _make_exercise(config_variables={"inputs": [{"name": "q", "value": "v"}]})
        result = self.service._format_current_exercise_state(ex, for_pure=False)
        assert "inputs" in result

    def test_pure_mode_does_not_include_config_variables(self):
        ex = _make_exercise(config_variables={"inputs": []})
        result = self.service._format_current_exercise_state(ex, for_pure=True)
        # config_variables should not appear in pure mode
        # (the state dict for pure doesn't include them)
        assert "variables de configuration" not in result

    def test_sandbox_variables_included_in_pure_mode(self):
        ex = _make_exercise(sandbox_variables={"my_var": "val"})
        result = self.service._format_current_exercise_state(ex, for_pure=True)
        assert "my_var" in result


# ---------------------------------------------------------------------------
# _format_components_for_prompt
# ---------------------------------------------------------------------------

class TestFormatComponentsForPrompt:
    def setup_method(self):
        self.service = _make_service()

    def test_known_component_tag_included(self):
        with patch.object(self.service, "_load_component_metadata", return_value=DUMMY_METADATA):
            result = self.service._format_components_for_prompt(["tag-quiz"])
        assert "tag-quiz" in result
        assert "Quiz" in result

    def test_unknown_component_tag_excluded(self):
        with patch.object(self.service, "_load_component_metadata", return_value=DUMMY_METADATA):
            result = self.service._format_components_for_prompt(["tag-unknown"])
        assert "tag-unknown" not in result

    def test_empty_component_list(self):
        with patch.object(self.service, "_load_component_metadata", return_value=DUMMY_METADATA):
            result = self.service._format_components_for_prompt([])
        assert result == ""


# ---------------------------------------------------------------------------
# generate_config_variables
# ---------------------------------------------------------------------------

class TestGenerateConfigVariables:
    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_returns_config_variables_result(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"question": "What is 2+2?", "name": "Ex", "description": "Desc"})

        service = _make_service()
        ex = _make_exercise(
            config_variables={"inputs": DUMMY_SCHEMA},
            description="A math template",
        )

        with patch.object(service, "_load_system_prompt", return_value=DUMMY_PROMPT):
            result = await service.generate_config_variables(
                exercise_data=ex,
                user_request="make an exercise about addition",
            )

        assert isinstance(result, ConfigVariablesGenerationResult)
        assert "question" in result.variables

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_name_and_description_extracted_from_llm_result(self, mock_llm):
        mock_llm.return_value = _make_llm_result({
            "question": "Q?",
            "name": "Exercise Name",
            "description": "Exercise Desc",
        })

        service = _make_service()
        ex = _make_exercise(config_variables={"inputs": DUMMY_SCHEMA})

        with patch.object(service, "_load_system_prompt", return_value=DUMMY_PROMPT):
            result = await service.generate_config_variables(
                exercise_data=ex,
                user_request="create",
            )

        assert ex.name == "Exercise Name"
        assert ex.description == "Exercise Desc"
        assert "name" not in result.variables
        assert "description" not in result.variables

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_fields_to_modify_sets_include_properties(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"question": "Q?"})

        service = _make_service()
        ex = _make_exercise(config_variables={"inputs": DUMMY_SCHEMA})

        with patch.object(service, "_load_system_prompt", return_value=DUMMY_PROMPT):
            await service.generate_config_variables(
                exercise_data=ex,
                user_request="modify question only",
                fields_to_modify=["question"],
            )

        call_kwargs = mock_llm.call_args[1]
        # The service uses include_properties to filter the JSON schema at the LLM level
        include_props = call_kwargs.get("include_properties")
        assert include_props == ["question"]

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_llm_result_provider_and_model_preserved(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"question": "Q?"})

        service = _make_service()
        ex = _make_exercise(config_variables={"inputs": DUMMY_SCHEMA})

        with patch.object(service, "_load_system_prompt", return_value=DUMMY_PROMPT):
            result = await service.generate_config_variables(
                exercise_data=ex,
                user_request="create",
            )

        assert result.llm.provider == "groq"
        assert result.llm.model == "llama3"


# ---------------------------------------------------------------------------
# generate_pure_exercise_with_examples
# ---------------------------------------------------------------------------

class TestGeneratePureExerciseWithExamples:
    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_returns_pure_exercise_result(self, mock_llm):
        mock_llm.return_value = _make_llm_result({
            "name": "N",
            "description": "D",
            "title": "T",
            "statement": "S",
            "form": "<f/>",
            "solution": "42",
            "sandbox": "python",
            "builder": "def b(): pass",
            "grader": "def g(): pass",
        })

        service = _make_service()
        with patch.object(service, "_load_pure_exercise_prompt", return_value=DUMMY_PROMPT):
            with patch.object(service, "_load_component_metadata", return_value=DUMMY_METADATA):
                result = await service.generate_pure_exercise_with_examples(
                    exercise_data=_make_exercise(),
                    user_request="make an exercise about fractions",
                    examples=[{"title": "Example", "statement": "Do X"}],
                )

        assert isinstance(result, PureExerciseGenerationResult)
        assert result.generated_exercise.name == "N"

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_file_ids_passed_to_llm(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"name": "N"})

        service = _make_service()
        with patch.object(service, "_load_pure_exercise_prompt", return_value=DUMMY_PROMPT):
            with patch.object(service, "_load_component_metadata", return_value=[]):
                await service.generate_pure_exercise_with_examples(
                    exercise_data=_make_exercise(),
                    user_request="create",
                    examples=[],
                    file_ids=["file-id-1", "file-id-2"],
                )

        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs.get("file_ids") == ["file-id-1", "file-id-2"]

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_fields_to_modify_appended_to_prompt(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"name": "N"})

        service = _make_service()
        with patch.object(service, "_load_pure_exercise_prompt", return_value=DUMMY_PROMPT):
            with patch.object(service, "_load_component_metadata", return_value=[]):
                await service.generate_pure_exercise_with_examples(
                    exercise_data=_make_exercise(),
                    user_request="create",
                    examples=[],
                    fields_to_modify=["statement", "solution"],
                )

        call_kwargs = mock_llm.call_args[1]
        include_props = call_kwargs.get("include_properties")
        assert include_props == ["statement", "solution"]

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_no_fields_to_modify_passes_none_to_llm(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"name": "N"})

        service = _make_service()
        with patch.object(service, "_load_pure_exercise_prompt", return_value=DUMMY_PROMPT):
            with patch.object(service, "_load_component_metadata", return_value=[]):
                await service.generate_pure_exercise_with_examples(
                    exercise_data=_make_exercise(),
                    user_request="create",
                    examples=[],
                    fields_to_modify=[],
                )

        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs.get("include_properties") is None

    @pytest.mark.asyncio
    @patch("src.services.generation_service.chat_with_llm", new_callable=AsyncMock)
    async def test_examples_appear_in_prompt(self, mock_llm):
        mock_llm.return_value = _make_llm_result({"name": "N"})
        example = {"title": "Example Exercise", "statement": "Do X"}

        service = _make_service()
        with patch.object(service, "_load_pure_exercise_prompt", return_value=DUMMY_PROMPT):
            with patch.object(service, "_load_component_metadata", return_value=[]):
                await service.generate_pure_exercise_with_examples(
                    exercise_data=_make_exercise(),
                    user_request="create",
                    examples=[example],
                )

        # The system_prompt sent to LLM should contain the example data
        call_kwargs = mock_llm.call_args[1]
        system_prompt = call_kwargs.get("system_prompt", "")
        assert "Example Exercise" in system_prompt or "Do X" in system_prompt

