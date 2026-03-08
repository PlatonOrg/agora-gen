from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime

class UserRequest(BaseModel):
    id: str = Field(..., description="Identifiant unique de la requête.")
    prompt: str = Field(..., description="Description de l'exercice.")
    additional_context: Optional[str] = None
    expected_template_usage: Literal['yes', 'no']
    expected_component: List[str]

class ClassificationResult(BaseModel):
    use_template: Literal['yes', 'no']
    template_name: Optional[str] = None
    component_name: str
    confidence_score: float

# --- Auth ---
class TokenExchangeRequest(BaseModel):
    platonAccessToken: str
    platonRefreshToken: Optional[str] = None

class AuthInitResponse(BaseModel):
    redirectUrl: str
    state: str

class AuthCallbackRequest(BaseModel):
    state: str
    platonAccessToken: str
    platonRefreshToken: Optional[str] = None

class UserProfile(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    permissions: List[str] = []

# --- Context ---
class CircleNode(BaseModel):
    name: str
    children: Optional[List['CircleNode']] = None

class Topic(BaseModel):
    id: str
    name: str
    description: str

class Component(BaseModel):
    id: str
    name: str
    label: str
    type: Literal['formulaire', 'widget']
    url: Optional[str] = None

# --- Chat ---
class ChatMessage(BaseModel):
    message: str
    attached_documents: Optional[List[str]] = []
    last_exercise_id: Optional[str] = None

class ChatSession(BaseModel):
    id: str
    createdAt: datetime

# --- Exercise ---
class Exercise(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str
    previewUrl: Optional[str] = None
    content: Optional[str] = None
    createdAt: Optional[str] = None

# --- Platon Publish ---
class PublishRequest(BaseModel):
    user_id: str
    exercise_id: str
    metadata: Dict[str, Any]
    files: Optional[List[Any]] = None