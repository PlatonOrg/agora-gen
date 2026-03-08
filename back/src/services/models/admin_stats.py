from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class DailyMetrics(BaseModel):
    date: str
    conversations: int
    published_exercises: int
    failures: int
    avg_response_time_ms: Optional[float]


class SummaryMetrics(BaseModel):
    total_conversations: int
    total_published_exercises: int
    total_failures: int
    avg_response_time_ms: Optional[float]


class AdminStatsResponse(BaseModel):
    summary: SummaryMetrics
    daily: List[DailyMetrics]
    date_from: str
    date_to: str


class LLMOptionEntry(BaseModel):
    """Single provider/model pair available for selection."""
    provider: str
    model: str


class LLMOptionsResponse(BaseModel):
    """All registered provider/model pairs plus the current default."""
    options: List[LLMOptionEntry]
    current_provider: str
    current_model: str


class SetLLMConfigRequest(BaseModel):
    """Payload sent by the admin to switch the active provider/model."""
    provider: str
    model: str


class SetLLMConfigResponse(BaseModel):
    """Confirmation of the applied provider/model change."""
    provider: str
    model: str


# -- Runtime Settings (database-backed) -----------------------------------


class RuntimeSettingEntry(BaseModel):
    """Single tuneable setting with its metadata, sent to the admin UI."""
    key: str
    value: str
    value_type: str
    description: str
    default: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None


class RuntimeSettingsResponse(BaseModel):
    """All admin-tuneable runtime settings."""
    settings: List[RuntimeSettingEntry]


class UpdateRuntimeSettingsRequest(BaseModel):
    """Partial update payload: only keys present are changed."""
    settings: dict[str, str]


class UpdateRuntimeSettingsResponse(BaseModel):
    """Confirmation with the new values after update."""
    updated: dict[str, str]


