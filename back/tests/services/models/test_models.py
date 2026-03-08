"""
Tests for Pydantic models in src.services.models.api and src.services.models.platon.

Covers:
- Field defaults and validation
- GeneratedExercise.from_llm_dict / to_dict round-trip
- SandboxError behaviour
- ExerciseState / PreviewResult construction
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.models.api import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ComponentInstance,
    ConfigVariablesGenerationResult,
    DeleteFilesResponse,
    ExerciseData,
    FileSupportResponse,
    GeneratedExercise,
    LLMResult,
    PlatonDocsQuestionRequest,
    PlatonDocsSource,
    PureExerciseGenerationResult,
    SessionFile,
    SessionFilesResponse,
    TemplateConfig,
    TemplatePreviewRequest,
    TemplateResponse,
    TreeNode,
    UploadFileResponse,
    WorkflowResult,
)
from src.services.models.platon import (
    EvaluateFeedback,
    EvaluateResult,
    ExerciseState,
    PlatonCircleNode,
    PlatonLevel,
    PlatonResource,
    PlatonResponse,
    PlatonTopic,
    PreviewResult,
    SandboxError,
    TemplateBasicInfo,
    TemplateSummary,
)


# ---------------------------------------------------------------------------
# SandboxError
# ---------------------------------------------------------------------------

class TestSandboxError:
    def test_stores_message(self):
        error = SandboxError("something broke")
        assert str(error) == "something broke | Response: {}"

    def test_stores_response_json(self):
        payload = {"code": 500, "detail": "internal error"}
        error = SandboxError("API failed", payload)
        assert error.response_json == payload
        assert "internal error" in str(error)

    def test_empty_response_json_defaults_to_empty_dict(self):
        error = SandboxError("msg")
        assert error.response_json == {}

    def test_is_exception(self):
        with pytest.raises(SandboxError):
            raise SandboxError("raising")


# ---------------------------------------------------------------------------
# ExerciseState
# ---------------------------------------------------------------------------

class TestExerciseState:
    def test_required_session_id(self):
        state = ExerciseState(session_id="abc")
        assert state.session_id == "abc"
        assert state.title is None

    def test_all_fields(self):
        state = ExerciseState(
            session_id="s1",
            title="T",
            statement="S",
            form="<form/>",
            preview_url="https://example.com",
        )
        assert state.title == "T"
        assert state.preview_url == "https://example.com"

    def test_missing_session_id_raises(self):
        with pytest.raises(ValidationError):
            ExerciseState()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# PreviewResult
# ---------------------------------------------------------------------------

class TestPreviewResult:
    def test_construction(self):
        state = ExerciseState(session_id="s1")
        result = PreviewResult(state=state, resource_id="r1")
        assert result.resource_id == "r1"
        assert result.state.session_id == "s1"


# ---------------------------------------------------------------------------
# GeneratedExercise
# ---------------------------------------------------------------------------

class TestGeneratedExercise:
    def test_from_llm_dict_known_fields(self):
        data = {
            "name": "N",
            "description": "D",
            "title": "T",
            "statement": "S",
            "form": "F",
            "solution": "Sol",
            "sandbox": "python",
            "builder": "B",
            "grader": "G",
            "hint": ["h1"],
            "theories": [{"title": "Theory", "url": "http://t.com"}],
            "metadata": {
                "levels": ["6e", "Difficile"],
                "topics": ["Fractions", "Mathématiques"],
                "objectifs_pedagogiques": "OP",
                "public_vise": "PV",
                "prerequis": "PR",
                "consignes": "CO",
            },
        }
        ex = GeneratedExercise.from_llm_dict(data)
        assert ex.name == "N"
        assert ex.sandbox == "python"
        assert ex.hint == ["h1"]
        assert ex.levels == ["6e", "Difficile"]
        assert ex.topics == ["Fractions", "Mathématiques"]
        assert ex.objectifs_pedagogiques == "OP"
        assert ex.public_vise == "PV"
        assert ex.prerequis == "PR"
        assert ex.consignes == "CO"
        assert ex.extra_fields == {}

    def test_from_llm_dict_extra_fields(self):
        data = {
            "name": "N",
            "metadata": {"levels": ["6e"], "topics": ["Fractions"]},
            "custom_var": "cv",
            "another": 42,
        }
        ex = GeneratedExercise.from_llm_dict(data)
        assert ex.extra_fields == {"custom_var": "cv", "another": 42}
        assert ex.name == "N"
        assert ex.levels == ["6e"]
        assert ex.topics == ["Fractions"]

    def test_to_dict_excludes_none(self):
        ex = GeneratedExercise(name="N", title="T")
        result = ex.to_dict()
        assert "name" in result
        assert "title" in result
        assert "statement" not in result

    def test_to_dict_includes_extra_fields(self):
        ex = GeneratedExercise(name="N", extra_fields={"my_key": "val"})
        result = ex.to_dict()
        assert result["my_key"] == "val"

    def test_to_dict_hint_included_when_set(self):
        ex = GeneratedExercise(hint=["clue1", "clue2"])
        result = ex.to_dict()
        assert result["hint"] == ["clue1", "clue2"]

    def test_round_trip(self):
        data = {
            "name": "Ex",
            "description": "Desc",
            "title": "Title",
            "statement": "Stmt",
            "form": "<f/>",
            "solution": "42",
            "sandbox": "node",
            "builder": "b()",
            "grader": "g()",
            "hint": ["tip"],
            "theories": [],
            "metadata": {
                "levels": ["6e"],
                "topics": ["Fractions"],
            },
        }
        ex = GeneratedExercise.from_llm_dict(data)
        result = ex.to_dict()
        for key in data:
            assert result[key] == data[key]

    def test_from_llm_dict_missing_all_fields(self):
        ex = GeneratedExercise.from_llm_dict({})
        assert ex.name is None
        assert ex.extra_fields == {}


# ---------------------------------------------------------------------------
# ExerciseData
# ---------------------------------------------------------------------------

class TestExerciseData:
    def test_defaults(self):
        ex = ExerciseData()
        assert ex.indications == []
        assert ex.theories == []
        assert ex.components == []
        assert ex.component_instances == []
        assert ex.config_variables == {}
        assert ex.sandbox_variables == {}
        assert ex.metadata.levels == []
        assert ex.metadata.topics == []
        assert ex.metadata.readme is None

    def test_full_construction(self):
        ex = ExerciseData(
            titre="T",
            enonce="<p>E</p>",
            forme="<form/>",
            solution="42",
            sandbox="python",
            construction="def b(): pass",
            evaluation="def g(): pass",
            template_id="tpl-1",
            exercise_id="ex-1",
        )
        assert ex.titre == "T"
        assert ex.template_id == "tpl-1"

    def test_empty_strings_normalized_to_none(self):
        """Empty strings from the frontend defaults must be treated as None
        so that truthiness checks in from_json_to_ple behave correctly."""
        ex = ExerciseData(
            name="", description="", titre="", enonce="",
            forme="", solution="", construction="", evaluation="",
            template_id="", exercise_id="",
        )
        assert ex.name is None
        assert ex.description is None
        assert ex.titre is None
        assert ex.enonce is None
        assert ex.forme is None
        assert ex.solution is None
        assert ex.construction is None
        assert ex.evaluation is None
        assert ex.template_id is None
        assert ex.exercise_id is None

    def test_whitespace_only_strings_normalized_to_none(self):
        ex = ExerciseData(titre="   ", enonce="  \n  ")
        assert ex.titre is None
        assert ex.enonce is None

    def test_nonempty_strings_preserved(self):
        ex = ExerciseData(titre="Mon titre", enonce="<p>Texte</p>")
        assert ex.titre == "Mon titre"
        assert ex.enonce == "<p>Texte</p>"

    def test_sandbox_empty_string_preserved(self):
        """sandbox is not in _OPTIONAL_STR_FIELDS and should keep empty strings."""
        ex = ExerciseData(sandbox="")
        assert ex.sandbox == ""

    def test_empty_readme_normalized_to_none(self):
        ex = ExerciseData(metadata={"levels": [], "topics": [], "readme": ""})
        assert ex.metadata.readme is None

    def test_nonempty_readme_preserved(self):
        ex = ExerciseData(metadata={"levels": [], "topics": [], "readme": "# Hello"})
        assert ex.metadata.readme == "# Hello"


# ---------------------------------------------------------------------------
# ComponentInstance
# ---------------------------------------------------------------------------

class TestComponentInstance:
    def test_construction(self):
        ci = ComponentInstance(
            id="inst-abc",
            selector="wc-quiz",
            componentName="Quiz",
            instanceName="q1",
            category="Widget",
            properties={"question": "What?"},
        )
        assert ci.id == "inst-abc"
        assert ci.selector == "wc-quiz"
        assert ci.properties["question"] == "What?"


# ---------------------------------------------------------------------------
# ChatRequest / ChatMessage / ChatResponse
# ---------------------------------------------------------------------------

class TestChatRequest:
    def test_minimal_construction(self):
        req = ChatRequest(
            exercise_state=ExerciseData(),
            user_request="make an exercise",
            user_selected_components=[],
        )
        assert req.user_request == "make an exercise"
        assert req.conversation_history == []
        assert req.fields_to_modify == []

    def test_with_history(self):
        msg = ChatMessage(role="user", content="hello")
        req = ChatRequest(
            exercise_state=ExerciseData(),
            user_request="req",
            user_selected_components=[],
            conversation_history=[msg],
        )
        assert len(req.conversation_history) == 1


class TestChatResponse:
    def test_all_none_defaults(self):
        resp = ChatResponse()
        assert resp.exercise_data is None
        assert resp.error is None
        assert resp.url is None

    def test_with_error(self):
        resp = ChatResponse(error="Something went wrong")
        assert resp.error == "Something went wrong"


# ---------------------------------------------------------------------------
# WorkflowResult
# ---------------------------------------------------------------------------

class TestWorkflowResult:
    def test_construction(self):
        ex = ExerciseData()
        result = WorkflowResult(
            exercise_data=ex,
            url="https://preview.example",
            message="Done",
        )
        assert result.url == "https://preview.example"
        assert result.error is None


# ---------------------------------------------------------------------------
# LLMResult
# ---------------------------------------------------------------------------

class TestLLMResult:
    def test_construction(self):
        r = LLMResult(parsed={"key": "val"}, provider="groq", model="llama3")
        assert r.provider == "groq"
        assert r.parsed["key"] == "val"


# ---------------------------------------------------------------------------
# PlatonDocsQuestionRequest
# ---------------------------------------------------------------------------

class TestPlatonDocsQuestionRequest:
    def test_default_top_k(self):
        req = PlatonDocsQuestionRequest(question="What is PLE?")
        assert req.top_k == 10

    def test_top_k_validation_lower_bound(self):
        with pytest.raises(ValidationError):
            PlatonDocsQuestionRequest(question="Q", top_k=0)

    def test_top_k_validation_upper_bound(self):
        with pytest.raises(ValidationError):
            PlatonDocsQuestionRequest(question="Q", top_k=11)

    def test_valid_top_k(self):
        req = PlatonDocsQuestionRequest(question="Q", top_k=5)
        assert req.top_k == 5


# ---------------------------------------------------------------------------
# TemplateResponse
# ---------------------------------------------------------------------------

class TestTemplateResponse:
    def test_construction(self):
        resp = TemplateResponse(
            id="t1",
            name="Template A",
            description="Desc",
            components=["tag-quiz"],
        )
        assert resp.id == "t1"
        assert resp.component_instances == []
        assert resp.config_variables == {}


# ---------------------------------------------------------------------------
# TreeNode (recursive model)
# ---------------------------------------------------------------------------

class TestTreeNode:
    def test_leaf_node(self):
        node = TreeNode(name="Leaf")
        assert node.children == []

    def test_nested(self):
        child = TreeNode(name="Child")
        parent = TreeNode(name="Parent", children=[child])
        assert parent.children[0].name == "Child"


# ---------------------------------------------------------------------------
# PlatonResource
# ---------------------------------------------------------------------------

class TestPlatonResource:
    def test_defaults(self):
        r = PlatonResource(id="1", name="R")
        assert r.extra == {}
        assert r.desc is None

    def test_full(self):
        r = PlatonResource(id="1", name="R", desc="D", type="EXERCISE", status="READY")
        assert r.status == "READY"


# ---------------------------------------------------------------------------
# TemplateSummary / TemplateBasicInfo
# ---------------------------------------------------------------------------

class TestTemplateSummary:
    def test_defaults(self):
        ts = TemplateSummary(platon_id="pid")
        assert ts.internal_id is None
        assert ts.variables is None


class TestTemplateBasicInfo:
    def test_construction(self):
        info = TemplateBasicInfo(title="T", description="D", main_plc_content={"inputs": []})
        assert info.title == "T"


# ---------------------------------------------------------------------------
# FileSupportResponse / SessionFile / UploadFileResponse / DeleteFilesResponse
# ---------------------------------------------------------------------------

class TestFileModels:
    def test_file_support(self):
        r = FileSupportResponse(supported=True, max_files=5, accepted_extensions=[])
        assert r.supported is True

    def test_file_support_with_extensions(self):
        r = FileSupportResponse(supported=True, max_files=3, accepted_extensions=[".pdf", ".txt"])
        assert ".pdf" in r.accepted_extensions

    def test_session_file(self):
        sf = SessionFile(file_id="f1", filename="doc.pdf")
        assert sf.file_id == "f1"

    def test_upload_response(self):
        r = UploadFileResponse(file_id="f1", filename="doc.pdf")
        assert r.filename == "doc.pdf"

    def test_delete_response_defaults(self):
        r = DeleteFilesResponse(deleted=2)
        assert r.failed == []

    def test_session_files_response(self):
        r = SessionFilesResponse(files=[SessionFile(file_id="x", filename="x.pdf")])
        assert len(r.files) == 1

