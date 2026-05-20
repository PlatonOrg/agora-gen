from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class PromptEntry(BaseModel):
    id: str
    name: str
    content: str
    created_at: Optional[str]
    updated_at: Optional[str]


class PromptUpdateRequest(BaseModel):
    content: Optional[str] = None


class LlmCallRecord(BaseModel):
    call_type: str
    provider: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    system_prompt_chars: Optional[int] = None
    user_prompt_chars: Optional[int] = None


class ConversationSummary(BaseModel):
    conversation_id: str
    session_id: Optional[str]
    username: Optional[str]
    exo_generation_count: int
    discussion_generation_count: int
    total_generation_count: int
    started_at: Optional[str]
    last_at: Optional[str]


class SessionSummary(BaseModel):
    session_id: str
    exo_generation_count: int
    discussion_generation_count: int
    total_generation_count: int
    started_at: Optional[str]
    last_at: Optional[str]


class RagSearchResult(BaseModel):
    rank: int
    platon_id: Optional[str]
    resource_name: Optional[str]
    kind: Optional[str]
    score: Optional[float]


class RagSearchInfo(BaseModel):
    query: str
    embedding_model: str
    vector_table: str
    created_at: Optional[str]
    results: List[RagSearchResult]


class DocChunkResult(BaseModel):
    rank: int
    chunk_text: Optional[str]
    source_path: Optional[str]
    score: Optional[float]


class DocRagSearchInfo(BaseModel):
    query: str
    embedding_model: str
    vector_table: str
    created_at: Optional[str]
    chunks: List[DocChunkResult]


class ComponentLink(BaseModel):
    component_tag: str


class FileSummaryEntry(BaseModel):
    filename: str
    text_excerpt: Optional[str]
    summary: Optional[str]


class ExoRequestInfo(BaseModel):
    id: str
    user_request: str
    session_id: Optional[str]
    fields_to_modify: Optional[List[str]]
    variables: Optional[Dict[str, Any]]
    file_names: Optional[List[str]]
    file_summaries: Optional[List[Dict[str, Any]]]
    conversation_history: Optional[List[Any]]
    current_exercise_state: Optional[Dict[str, Any]]
    components: List[str]
    created_at: Optional[str]


class LlmResultInfo(BaseModel):
    system_prompt_name: str
    system_prompt_content: Optional[str]
    examples_used: Optional[List[Any]]
    llm_output: Optional[Dict[str, Any]]
    llm_provider: str
    llm_model: str
    preview_url: Optional[str]
    retry_count: Optional[int]
    retry_errors: Optional[List[str]]
    created_at: Optional[str]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    llm_request_count: Optional[int] = None
    llm_calls: Optional[List[LlmCallRecord]] = None


class ComponentSelectionInfo(BaseModel):
    user_priority_tags: List[str]
    selected_tags: List[str]
    llm_provider: str
    llm_model: str
    reasoning: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    created_at: Optional[str]


class DiscussionLlmResultInfo(BaseModel):
    system_prompt_name: str
    system_prompt_content: Optional[str]
    chunks_used: Optional[List[Any]]
    llm_output: Optional[str]
    llm_provider: str
    llm_model: str
    created_at: Optional[str]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class GenerationStatsEntry(BaseModel):
    kind: str
    embedding_model: str
    llm_provider: str
    llm_model: str
    count: int


class GenerationStats(BaseModel):
    exo: List[GenerationStatsEntry]
    discussion: List[GenerationStatsEntry]


class AppConfig(BaseModel):
    embedding_model: str


class DiscussionRequestInfo(BaseModel):
    id: str
    user_request: str
    session_id: Optional[str]
    created_at: Optional[str]


class ExoGenerationDetail(BaseModel):
    id: str
    kind: str
    created_at: Optional[str]
    status: Optional[str] = None
    username: Optional[str] = None
    request: Optional[ExoRequestInfo]
    rag_search: Optional[RagSearchInfo]
    llm_result: Optional[LlmResultInfo]
    component_selection: Optional[ComponentSelectionInfo] = None


class DiscussionGenerationDetail(BaseModel):
    id: str
    kind: str
    created_at: Optional[str]
    status: Optional[str] = None
    username: Optional[str] = None
    request: Optional[DiscussionRequestInfo]
    rag_search: Optional[DocRagSearchInfo]
    llm_result: Optional[DiscussionLlmResultInfo]


class ConversationDetail(BaseModel):
    conversation_id: str
    session_id: Optional[str]
    username: Optional[str]
    started_at: Optional[str]
    last_at: Optional[str]
    exo_generations: List[ExoGenerationDetail]
    discussion_generations: List[DiscussionGenerationDetail]


class SessionDetail(BaseModel):
    session_id: str
    started_at: Optional[str]
    last_at: Optional[str]
    exo_generations: List[ExoGenerationDetail]
    discussion_generations: List[DiscussionGenerationDetail]

