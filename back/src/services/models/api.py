from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator

class ComponentInstance(BaseModel):
    id: str
    selector: str
    componentName: str
    instanceName: str
    category: str
    properties: Dict[str, Any]

    @field_validator("instanceName", mode="before")
    @classmethod
    def _normalize_instance_name(cls, value: str) -> str:
        return value.replace("-", "_")

class FilterTemplatesRequest(BaseModel):
    cercle: str
    sujets: List[str]
    niveaux: List[str]
    composants: List[str] = Field(default_factory=list)
    search: Optional[str] = None

class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    config_variables: Dict[str, Any] = Field(default_factory=dict)
    compil_variables: Dict[str, Any] = Field(default_factory=dict)
    components: List[str]
    component_instances: List[ComponentInstance] = Field(default_factory=list)
    levels: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)

class TemplatePreviewRequest(BaseModel):
    template_id: str
    variables: Dict[str, Any]


class ExerciseMetadata(BaseModel):
    levels: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    readme: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_readme(cls, values: Any) -> Any:
        """Treat blank readme strings as absent."""
        if isinstance(values, dict):
            readme_value = values.get("readme")
            if isinstance(readme_value, str) and not readme_value.strip():
                values["readme"] = None
        return values


_EXERCISE_OPTIONAL_STR_FIELDS = frozenset({
    "name", "description", "titre", "enonce", "forme", "solution",
    "construction", "evaluation", "template_id", "exercise_id",
})


class ExerciseData(BaseModel):
    """Canonical representation of an exercise being edited in the workspace."""

    name: Optional[str] = None
    description: Optional[str] = None
    titre: Optional[str] = None
    enonce: Optional[str] = None
    forme: Optional[str] = None
    solution: Optional[str] = None
    indications: List[str] = Field(default_factory=list)
    theories: List[Dict[str, str]] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    component_instances: List[ComponentInstance] = Field(default_factory=list)
    sandbox: Optional[str] = None
    construction: Optional[str] = None
    evaluation: Optional[str] = None
    template_id: Optional[str] = None
    exercise_id: Optional[str] = None
    config_variables: Dict[str, Any] = Field(default_factory=dict)
    sandbox_variables: Dict[str, Any] = Field(default_factory=dict)
    metadata: ExerciseMetadata = Field(default_factory=ExerciseMetadata)

    @model_validator(mode="before")
    @classmethod
    def _normalize_empty_strings(cls, values: Any) -> Any:
        """Convert blank optional-string fields to None.

        The frontend sends empty strings as defaults for every text field.
        Normalizing them here keeps truthiness checks consistent across the
        entire backend (e.g. ``if exercise_data.titre:``).
        """
        if not isinstance(values, dict):
            return values

        for field_name in _EXERCISE_OPTIONAL_STR_FIELDS:
            value = values.get(field_name)
            if isinstance(value, str) and not value.strip():
                values[field_name] = None

        return values

class ChatMessage(BaseModel):
    role: str  # 'user', 'ai', or 'system'
    content: str
    components: List[str] = Field(default_factory=list)

class ChatRequest(BaseModel):
    exercise_state: ExerciseData
    user_request: str
    user_selected_components: List[str]
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    fields_to_modify: List[str] = Field(default_factory=list)
    llm_model: Optional[str] = None
    file_ids: List[str] = Field(default_factory=list)
    file_contents: List[str] = Field(default_factory=list)
    file_infos: List[Dict[str, Any]] = Field(default_factory=list)
    conversation_mode: Optional[str] = None
    force_pure_exercise: bool = False
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    exercise_data: Optional[ExerciseData] = None
    url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    retry_count: Optional[int] = None
    retry_errors: Optional[List[str]] = None
    conversation_mode: Optional[str] = None


