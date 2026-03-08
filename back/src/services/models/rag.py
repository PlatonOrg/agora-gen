from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.api.v1.schemas import UserRequest, ClassificationResult


@dataclass
class RetrievedChunk:
    doc_type: str
    name: str | None
    score: float | None
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
