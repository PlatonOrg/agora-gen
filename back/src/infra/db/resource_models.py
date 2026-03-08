"""
SQLAlchemy ORM models for the core resource tables:
  - component
  - template
  - exercise
  - exercise_component_link
  - template_component_link

These are the canonical definitions used everywhere in src/.
The old script-level re-declarations in scripts/ are superseded by this file.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UUID,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ResourceBase(DeclarativeBase):
    pass


class Component(ResourceBase):
    __tablename__ = "component"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tag: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    usage: Mapped[str] = mapped_column(Text, nullable=True)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_modified_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    exercises: Mapped[List["Exercise"]] = relationship(
        "Exercise", secondary="exercise_component_link", back_populates="components"
    )
    templates: Mapped[List["Template"]] = relationship(
        "Template", secondary="template_component_link", back_populates="components"
    )

    __table_args__ = (Index("ix_component_tag", "tag"),)


class Template(ResourceBase):
    __tablename__ = "template"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    platon_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    variables: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_modified_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    exercises: Mapped[List["Exercise"]] = relationship("Exercise", back_populates="template")
    components: Mapped[List["Component"]] = relationship(
        "Component", secondary="template_component_link", back_populates="templates"
    )

    __table_args__ = (Index("ix_template_platon_id", "platon_id"),)


class Exercise(ResourceBase):
    __tablename__ = "exercise"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    platon_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    template_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template.id"), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_modified_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    template: Mapped["Template"] = relationship("Template", back_populates="exercises")
    components: Mapped[List["Component"]] = relationship(
        "Component", secondary="exercise_component_link", back_populates="exercises"
    )

    __table_args__ = (Index("ix_exercise_platon_id", "platon_id"),)


class ExerciseComponentLink(ResourceBase):
    __tablename__ = "exercise_component_link"

    exercise_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercise.id"), primary_key=True
    )
    component_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("component.id"), primary_key=True
    )

    __table_args__ = (
        Index("ix_exercise_component_link_exercise_component", "exercise_id", "component_id"),
    )


class TemplateComponentLink(ResourceBase):
    __tablename__ = "template_component_link"

    template_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template.id"), primary_key=True
    )
    component_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("component.id"), primary_key=True
    )

    __table_args__ = (
        Index("ix_template_component_link_template_component", "template_id", "component_id"),
    )

