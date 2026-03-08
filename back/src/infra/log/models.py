from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UUID,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ComponentSelectionLog(BaseModel):
    user_request: str
    user_priority_tags: List[str]
    selected_tags: List[str]
    llm_provider: str
    llm_model: str
    reasoning: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class ExoGenerationLog(BaseModel):
    user_request: str
    components: List[str]
    fields_to_modify: List[str]
    variables: Optional[Dict[str, Any]]
    file_names: List[str]
    file_summaries: List[Dict[str, Any]]
    conversation_history: List[Any]
    current_exercise_state: Optional[Dict[str, Any]]
    retrieved_chunks: List[Any]
    embedding_model: str
    vector_table: str
    rag_query: str
    examples_used: List[Dict[str, Any]]
    system_prompt_name: str
    llm_raw_output: Optional[str] = None
    llm_output: Optional[Dict[str, Any]]
    llm_provider: str
    llm_model: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    username: Optional[str] = None
    preview_url: Optional[str] = None
    retry_count: Optional[int] = None
    retry_errors: Optional[List[str]] = None
    request_received_at: Optional[datetime] = None
    component_selection: Optional["ComponentSelectionLog"] = None
    status: str = "completed"
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    llm_request_count: int = 1
    llm_calls: Optional[List[Dict[str, Any]]] = None

class PublishEventLog(BaseModel):
    exercise_id: str
    platon_resource_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    username: Optional[str] = None
    template_id: Optional[str] = None

class DiscussionGenerationLog(BaseModel):
    user_request: str
    retrieved_chunks: List[Any]
    embedding_model: str
    vector_table: str
    rag_query: str
    system_prompt_name: str
    llm_raw_output: Optional[str] = None
    llm_output: Optional[str]
    llm_provider: str
    llm_model: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    username: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None




class LogBase(DeclarativeBase):
    pass


class Prompt(LogBase):
    """Stores all system prompts by name, loaded from the prompts directory."""

    __tablename__ = "log_prompt"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_log_prompt_name", "name"),
    )


class LogConversation(LogBase):
    """Tracks the logical grouping of requests and generations within the same user session."""

    __tablename__ = "log_conversation"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at: Mapped[Optional[str]] = mapped_column(DateTime(timezone=True), nullable=True)

    exo_generations: Mapped[List["ExoGeneration"]] = relationship(
        "ExoGeneration", back_populates="conversation", cascade="all, delete-orphan"
    )
    discussion_generations: Mapped[List["DiscussionGeneration"]] = relationship(
        "DiscussionGeneration", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_log_conversation_conversation_id", "conversation_id"),
        Index("ix_log_conversation_session_id", "session_id"),
        Index("ix_log_conversation_created_at", "created_at"),
        Index("ix_log_conversation_username", "username"),
    )


class ExoGenerationRequest(LogBase):
    """One entry per user exercise-generation request."""

    __tablename__ = "log_exo_generation_request"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    request: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    fields_to_modify: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    variables: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    file_names: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    file_summaries: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    conversation_history: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    current_exercise_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    component_links: Mapped[List["ExoGenerationRequestComponentLink"]] = relationship(
        "ExoGenerationRequestComponentLink", back_populates="request_row", cascade="all, delete-orphan"
    )
    generation: Mapped[Optional["ExoGeneration"]] = relationship(
        "ExoGeneration", back_populates="request_row", uselist=False
    )

    __table_args__ = (
        Index("ix_log_exo_generation_request_created_at", "created_at"),
        Index("ix_log_exo_generation_request_session_id", "session_id"),
    )


class ExoGenerationRequestComponentLink(LogBase):
    """Links a generation request to the component tags it involved."""

    __tablename__ = "log_exo_generation_request_component_link"

    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_exo_generation_request.id", ondelete="CASCADE"), primary_key=True
    )
    component_tag: Mapped[str] = mapped_column(String, primary_key=True)

    request_row: Mapped["ExoGenerationRequest"] = relationship(
        "ExoGenerationRequest", back_populates="component_links"
    )

    __table_args__ = (
        Index("ix_log_exo_req_component_link", "request_id", "component_tag"),
    )


