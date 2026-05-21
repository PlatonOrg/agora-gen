from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core import path_constants
from src.core.config_app import settings
from src.infra.llm.json_facility import build_component_selection_schema
from src.infra.llm.llm_wrapper import chat_with_llm

logger = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    prompt_path = path_constants.PROMPTS_DIR / "component_selection.txt"
    with open(prompt_path, "r", encoding="utf-8") as fh:
        return fh.read()


@dataclass
class ComponentSelectionResult:
    llm_selected_tags: List[str]
    user_priority_tags: List[str]
    llm_provider: str
    llm_model: str
    available_tags: List[str]
    reasoning: str = field(default="")

    @property
    def all_tags(self) -> List[str]:
        combined = list(self.user_priority_tags)
        for tag in self.llm_selected_tags:
            if tag not in combined:
                combined.append(tag)
        return combined

    @property
    def llm_only_tags(self) -> List[str]:
        user_set = set(self.user_priority_tags)
        return [t for t in self.llm_selected_tags if t not in user_set]


def _load_component_metadata() -> List[Dict[str, Any]]:
    with open(path_constants.COMPONENT_METADATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_component_mdx(entry: Dict[str, Any], max_chars: int = 500) -> str:
    """Load the MDX documentation file for a component, truncated to max_chars."""
    doc_path = entry.get("doc_path")
    if not doc_path:
        return entry.get("description", "")
    full_path = path_constants.PLATON_DOCS_DIR.parent / doc_path
    try:
        content = full_path.read_text(encoding="utf-8")
        # Strip frontmatter and MDX imports to keep only useful content.
        lines = [l for l in content.splitlines() if not l.startswith("import ")]
        cleaned = "\n".join(lines).strip()
        return cleaned[:max_chars]
    except Exception:
        return entry.get("description", "")


def _build_component_docs_block(
    tags: List[str],
    metadata: List[Dict[str, Any]],
    full: bool = False,
    name_only: bool = False,
) -> str:
    """Build a component listing for the selection prompt.

    - name_only=True : one line per tag (tag + name). Used for the full available list.
    - full=False     : tag + name + short description from metadata.
    - full=True      : tag + name + content from the dedicated .mdx file.
    """
    blocks: List[str] = []
    for tag in tags:
        entry = next((c for c in metadata if c.get("tag") == tag), None)
        if not entry:
            continue

        if name_only:
            blocks.append(f"`{entry['tag']}` — {entry['name']}")
            continue

        lines: List[str] = []
        lines.append(f"### `{entry['tag']}` — {entry['name']} ({entry['category']})")
        if full:
            lines.append(_load_component_mdx(entry))
        else:
            description = entry.get("description", "")
            if description:
                lines.append(description)

        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


def _build_selection_user_prompt(
    user_request: str,
    available_tags: List[str],
    metadata: List[Dict[str, Any]],
    user_priority_tags: Optional[List[str]] = None,
    file_summaries: Optional[List[str]] = None,
    current_components: Optional[List[str]] = None,
) -> str:
    parts: List[str] = []

    # Available components — tag + name only to keep the prompt light.
    # Full docs are only loaded for priority components below.
    parts.append("## Composants disponibles")
    parts.append(_build_component_docs_block(available_tags, metadata, name_only=True))
    parts.append("")

    # User request
    parts.append("## Demande de l'utilisateur")
    parts.append(user_request)
    parts.append("")

    # Mandatory components (user-chosen) — full docs so LLM knows how to use them
    if user_priority_tags:
        parts.append("## Composants imposés par l'utilisateur (obligatoires)")
        parts.append(
            "Les composants suivants ont été explicitement choisis par l'utilisateur. "
            "Ils DOIVENT figurer dans la sélection finale sans exception."
        )
        mandatory_docs = _build_component_docs_block(user_priority_tags, metadata, full=True)
        parts.append(mandatory_docs if mandatory_docs else ", ".join(user_priority_tags))
        parts.append("")

    # Attached files
    if file_summaries:
        relevant = [s for s in file_summaries if s and s.strip()]
        if relevant:
            parts.append("## Résumés des fichiers joints")
            for i, summary in enumerate(relevant, start=1):
                parts.append(f"- Fichier {i} : {summary}")
            parts.append("")

    # Existing components in the exercise (for modification requests)
    if current_components:
        parts.append("## Composants déjà présents dans l'exercice")
        parts.append(", ".join(current_components))
        parts.append("")

    # Task instruction — direct, no verbose scaffold
    parts.append("## Tâche")
    if user_priority_tags:
        parts.append(
            f"Les composants imposés sont : {', '.join(user_priority_tags)}. "
            "Sélectionne les composants additionnels nécessaires (liste disponible ci-dessus) "
            "et retourne la liste complète (imposés + additionnels). "
            "Dans ton raisonnement, explique uniquement comment les composants "
            "sélectionnés (hors imposés) répondent à la demande et comment ils seront "
            "utilisés concrètement dans l'exercice."
        )
    else:
        parts.append(
            "Sélectionne l'ensemble minimal de composants de la liste disponible "
            "qui permet de construire cet exercice. "
            "Dans ton raisonnement, explique comment les composants sélectionnés "
            "seront utilisés concrètement dans l'exercice."
        )

    return "\n".join(parts)


async def select_components_for_request(
    user_request: str,
    user_priority_tags: Optional[List[str]] = None,
    file_summaries: Optional[List[str]] = None,
    current_components: Optional[List[str]] = None,
    llm_calls_accumulator: Optional[List[Dict[str, Any]]] = None,
) -> ComponentSelectionResult:
    metadata = _load_component_metadata()
    banned = set(settings.BANNED_COMPONENTS)
    available_tags = [c["tag"] for c in metadata if c.get("tag") not in banned]

    priority_tags = user_priority_tags or []

    logger.info(
        "Component selection: available=%d tags, user_priority=%s",
        len(available_tags),
        priority_tags,
    )

    user_prompt = _build_selection_user_prompt(
        user_request=user_request,
        available_tags=available_tags,
        metadata=metadata,
        user_priority_tags=priority_tags or None,
        file_summaries=file_summaries,
        current_components=current_components,
    )

    schema = build_component_selection_schema(available_tags)

    llm_result = await chat_with_llm(
        system_prompt=_load_system_prompt(),
        user_request=user_prompt,
        temperature=0.0,
        raw_json_schema=schema,
        llm_calls_accumulator=llm_calls_accumulator,
        call_type="component_selection",
    )

    parsed = llm_result.parsed or {}
    selected_raw: List[str] = parsed.get("selected_tags", [])
    reasoning: str = parsed.get("reasoning", "")

    valid_set = set(available_tags)
    llm_selected = [t for t in selected_raw if t in valid_set]

    for tag in priority_tags:
        if tag not in llm_selected and tag in valid_set:
            llm_selected.append(tag)

    logger.info(
        "Component selection: user_priority=%s, llm_selected=%s",
        priority_tags,
        llm_selected,
    )
    if reasoning:
        logger.debug("Component selection reasoning: %s", reasoning[:400])

    return ComponentSelectionResult(
        llm_selected_tags=llm_selected,
        user_priority_tags=priority_tags,
        llm_provider=llm_result.provider,
        llm_model=llm_result.model,
        available_tags=available_tags,
        reasoning=reasoning,
    )
