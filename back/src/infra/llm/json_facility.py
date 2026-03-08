"""
JSON schema construction for structured LLM output.

This module builds *raw* JSON Schema dicts that describe the expected
output shape.  Provider-specific wrapping (the envelope that Gemini,
Groq, or Ollama expect) is **not** done here -- that responsibility
belongs to each ``LLMProvider.wrap_json_schema`` implementation.
"""

import logging
from typing import Any, Dict, List, Optional

from src.services.models.schemas import TYPE_MAP

logger = logging.getLogger(__name__)


def build_fixed_exercise_json_schema(
    include_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the canonical exercise JSON schema.

    Args:
        include_properties: When provided, only these properties are
            included in the schema.  ``None`` means "include everything".

    Returns:
        A raw JSON Schema ``dict`` (no provider envelope).
    """
    logger.info(
        "Building fixed exercise JSON schema -- include_properties: %s",
        include_properties,
    )

    all_properties: Dict[str, Any] = {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "sandbox": {"type": "string", "enum": ["node", "python"]},
        "builder": {"type": "string"},
        "grader": {"type": "string"},
        "statement": {"type": "string"},
        "form": {"type": "string"},
        "solution": {"type": "string"},
        "hint": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "theories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["title", "url"],
            },
            "maxItems": 5,
        },
        "metadata": {
            "type": "object",
            "properties": {
                "levels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3,
                    "uniqueItems": True,
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                    "uniqueItems": True,
                },
                "objectifs_pedagogiques": {"type": "string"},
                "public_vise": {"type": "string"},
                "prerequis": {"type": "string"},
                "consignes": {"type": "string"},
            },
            "required": ["levels", "topics"],
        },
    }

    all_required = [
        "name", "description",
        "title", "sandbox", "builder", "grader",
        "statement", "form", "solution",
        "metadata",
    ]

    allow_additional = (
        include_properties is None
        or "sandbox_variables" in include_properties
    )

    if include_properties is not None:
        properties = {
            key: val
            for key, val in all_properties.items()
            if key in include_properties
        }
        required = [r for r in all_required if r in include_properties]
    else:
        properties = all_properties
        required = all_required

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    if allow_additional:
        schema["additionalProperties"] = True

    return schema


def build_component_selection_schema(available_tags: List[str]) -> Dict[str, Any]:
    """Build a JSON schema that forces the LLM to output a list of component tags with reasoning.

    Args:
        available_tags: The exhaustive list of valid component tags.

    Returns:
        A raw JSON Schema ``dict`` (no provider envelope).
    """
    return {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": (
                    "Raisonnement structuré suivant exactement ce format : "
                    "1. Analyse de l'interaction — ce que l'apprenant doit faire (2 à 3 phrases). "
                    "2. Composants imposés par l'utilisateur — pour chacun, comment il sera utilisé "
                    "(initialisation builder, lecture grader). "
                    "3. Composants additionnels sélectionnés — pour chacun, justifier (a) l'interaction "
                    "ou le besoin d'affichage, (b) comment le builder l'initialisera, "
                    "(c) comment le grader le lira. "                ),
            },
            "selected_tags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": available_tags,
                },
                "description": "Liste ordonnée des tags de composants les plus pertinents pour la requête.",
            },
        },
        "required": ["reasoning", "selected_tags"],
        "additionalProperties": False,
    }


def build_json_schema_from_config(
    config: List[Dict[str, Any]],
    include_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    base_properties: Dict[str, Any] = {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "metadata": {
            "type": "object",
            "properties": {
                "levels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3,
                    "uniqueItems": True,
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                    "uniqueItems": True,
                },
                "objectifs_pedagogiques": {"type": "string"},
                "public_vise": {"type": "string"},
                "prerequis": {"type": "string"},
                "consignes": {"type": "string"},
            },
            "required": ["levels", "topics"],
        },
    }

    if include_properties is not None:
        properties: Dict[str, Any] = {}
        required: List[str] = []
    else:
        properties = dict(base_properties)
        required = ["name", "description", "metadata"]

    logger.info("Building JSON schema from config: %s", config)

    for var in config:
        if not isinstance(var, dict):
            continue

        name = var.get("name")
        var_type = var.get("type")

        if not name or var_type not in TYPE_MAP:
            continue

        if include_properties is not None and name not in include_properties:
            continue

        schema_entry: Dict[str, Any] = {"type": TYPE_MAP[var_type]}

        if var_type == "list":
            schema_entry["items"] = {"type": "string"}
        elif var_type == "select" and "options" in var:
            choices = var["options"].get("choices", [])
            if choices:
                schema_entry["enum"] = choices
        elif var_type == "number" and "options" in var:
            options = var["options"]
            if "min" in options:
                schema_entry["minimum"] = options["min"]
            if "max" in options:
                schema_entry["maximum"] = options["max"]
        elif var_type == "code":
            value = var.get("value")
            if value is not None:
                try:
                    float(value)
                    schema_entry["type"] = "number"
                except (ValueError, TypeError):
                    schema_entry["type"] = "string"
            else:
                schema_entry["type"] = "string"

        properties[name] = schema_entry
        required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