class GeneratedExercise(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    title: Optional[str] = None
    statement: Optional[str] = None
    form: Optional[str] = None
    solution: Optional[str] = None
    sandbox: Optional[str] = None
    builder: Optional[str] = None
    grader: Optional[str] = None
    hint: Optional[List[str]] = None
    theories: Optional[List[Dict[str, str]]] = None
    levels: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    objectifs_pedagogiques: Optional[str] = None
    public_vise: Optional[str] = None
    prerequis: Optional[str] = None
    consignes: Optional[str] = None
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_llm_dict(cls, data: Dict[str, Any]) -> "GeneratedExercise":
        known = {"name", "description", "title", "statement", "form", "solution", "sandbox", "builder", "grader", "hint", "theories", "metadata"}
        extra = {k: v for k, v in data.items() if k not in known}
        metadata = data.get("metadata") or {}
        return cls(
            name=data.get("name"),
            description=data.get("description"),
            title=data.get("title"),
            statement=data.get("statement"),
            form=data.get("form"),
            solution=data.get("solution"),
            sandbox=data.get("sandbox"),
            builder=data.get("builder"),
            grader=data.get("grader"),
            hint=data.get("hint"),
            theories=data.get("theories"),
            levels=metadata.get("levels"),
            topics=metadata.get("topics"),
            objectifs_pedagogiques=metadata.get("objectifs_pedagogiques"),
            public_vise=metadata.get("public_vise"),
            prerequis=metadata.get("prerequis"),
            consignes=metadata.get("consignes"),
            extra_fields=extra,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.name is not None:
            result["name"] = self.name
        if self.description is not None:
            result["description"] = self.description
        if self.title is not None:
            result["title"] = self.title
        if self.statement is not None:
            result["statement"] = self.statement
        if self.form is not None:
            result["form"] = self.form
        if self.solution is not None:
            result["solution"] = self.solution
        if self.sandbox is not None:
            result["sandbox"] = self.sandbox
        if self.builder is not None:
            result["builder"] = self.builder
        if self.grader is not None:
            result["grader"] = self.grader
        if self.hint is not None:
            result["hint"] = self.hint
        if self.theories is not None:
            result["theories"] = self.theories
        metadata: Dict[str, Any] = {}
        if self.levels is not None:
            metadata["levels"] = self.levels
        if self.topics is not None:
            metadata["topics"] = self.topics
        if self.objectifs_pedagogiques is not None:
            metadata["objectifs_pedagogiques"] = self.objectifs_pedagogiques
        if self.public_vise is not None:
            metadata["public_vise"] = self.public_vise
        if self.prerequis is not None:
            metadata["prerequis"] = self.prerequis
        if self.consignes is not None:
            metadata["consignes"] = self.consignes
        if metadata:
            result["metadata"] = metadata
        result.update(self.extra_fields)
        return result


class LLMResult(BaseModel):
    parsed: Dict[str, Any]
    provider: str
    model: str
    raw_text: str = ""
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    request_count: int = 1


class LLMTextResult(BaseModel):
    text: str
    raw_text: str
    provider: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class PureExerciseGenerationResult(BaseModel):
    generated_exercise: "GeneratedExercise"
    llm: LLMResult


class ConfigVariablesGenerationResult(BaseModel):
    variables: Dict[str, Any]
    llm: LLMResult


class SessionFile(BaseModel):
    file_id: str
    filename: str


class FileInfo(BaseModel):
    file_id: str
    filename: str
    text_excerpt: Optional[str] = None
    summary: Optional[str] = None


class WorkflowResult(BaseModel):
    exercise_data: ExerciseData
    url: str
    message: str
    retry_count: Optional[int] = None
    retry_errors: Optional[List[str]] = None
    error: Optional[str] = None


class PlatonDocsQuestionRequest(BaseModel):
    question: str
    top_k: int = Field(default=10, ge=1, le=10)
    conversation_id: Optional[str] = None


class PlatonDocsSource(BaseModel):
    source_path: str
    chunk_index: int
    score: Optional[float] = None
    excerpt: str


class PlatonDocsQuestionResponse(BaseModel):
    answer: Optional[str] = None
    sources: List[PlatonDocsSource] = Field(default_factory=list)
    error: Optional[str] = None


class TemplateConfig(BaseModel):
    title: str
    description: str
    variables: Dict[str, Any]
    components: List[str]
    compiled_data: Dict[str, Any]


class PreviewUrlResponse(BaseModel):
    preview_url: str


class PleContentResponse(BaseModel):
    ple_content: str


class CircleNode(BaseModel):
    id: str
    name: str
    fullPath: str
    parentId: Optional[str] = None
    hasChildren: bool = False
    writePermission: bool = False


class TreeNode(BaseModel):
    name: str
    children: List["TreeNode"] = Field(default_factory=list)


TreeNode.model_rebuild()


class Topic(BaseModel):
    id: str
    name: str
    description: str


class Level(BaseModel):
    id: str
    name: str
    description: str


class FileSupportResponse(BaseModel):
    supported: bool
    max_files: int
    accepted_extensions: List[str]


class UploadFileResponse(BaseModel):
    file_id: str
    filename: str


class DeleteFilesResponse(BaseModel):
    deleted: int
    failed: List[str] = Field(default_factory=list)


class SessionFilesResponse(BaseModel):
    files: List[SessionFile]




