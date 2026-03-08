from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class SandboxError(Exception):
    """Custom exception for Platon API errors."""

    def __init__(self, message: str, response_json: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.response_json = response_json or {}

    def __str__(self) -> str:
        return f"{super().__str__()} | Response: {self.response_json}"


class PlatonLogEntry(BaseModel):
    """A single log entry returned by the Platon sandbox after a preview evaluation."""

    message: str
    type: str  # "error" | "warning" | "log"


class SandboxRuntimeError(Exception):
    """
    Raised when a Platon preview succeeds at the HTTP level (200 OK) but
    the sandbox reported runtime errors inside ``platon_logs``.

    This is distinct from :class:`SandboxError` which represents HTTP-level
    failures.  Both are caught by the retry handler so the LLM can repair
    the exercise in either case.

    The ``source`` parameter distinguishes where the error originated:
    - ``"builder"`` (default): error in the builder script, detected during preview.
    - ``"grader"``: error in the grader script, detected during evaluate.
    """

    def __init__(self, error_logs: List[PlatonLogEntry], source: str = "builder") -> None:
        self.error_logs = error_logs
        self.source = source
        formatted = "\n".join(
            f"[{entry.type.upper()}] {entry.message}" for entry in error_logs
        )
        prefix = "Grader runtime errors detected" if source == "grader" else "Sandbox runtime errors detected"
        super().__init__(f"{prefix}:\n{formatted}")


class ExerciseState(BaseModel):
    """
    Represents the state of an exercise after evaluation by Platon.
    Converted from dataclass to Pydantic for FastAPI compatibility.
    """

    session_id: str = Field(..., description="Unique session ID for the exercise run.")
    title: Optional[str] = None
    statement: Optional[str] = None
    form: Optional[str] = None
    preview_url: Optional[str] = None
    platon_logs: List[PlatonLogEntry] = Field(
        default_factory=list,
        description="Raw log entries returned by the Platon sandbox during preview.",
    )

    @property
    def runtime_error_logs(self) -> List[PlatonLogEntry]:
        """Return only the log entries whose type is 'error'."""
        return [entry for entry in self.platon_logs if entry.type == "error"]

    @property
    def has_runtime_errors(self) -> bool:
        """True when the sandbox reported at least one error-level log entry."""
        return bool(self.runtime_error_logs)


class PreviewResult(BaseModel):
    state: ExerciseState
    resource_id: str

class EvaluateFeedback(BaseModel):
    content: str
    type: str

class EvaluateResult(BaseModel):
    session_id: str
    title: Optional[str] = None
    form: Optional[str] = None
    feedbacks: List[EvaluateFeedback] = Field(default_factory=list)
    platon_logs: List[PlatonLogEntry] = Field(default_factory=list)

    @property
    def runtime_error_logs(self) -> List[PlatonLogEntry]:
        return [entry for entry in self.platon_logs if entry.type == "error"]

    @property
    def has_runtime_errors(self) -> bool:
        return bool(self.runtime_error_logs)

class PlatonResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class PlatonResource(BaseModel):
    id: str
    name: str
    desc: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    configurable: Optional[bool] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

class PlatonCircleNode(BaseModel):
    id: str
    name: str
    full_path: str
    parent_id: Optional[str] = None
    has_children: bool = False

class PlatonTopic(BaseModel):
    id: str
    name: str
    description: str

class PlatonLevel(BaseModel):
    id: str
    name: str
    description: str

class TemplateSummary(BaseModel):
    platon_id: str
    internal_id: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None

class TemplateBasicInfo(BaseModel):
    title: str
    description: str
    main_plc_content: Dict[str, Any]

class PublishFile(BaseModel):
    path: str
    content: str

class PublishExerciseRequest(BaseModel):
    name: str
    parentId: str
    templateId: Optional[str] = None
    templateVersion: Optional[str] = None
    code: Optional[str] = None
    desc: str
    type: str = "EXERCISE"
    status: str
    levels: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    files: List[PublishFile] = Field(default_factory=list)

class PublishExerciseResponse(BaseModel):
    id: str

class CirclePermissions(BaseModel):
    read: bool = False
    write: bool = False
    watcher: bool = False
    member: bool = False
    waiting: bool = False

class CircleNode(BaseModel):
    id: str
    name: str
    code: str = ""
    versions: List[str] = Field(default_factory=list)
    permissions: CirclePermissions = Field(default_factory=CirclePermissions)
    children: List['CircleNode'] = Field(default_factory=list)

CircleNode.model_rebuild()


class PlatonUser(BaseModel):
    id: str
    username: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    hasPassword: Optional[bool] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    lastLogin: Optional[str] = None
    firstLogin: Optional[str] = None
    lastActivity: Optional[str] = None
    discordId: Optional[str] = None

