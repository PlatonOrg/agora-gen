import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.infra.llm.llm_wrapper import chat_with_llm
from src.services.models.api import (
    ConfigVariablesGenerationResult,
    ExerciseData,
    ExerciseMetadata,
    GeneratedExercise,
    PureExerciseGenerationResult,
)
from src.core import path_constants
from src.core.config_app import settings
from src.services.output_sanitizer_service import sanitize_generated_exercise

logger = logging.getLogger(__name__)

_COMPONENT_EXTRA_DOCS: Dict[str, str] = {
    "wc-drag-drop": "drag_drop.txt",
    "wc-match-list": "wc_match_list.txt",
    "wc-crossword": "wc_cross_word.txt",
    "wc-jsx": "wc_jsx.txt",
    "wc-matrix": "wc_matrix.txt",
    "wc-binded-bubbles": "wc_binded_bubbles.txt",
    "wc-radio-group": "wc_radio_group.txt",
    "wc-presenter": "wc_presenter.txt",
}


class GenerationService:
    def __init__(self, temperature: float = 0.0) -> None:
        self._temperature = temperature
        self._logger = logging.getLogger(__name__)

    def _load_system_prompt(self) -> str:
        prompt_path = os.path.join(path_constants.PROMPTS_DIR, 'template_exercise.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_pure_exercise_prompt(self) -> str:
        prompt_path = os.path.join(path_constants.PROMPTS_DIR, 'pure_exercise.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_pure_exercise_modification_prompt(self) -> str:
        prompt_path = os.path.join(path_constants.PROMPTS_DIR, 'pure_exercise_modification.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_template_modification_prompt(self) -> str:
        prompt_path = os.path.join(path_constants.PROMPTS_DIR, 'template_exercise_modification.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_component_metadata(self) -> List[Dict[str, Any]]:
        with open(path_constants.COMPONENT_METADATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _format_components_for_prompt(self, components: List[str]) -> str:
        metadata = self._load_component_metadata()
        use_full_mdx = settings.COMPONENT_DOC_MODE == "full"
        component_docs = []

        for comp in components:
            comp_data = next((item for item in metadata if item['tag'] == comp), None)
            if not comp_data:
                continue

            if use_full_mdx:
                doc_path = comp_data.get("doc_path")
                if doc_path:
                    mdx_file = path_constants.COMPONENT_DOCS_DIR.parent / doc_path
                    try:
                        full_doc = mdx_file.read_text(encoding="utf-8").strip()
                        component_body = (
                            f"=== Composant: {comp_data['name']} (tag: {comp_data['tag']}) ===\n"
                            f"{full_doc}"
                        )
                    except OSError:
                        self._logger.warning(
                            "MDX file not found for tag '%s': %s", comp, mdx_file
                        )
                        component_body = self._build_schema_block(comp_data)
                else:
                    component_body = self._build_schema_block(comp_data)
            else:
                component_body = self._build_schema_block(comp_data)

            extra_instructions_filename = _COMPONENT_EXTRA_DOCS.get(comp)
            if extra_instructions_filename:
                instructions_path = Path(path_constants.PROMPTS_DIR) / extra_instructions_filename
                try:
                    instructions = instructions_path.read_text(encoding="utf-8").strip()
                    if instructions:
                        component_body += f"\n\nInstructions spécifiques:\n{instructions}"
                except OSError:
                    self._logger.warning(
                        "Component instructions file not found for tag '%s': %s",
                        comp, instructions_path,
                    )

            component_docs.append(component_body)

        return "\n\n".join(component_docs)

    @staticmethod
    def _build_schema_block(comp_data: Dict[str, Any]) -> str:
        return (
            f"=== Composant: {comp_data['name']} (tag: {comp_data['tag']}) ===\n"
            f"Catégorie: {comp_data.get('category', '')}\n"
            f"Description: {comp_data.get('description', '')}\n"
            f"Schéma des propriétés:\n"
            f"{json.dumps(comp_data.get('properties', {}), ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _build_readme_from_llm_metadata(metadata: Dict[str, Any]) -> Optional[str]:
        lines: List[str] = []
        if metadata.get("objectifs_pedagogiques"):
            lines.append("## Objectifs pédagogiques\n")
            lines.append(metadata["objectifs_pedagogiques"])
            lines.append("")
        if metadata.get("public_vise"):
            lines.append("## Public visé\n")
            lines.append(metadata["public_vise"])
            lines.append("")
        if metadata.get("prerequis"):
            lines.append("## Prérequis\n")
            lines.append(metadata["prerequis"])
            lines.append("")
        if metadata.get("consignes"):
            lines.append("## Consignes\n")
            lines.append(metadata["consignes"])
            lines.append("")
        if not lines:
            return None
        return "\n".join(lines).rstrip()

    def _format_schema_for_prompt(self, schema: List[Dict[str, Any]]) -> str:
        formatted = ""
        for var in schema:
            if not isinstance(var, dict):
                continue
            formatted += f'    "nom de la variable": "{var["name"]}",\n'
            formatted += f'    "type de la variable": "{var["type"]}",\n'
            formatted += f'    "description de la variable": "{var["description"]}"\n'
            formatted += f'    "valeur par defaut": "{var["value"]}"\n'
        formatted = formatted.rstrip(',\n') + "\n]"
        return formatted

    def _format_conversation_history(self, conversation_history: List[Any]) -> str:
        """Format the conversation history for inclusion in the prompt."""
        if not conversation_history:
            return ""

        formatted = "Historique de la conversation avec l'utilisateur:\n"
        for i, msg in enumerate(conversation_history, 1):
            # Handle both Pydantic models and dictionaries
            if hasattr(msg, 'role'):
                # Pydantic model
                role = msg.role
                content = msg.content
                components = msg.components or []
            else:
                # Dictionary
                role = msg.get("role", "user")
                content = msg.get("content", "")
                components = msg.get("components", [])

            if role == "user":
                formatted += f"Message {i} de l'utilisateur: {content}"
                if components:
                    formatted += f" [Composants demandes: {', '.join(components)}]"
                formatted += "\n"

        return formatted

    def _format_current_exercise_state(self, exercise_data: ExerciseData, for_pure: bool = True) -> str:
        """Serialize the current exercise state using the exact JSON field names the LLM
        schema expects.

        Using the correct canonical keys (title, statement, form, builder, grader, …)
        is critical: if we send French translations the LLM will mirror those names in
        its output, producing invalid exercise data (e.g. a top-level "bac a sable" key
        instead of "sandbox").
        """
        if for_pure:
            # Build a dict that mirrors the LLM output schema exactly.
            state: Dict[str, Any] = {}

            if exercise_data.name:
                state["name"] = exercise_data.name
            if exercise_data.description:
                state["description"] = exercise_data.description
            if exercise_data.titre:
                state["title"] = exercise_data.titre
            if exercise_data.enonce:
                state["statement"] = exercise_data.enonce
            if exercise_data.forme:
                state["form"] = exercise_data.forme
            if exercise_data.solution:
                state["solution"] = exercise_data.solution
            if exercise_data.sandbox:
                state["sandbox"] = exercise_data.sandbox
            if exercise_data.construction:
                state["builder"] = exercise_data.construction
            if exercise_data.evaluation:
                state["grader"] = exercise_data.evaluation
            if exercise_data.indications:
                state["hint"] = exercise_data.indications
            if exercise_data.theories:
                state["theories"] = exercise_data.theories

            # Metadata block — keys must match the LLM metadata sub-object schema.
            meta = exercise_data.metadata
            metadata: Dict[str, Any] = {}
            if meta.levels:
                metadata["levels"] = meta.levels
            if meta.topics:
                metadata["topics"] = meta.topics
            if meta.readme:
                metadata["readme"] = meta.readme
            if metadata:
                state["metadata"] = metadata

            # Sandbox variables are extra top-level keys in the LLM schema — inline them.
            if exercise_data.sandbox_variables:
                for var_name, var_value in exercise_data.sandbox_variables.items():
                    if var_name not in state:
                        state[var_name] = var_value

        else:
            # For config variables generation: use the canonical config_variables key.
            state = {}
            if exercise_data.config_variables:
                state["config_variables"] = exercise_data.config_variables

        if not state:
            return ""

        return f"Current exercise state:\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"

    async def generate_config_variables(
            self,
            exercise_data: ExerciseData,
            user_request: str,
            conversation_history: List[Dict[str, Any]] | None = None,
            fields_to_modify: List[str] = [],
            is_modification: bool = False,
    ) -> ConfigVariablesGenerationResult:
        self._logger.info("Starting config variable generation (modification=%s)", is_modification)

        schema_config = exercise_data.config_variables["inputs"]
        base_system_prompt = self._load_template_modification_prompt() if is_modification else self._load_system_prompt()

        if fields_to_modify:
            filtered_schema = [var for var in schema_config if var.get("name") in fields_to_modify]
            schema_str = self._format_schema_for_prompt(filtered_schema)
            system_prompt = f"""
{base_system_prompt}

**Description du template**: {exercise_data.description or ''}

Vous etes donne des exemples complets pour le contexte, mais vous devez generer uniquement les variables indiquees dans le schema ci-dessous. Ne generez pas l'exercice complet, seulement les parties specifiees.

**Les variables a modifier**: {schema_str}
"""
        else:
            schema_str = self._format_schema_for_prompt(schema_config)
            system_prompt = f"""
{base_system_prompt}

**Description du template**: {exercise_data.description or ''}
**Les variables du template**: {schema_str}
"""

        history_str = self._format_conversation_history(conversation_history or [])
        state_str = self._format_current_exercise_state(exercise_data, for_pure=False)

        user_prompt = state_str
        if history_str:
            user_prompt += f"{history_str}\n\n"
        user_prompt += f"Derniere demande de l'utilisateur: {user_request}"

        include_properties = fields_to_modify if fields_to_modify else None

        llm_result = await chat_with_llm(
            system_prompt=system_prompt,
            user_request=user_prompt,
            temperature=self._temperature,
            schema_config=schema_config,
            include_properties=include_properties,
        )

        variables = llm_result.parsed
        if isinstance(variables, dict) and variables.get("name"):
            exercise_data.name = variables.pop("name").replace("_", " ")
        if isinstance(variables, dict) and variables.get("description"):
            exercise_data.description = variables.pop("description")
        if isinstance(variables, dict) and variables.get("metadata"):
            metadata = variables.pop("metadata")
            if isinstance(metadata, dict):
                existing = exercise_data.metadata
                readme = existing.readme if existing.readme is not None else self._build_readme_from_llm_metadata(metadata)
                exercise_data.metadata = ExerciseMetadata(
                    levels=metadata.get("levels") or existing.levels,
                    topics=metadata.get("topics") or existing.topics,
                    readme=readme,
                )

        return ConfigVariablesGenerationResult(variables=variables, llm=llm_result)

    def _build_components_block(
        self,
        component_docs: str,
        mandatory_tags: List[str],
        indicative_tags: List[str],
        llm_reasoning: str = "",
    ) -> str:
        if not mandatory_tags and not indicative_tags:
            return ""

        parts: List[str] = []

        parts.append("## Composants de l'exercice")

        if mandatory_tags:
            parts.append(
                "### Composants obligatoires\n\n"
                "L'utilisateur vient d'attacher explicitement les composants suivants à cette demande. "
                "Leur utilisation est **obligatoire et non négociable** — tu dois impérativement les inclure "
                "dans le `form`, les initialiser dans le `builder` et les lire dans le `grader` :\n\n"
                + "\n".join(f"- `{tag}`" for tag in mandatory_tags)
            )

        if indicative_tags:
            parts.append(
                "### Composants déjà présents dans l'exercice (historique)\n\n"
                "Les composants suivants ont été utilisés dans les générations précédentes de cet exercice. "
                "Ils sont fournis à titre de contexte — l'exercice les utilise déjà, donc tu dois en tenir "
                "compte pour rester cohérent, mais tu n'es pas obligé de les réintroduire si la modification "
                "demandée ne les concerne pas :\n\n"
                + "\n".join(f"- `{tag}`" for tag in indicative_tags)
            )

        if llm_reasoning:
            parts.append(
                "### Raisonnement de la sélection initiale\n\n"
                "Voici le raisonnement produit lors de la phase de sélection des composants au premier tour. "
                "Il suit une structure en cinq points : (1) analyse de l'interaction apprenant, "
                "(2) justification des composants imposés par l'utilisateur, "
                "(3) justification des composants additionnels sélectionnés, "
                "Utilise-le pour comprendre l'intention pédagogique originale de l'exercice :\n\n"
                + llm_reasoning
            )

        parts.append(
            "### Documentation des composants\n\n"
            "Voici la documentation complète des composants concernés. "
            "Respecte scrupuleusement les noms et types des propriétés — "
            "n'invente aucune propriété absente de cette documentation :\n\n"
            + component_docs
        )

        return "\n\n".join(parts) + "\n\n"

    async def generate_pure_exercise_with_examples(
        self,
        exercise_data: ExerciseData,
        user_request: str,
        examples: List[Dict[str, Any]],
        conversation_history: List[Dict[str, Any]] = None,
        fields_to_modify: List[str] = [],
        file_ids: Optional[List[str]] = None,
        file_contents: Optional[List[str]] = None,
        mandatory_tags: Optional[List[str]] = None,
        indicative_tags: Optional[List[str]] = None,
        llm_reasoning: str = "",
        is_modification: bool = False,
        llm_calls_accumulator: Optional[List[Dict[str, Any]]] = None,
    ) -> PureExerciseGenerationResult:
        self._logger.info("Starting pure exercise generation with examples (modification=%s)", is_modification)
        if file_ids:
            self._logger.info(
                "Files attached to generation request: %d file(s), ids=%s",
                len(file_ids), file_ids,
            )

        components = exercise_data.components or []
        component_docs = self._format_components_for_prompt(components)

        logger.info(f"component_docs for exercise with components {components}:\n{component_docs}")

        if is_modification:
            system_prompt = self._load_pure_exercise_modification_prompt()
        else:
            system_prompt = self._load_pure_exercise_prompt()
            examples_text = "\n\n".join(f"Exercise {i+1} : {json.dumps(ex, ensure_ascii=False)}" for i, ex in enumerate(examples))
            system_prompt += f"\n\nExemples d'exercies proches a la demande de l'utilisateur:\n{examples_text}"


        if fields_to_modify:
            system_prompt += f"""
\n\nTu es donne des exemples complets pour le contexte, mais tu doit generer uniquement les champs indiques 
ci-dessous. Ne genere pas l'exercice complet, seulement les parties specifiees.\n\nChamps a modifier: 
{', '.join(fields_to_modify)}

Il faut que tu regardes l'etat actuel de l'exercice et que tu modifies les champs demandes pour repondre a la demande
de l'utilisateur.
"""

        history_str = self._format_conversation_history(conversation_history or [])
        state_str = self._format_current_exercise_state(exercise_data, for_pure=True)

        user_prompt = f"\n{state_str}\n"

        components_block = self._build_components_block(
            component_docs=component_docs,
            mandatory_tags=mandatory_tags or [],
            indicative_tags=indicative_tags or [],
            llm_reasoning=llm_reasoning,
        )
        if components_block:
            user_prompt = components_block + user_prompt

        if history_str:
            user_prompt += f"{history_str}\n"
        user_prompt += f"\nDernière demande de l'utilisateur: {user_request}"

        if file_contents:
            self._logger.info(
                "Injecting %d file content(s) into user prompt (text extraction fallback)",
                len(file_contents),
            )
            files_block = "\n\n".join(
                f"[Fichier joint {i + 1}]\n{text}" for i, text in enumerate(file_contents)
            )
            user_prompt += f"\n\nContenu des fichiers joints par l'utilisateur:\n{files_block}"

        include_properties = fields_to_modify if fields_to_modify else None

        llm_result = await chat_with_llm(
            system_prompt=system_prompt,
            user_request=user_prompt,
            temperature=self._temperature,
            use_fixed_schema=True,
            include_properties=include_properties,
            file_ids=file_ids or [],
            llm_calls_accumulator=llm_calls_accumulator,
            call_type="modification" if is_modification else "generation",
        )

        return PureExerciseGenerationResult(
            generated_exercise=sanitize_generated_exercise(GeneratedExercise.from_llm_dict(llm_result.parsed)),
            llm=llm_result,
        )