class DiscussionRequest(LogBase):
    """A plain documentation-search request sent by the user."""

    __tablename__ = "log_discussion_request"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    request: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    generation: Mapped[Optional["DiscussionGeneration"]] = relationship(
        "DiscussionGeneration", back_populates="request_row", uselist=False
    )

    __table_args__ = (
        Index("ix_log_discussion_request_created_at", "created_at"),
        Index("ix_log_discussion_request_session_id", "session_id"),
    )


class ExoRagSearch(LogBase):
    """One RAG search run over the exercises vector table."""

    __tablename__ = "log_exo_rag_search"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    vector_table: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    result_nodes: Mapped[List["ExoRagSearchResult"]] = relationship(
        "ExoRagSearchResult", back_populates="search", cascade="all, delete-orphan"
    )
    generation: Mapped[Optional["ExoGeneration"]] = relationship(
        "ExoGeneration", back_populates="rag_search", uselist=False
    )

    __table_args__ = (
        Index("ix_log_exo_rag_search_created_at", "created_at"),
    )


class ExoRagSearchResult(LogBase):
    """One ranked result node from an exercise RAG search (top RAG_LOG_TOP_K)."""

    __tablename__ = "log_exo_rag_search_result"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    search_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_exo_rag_search.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_row_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    platon_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    search: Mapped["ExoRagSearch"] = relationship("ExoRagSearch", back_populates="result_nodes")

    __table_args__ = (
        Index("ix_log_exo_rag_search_result_search_id", "search_id"),
        Index("ix_log_exo_rag_search_result_rank", "search_id", "rank"),
    )


class DiscussionRagSearch(LogBase):
    """One RAG search run over the Platon documentation vector table."""

    __tablename__ = "log_discussion_rag_search"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    vector_table: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    chunk_links: Mapped[List["DiscussionRagSearchChunkLink"]] = relationship(
        "DiscussionRagSearchChunkLink", back_populates="search", cascade="all, delete-orphan"
    )
    generation: Mapped[Optional["DiscussionGeneration"]] = relationship(
        "DiscussionGeneration", back_populates="rag_search", uselist=False
    )

    __table_args__ = (
        Index("ix_log_discussion_rag_search_created_at", "created_at"),
    )


class DiscussionRagSearchChunkLink(LogBase):
    """Links a discussion RAG search to the actual text chunk rows it retrieved."""

    __tablename__ = "log_discussion_rag_search_chunk_link"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    search_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_discussion_rag_search.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_row_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chunk_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    search: Mapped["DiscussionRagSearch"] = relationship("DiscussionRagSearch", back_populates="chunk_links")

    __table_args__ = (
        Index("ix_log_discussion_rag_chunk_search_id", "search_id"),
        Index("ix_log_discussion_rag_chunk_rank", "search_id", "rank"),
    )


class ExoGenerationResult(LogBase):
    """The full LLM call details for one exercise generation."""

    __tablename__ = "log_exo_generation_result"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    system_prompt_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_prompt.id", ondelete="SET NULL"), nullable=True
    )
    examples_used: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    llm_raw_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[str] = mapped_column(String, nullable=False)
    preview_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retry_errors: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    request_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    llm_calls: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    prompt: Mapped[Optional["Prompt"]] = relationship("Prompt", foreign_keys=[prompt_id])
    generation: Mapped[Optional["ExoGeneration"]] = relationship(
        "ExoGeneration", back_populates="generation_result", uselist=False
    )

    __table_args__ = (
        Index("ix_log_exo_generation_result_created_at", "created_at"),
        Index("ix_log_exo_generation_result_request_received_at", "request_received_at"),
    )


