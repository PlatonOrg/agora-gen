from __future__ import annotations

from typing import List

from src.infra.vector.models import ExerciseMetadata, ExerciseParts, FilledTemplateParameter, TemplateParameter


def build_exercise_text(metadata: ExerciseMetadata, parts: ExerciseParts, label: str) -> str:
    lines: List[str] = [f"{label}: {metadata.name}"]

    if parts.title:
        lines.append(f"Le titre: {parts.title}")

    if metadata.description:
        lines.append(f"Description: {metadata.description}")

    if metadata.topics:
        lines.append(f"Les sujets: {', '.join(metadata.topics)}")

    if metadata.levels:
        lines.append(f"Les niveaux: {', '.join(metadata.levels)}")

    if parts.statement:
        lines.append(f"L'énoncé de l'exercice: {parts.statement}")

    if parts.solution:
        lines.append(f"La solution de l'exercice: {parts.solution}")

    if parts.form:
        lines.append(f"Le corps de l'exercice: {parts.form}")

    if parts.components:
        lines.append(f"Les composants utilisés dans l'exercice: {', '.join(parts.components)}")

    return "\n\n".join(lines)


def build_template_text(
    metadata: ExerciseMetadata,
    parts: ExerciseParts,
    parameters: List[TemplateParameter],
    is_configurable: bool,
) -> str:
    label = "Modèle" if is_configurable else "Exercice basé sur modèle"
    text = build_exercise_text(metadata, parts, label)

    param_lines: List[str] = []
    for param in parameters:
        if not param.description:
            continue
        clean_desc = param.description.replace("\n", " ").strip()
        param_lines.append(f"{param.name}: {clean_desc} de type {param.type}")

    if param_lines:
        text += "\n" + f"Paramètres de {label.lower()}:\n" + "\n".join(param_lines)

    return text


def build_template_exo_text(
    metadata: ExerciseMetadata,
    parts: ExerciseParts,
    filled_parameters: List[FilledTemplateParameter],
) -> str:
    """
    Build the embedding text for a TEMPLATE_EXO instance.

    Unlike the parent template which describes *what* each parameter does,
    a template_exo embedding describes *what values were actually used*,
    making each instance semantically distinct.
    """
    text = build_exercise_text(metadata, parts, "Exercice basé sur modèle")

    param_lines: List[str] = []
    for param in filled_parameters:
        parts_line = [param.name]
        if param.description:
            parts_line.append(param.description.replace("\n", " ").strip())
        if param.filled_value is not None:
            parts_line.append(f"valeur: {param.filled_value}")
        param_lines.append(" — ".join(parts_line))

    if param_lines:
        text += "\n\nValeurs des paramètres:\n" + "\n".join(param_lines)

    return text


