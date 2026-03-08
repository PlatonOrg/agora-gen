"""
Data models for the vector embedding pipeline.

These are internal transfer objects used exclusively within the embedding
infrastructure and are not exposed through the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID


@dataclass
class ExerciseMetadata:
    db_id: UUID
    platon_id: str
    name: str
    cercle: str
    description: Optional[str] = None
    topics: Optional[List[str]] = None
    levels: Optional[List[str]] = None


@dataclass
class TemplateParameter:
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    default_value: Optional[str] = None


@dataclass
class FilledTemplateParameter:
    """
    A template parameter enriched with the concrete value it was given in a
    specific template_exo instance (read from ``main.plo``).
    """
    name: str
    filled_value: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None


@dataclass
class ExerciseParts:
    title: str
    statement: str
    form: str
    solution: Optional[str] = None
    components: Optional[List[str]] = None


@dataclass
class ExerciseResource:
    metadata: ExerciseMetadata
    parts: ExerciseParts


@dataclass
class TemplateResource:
    metadata: ExerciseMetadata
    parts: ExerciseParts
    parameters_content: List[TemplateParameter] = field(default_factory=list)
    is_configurable: bool = True