class DiscussionGenerationResult(LogBase):
    """The full LLM call details for one discussion (doc-QA) generation."""

    __tablename__ = "log_discussion_generation_result"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    system_prompt_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_prompt.id", ondelete="SET NULL"), nullable=True
    )
    chunks_used: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    llm_raw_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    prompt: Mapped[Optional["Prompt"]] = relationship("Prompt", foreign_keys=[prompt_id])
    generation: Mapped[Optional["DiscussionGeneration"]] = relationship(
        "DiscussionGeneration", back_populates="generation_result", uselist=False
    )

    __table_args__ = (
        Index("ix_log_discussion_generation_result_created_at", "created_at"),
    )


class LogComponentSelection(LogBase):
    """Stores the output of the component-selection LLM step before pure exercise generation."""

    __tablename__ = "log_component_selection"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    user_priority_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    selected_tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[str] = mapped_column(String, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    generation: Mapped[Optional["ExoGeneration"]] = relationship(
        "ExoGeneration", back_populates="component_selection", uselist=False
    )

    __table_args__ = (
        Index("ix_log_component_selection_created_at", "created_at"),
    )


class ExoGeneration(LogBase):
    """Aggregates one complete exercise generation run: request + RAG + LLM."""

    __tablename__ = "log_exo_generation"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_exo_generation_request.id", ondelete="SET NULL"), nullable=True
    )
    rag_search_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_exo_rag_search.id", ondelete="SET NULL"), nullable=True
    )
    generation_result_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_exo_generation_result.id", ondelete="SET NULL"), nullable=True
    )
    component_selection_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_component_selection.id", ondelete="SET NULL"), nullable=True
    )
    conversation_fk: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_conversation.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="completed")
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    request_row: Mapped[Optional["ExoGenerationRequest"]] = relationship(
        "ExoGenerationRequest", back_populates="generation"
    )
    rag_search: Mapped[Optional["ExoRagSearch"]] = relationship(
        "ExoRagSearch", back_populates="generation"
    )
    generation_result: Mapped[Optional["ExoGenerationResult"]] = relationship(
        "ExoGenerationResult", back_populates="generation"
    )
    component_selection: Mapped[Optional["LogComponentSelection"]] = relationship(
        "LogComponentSelection", back_populates="generation"
    )
    conversation: Mapped[Optional["LogConversation"]] = relationship(
        "LogConversation", back_populates="exo_generations"
    )

    __table_args__ = (
        Index("ix_log_exo_generation_request_id", "request_id"),
        Index("ix_log_exo_generation_created_at", "created_at"),
        Index("ix_log_exo_generation_conversation_fk", "conversation_fk"),
    )


class DiscussionGeneration(LogBase):
    """Aggregates one complete discussion (doc-QA) run: request + RAG + LLM."""

    __tablename__ = "log_discussion_generation"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_discussion_request.id", ondelete="SET NULL"), nullable=True
    )
    rag_search_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_discussion_rag_search.id", ondelete="SET NULL"), nullable=True
    )
    generation_result_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_discussion_generation_result.id", ondelete="SET NULL"), nullable=True
    )
    conversation_fk: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("log_conversation.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="completed")
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    request_row: Mapped[Optional["DiscussionRequest"]] = relationship(
        "DiscussionRequest", back_populates="generation"
    )
    rag_search: Mapped[Optional["DiscussionRagSearch"]] = relationship(
        "DiscussionRagSearch", back_populates="generation"
    )
    generation_result: Mapped[Optional["DiscussionGenerationResult"]] = relationship(
        "DiscussionGenerationResult", back_populates="generation"
    )
    conversation: Mapped[Optional["LogConversation"]] = relationship(
        "LogConversation", back_populates="discussion_generations"
    )

    __table_args__ = (
        Index("ix_log_discussion_generation_request_id", "request_id"),
        Index("ix_log_discussion_generation_created_at", "created_at"),
        Index("ix_log_discussion_generation_conversation_fk", "conversation_fk"),
    )


class PublishEvent(LogBase):
    """Tracks exercise publish events sent to Platon."""

    __tablename__ = "log_publish_event"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    exercise_id: Mapped[str] = mapped_column(String, nullable=False)
    platon_resource_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    template_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_log_publish_event_created_at", "created_at"),
        Index("ix_log_publish_event_exercise_id", "exercise_id"),
    )

