"""
Sandbox correction service.

Owns the LLM-based correction loop that fires when a Platon preview
fails with a compilation / sandbox error.  Provides two high-level
methods -- one for pure-exercise PLE previews and one for
template-based PLO previews -- so the workflow stays thin.

Responsibilities:
    - Loading the repair prompt.
    - Calling the LLM for correction.
    - Re-applying corrected data to ``ExerciseData``.
    - Driving the generic ``attempt_with_retry`` loop.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.llm.llm_wrapper import chat_with_llm
from src.workflows.retry_handler import attempt_with_retry, RetryResult
from src.services.models.platon import PreviewResult, SandboxError, SandboxRuntimeError, PlatonLogEntry
from src.services.models.api import GeneratedExercise, ExerciseMetadata
from src.services.logs_service import get_prompt

from src.core import path_constants
from src.core.config_app import settings
from src.services.output_sanitizer_service import sanitize_generated_exercise

logger = logging.getLogger(__name__)

# Reusable type alias for the SSE progress callback.
ProgressCallback = Optional[Callable[[str, Dict[str, Any]], None]]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Declarative mapping: generated key -> ExerciseData attribute name.
_GENERATED_KEY_TO_ATTRIBUTE: Dict[str, str] = {
    "name": "name",
    "description": "description",
    "title": "titre",
    "statement": "enonce",
    "form": "forme",
    "solution": "solution",
    "sandbox": "sandbox",
    "builder": "construction",
    "grader": "evaluation",
}

# Keys whose values default to [] when falsy.
_LIST_KEYS: Dict[str, str] = {
    "hint": "indications",
    "theories": "theories",
}

# Keys to silently skip.
_IGNORED_KEYS: frozenset = frozenset({"author"})


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


def apply_generated_to_exercise(exercise_data: Any, generated_exercise: GeneratedExercise) -> None:
    """Map a generated exercise dict onto an ExerciseData model in-place."""
    raw = generated_exercise.to_dict()
    exercise_data.sandbox_variables = exercise_data.sandbox_variables or {}

    for key, value in raw.items():
        if key in _IGNORED_KEYS:
            continue

        if key == "metadata" and isinstance(value, dict):
            existing: ExerciseMetadata = exercise_data.metadata or ExerciseMetadata()
            exercise_data.metadata = ExerciseMetadata(
                levels=value.get("levels") or existing.levels,
                topics=value.get("topics") or existing.topics,
                readme=existing.readme if existing.readme is not None else _build_readme_from_llm_metadata(value),
            )

        elif key in _GENERATED_KEY_TO_ATTRIBUTE:
            if key == "name" and isinstance(value, str):
                value = value.replace("_", " ")
            setattr(exercise_data, _GENERATED_KEY_TO_ATTRIBUTE[key], value)

        elif key in _LIST_KEYS:
            setattr(exercise_data, _LIST_KEYS[key], value or [])

        else:
            exercise_data.sandbox_variables[key] = value

    from src.services.workspace_service import workspace_service
    workspace_service.sanitise_exercise_data(exercise_data)


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------

class SandboxCorrectionService:
    """Encapsulates LLM-based correction and retry logic for sandbox failures."""

    def __init__(self, db_session: AsyncSession, temperature: float = 0.0) -> None:
        self._logger = logging.getLogger(__name__)
        self._temperature = temperature
        self._db_session = db_session

    # -- Prompt loading --------------------------------------------------

    async def _load_repair_prompt(self) -> str:
        prompt_entry = await get_prompt(self._db_session, 'exercise_repair')
        return prompt_entry.content

    @staticmethod
    def _load_ple_language_doc() -> str:
        if not settings.REPAIR_INJECT_PLE_DOCS:
            logger.debug("[REPAIR] REPAIR_INJECT_PLE_DOCS=False — skipping langage.mdx injection (~3 570 tokens saved)")
            return ""
        doc_path = path_constants.PLATON_DOCS_DIR / "main" / "programing" / "exercise" / "langage.mdx"
        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            logger.warning("Could not load PLE language doc: %s", exc)
            return "(documentation non disponible)"

    @staticmethod
    def _load_ple_workflow_doc() -> str:
        if not settings.REPAIR_INJECT_PLE_DOCS:
            logger.debug("[REPAIR] REPAIR_INJECT_PLE_DOCS=False — skipping workflow.mdx injection (~1 130 tokens saved)")
            return ""
        doc_path = path_constants.PLATON_DOCS_DIR / "main" / "programing" / "exercise" / "workflow.mdx"
        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            logger.warning("Could not load PLE workflow doc: %s", exc)
            return "(documentation non disponible)"

    @staticmethod
    def _format_component_docs(component_tags: List[str]) -> str:
        try:
            with open(path_constants.COMPONENT_METADATA_PATH, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except OSError as exc:
            logger.warning("Could not load component metadata: %s", exc)
            return "(métadonnées composants non disponibles)"

        lines: List[str] = []
        for tag in component_tags:
            entry = next((c for c in metadata if c.get("tag") == tag), None)
            if not entry:
                continue
            lines.append(f"--- Composant : {entry.get('name', tag)} (tag: {tag}) ---")
            lines.append(f"Catégorie : {entry.get('category', '?')}")
            lines.append(f"Description : {entry.get('description', '')}")
            lines.append(f"Usage : {entry.get('usage', '')}")
            props = entry.get("properties", {})
            if props:
                lines.append("Propriétés :")
                for prop_name, prop_def in props.items():
                    prop_type = prop_def.get("type", "?")
                    prop_desc = prop_def.get("description", "")
                    lines.append(f"  - {prop_name} ({prop_type}) : {prop_desc}")
            lines.append("")
        return "\n".join(lines) if lines else "(aucun composant documenté)"

    @staticmethod
    def _format_conversation_history(conversation_history: Optional[List[Any]]) -> str:
        if not conversation_history:
            return "(aucun historique de conversation)"
        lines: List[str] = ["Historique de la conversation :"]
        for msg in conversation_history:
            if hasattr(msg, "role"):
                role = msg.role
                content = msg.content
            elif isinstance(msg, dict):
                role = msg.get("role", "?")
                content = msg.get("content", "")
            else:
                continue
            lines.append(f"[{role.upper()}] {content}")
        return "\n".join(lines)

    # -- LLM correction calls -------------------------------------------

    @staticmethod
    def _fill_repair_prompt(
        template: str,
        *,
        attempt_number: int,
        max_attempts: int,
        sandbox_error: str,
        error_type: str,
        current_exercise_json: str,
        user_request: str,
        ple_language_doc: str,
        ple_workflow_doc: str,
        component_docs: str,
        conversation_history: str,
    ) -> str:
        """Substitute all placeholders in the repair prompt template.

        Uses sequential ``str.replace()`` instead of ``str.format()`` so that
        values which contain curly-brace sequences (e.g. Python f-strings
        like ``f"result = {n}"`` inside builder code, or PLE syntax like
        ``{{input_box}}``) are never misinterpreted as format placeholders.

        Each replacement is done exactly once on the known placeholder name.
        """
        return (
            template
            .replace("{ple_language_doc}", ple_language_doc)
            .replace("{ple_workflow_doc}", ple_workflow_doc)
            .replace("{component_docs}", component_docs)
            .replace("{user_request}", user_request)
            .replace("{conversation_history}", conversation_history)
            .replace("{current_exercise_json}", current_exercise_json)
            .replace("{attempt_number}", str(attempt_number))
            .replace("{max_attempts}", str(max_attempts))
            .replace("{error_type}", error_type)
            .replace("{sandbox_error}", sandbox_error)
        )

    async def _correct_pure_exercise(
        self,
        original_generated: GeneratedExercise,
        sandbox_error: str,
        user_request: str,
        attempt_number: int,
        max_attempts: int,
        conversation_history: Optional[List[Any]] = None,
        component_tags: Optional[List[str]] = None,
        error_type: str = "compilation",
        llm_calls_accumulator: Optional[List[Any]] = None,
    ) -> GeneratedExercise:
        """Ask the LLM to fix a pure exercise that failed compilation or had runtime errors."""
        self._logger.info(
            "Correcting pure exercise (%s error) -- attempt %d/%d",
            error_type,
            attempt_number,
            max_attempts,
        )
        system_prompt = self._fill_repair_prompt(
            await self._load_repair_prompt(),
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            sandbox_error=sandbox_error,
            error_type=error_type,
            current_exercise_json=json.dumps(original_generated.to_dict(), ensure_ascii=False, indent=2),
            user_request=user_request,
            ple_language_doc=self._load_ple_language_doc(),
            ple_workflow_doc=self._load_ple_workflow_doc(),
            component_docs=self._format_component_docs(component_tags or []),
            conversation_history=self._format_conversation_history(conversation_history),
        )
        llm_result = await chat_with_llm(
            system_prompt=system_prompt,
            user_request=(
                "Analyse l'erreur sandbox ci-dessus, identifie sa cause précise dans le JSON fourni, "
                "et retourne le JSON complet corrigé de l'exercice. "
                "Retourne uniquement le JSON corrigé, sans aucun commentaire."
            ),
            temperature=self._temperature,
            use_fixed_schema=True,
            llm_calls_accumulator=llm_calls_accumulator,
            call_type=f"repair_{error_type}",
        )
        return sanitize_generated_exercise(GeneratedExercise.from_llm_dict(llm_result.parsed))

    async def _correct_config_variables(
        self,
        original_vars: Dict[str, Any],
        sandbox_error: str,
        user_request: str,
        schema_config: List[Dict[str, Any]],
        attempt_number: int,
        max_attempts: int,
    ) -> Dict[str, Any]:
        """Ask the LLM to fix template config variables that failed compilation."""
        self._logger.info(
            "Correcting config variables -- attempt %d/%d",
            attempt_number,
            max_attempts,
        )
        system_prompt = self._fill_repair_prompt(
            await self._load_repair_prompt(),
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            sandbox_error=sandbox_error,
            error_type="compilation",
            current_exercise_json=json.dumps(original_vars, ensure_ascii=False, indent=2),
            user_request=user_request,
            ple_language_doc=self._load_ple_language_doc(),
            ple_workflow_doc=self._load_ple_workflow_doc(),
            component_docs="(non applicable pour les variables de configuration de template)",
            conversation_history="(non applicable pour les variables de configuration de template)",
        )
        llm_result = await chat_with_llm(
            system_prompt=system_prompt,
            user_request=(
                "Corrige les variables de configuration ci-dessus pour que l'exercice "
                "compile sur Platon. Retourne uniquement le JSON corrige."
            ),
            temperature=self._temperature,
            schema_config=schema_config,
        )
        return llm_result.parsed

    # -- High-level orchestration ----------------------------------------

    async def preview_pure_exercise_with_retry(
        self,
        exercise_data: Any,
        generated_exercise: GeneratedExercise,
        user_request: str,
        platon_service: Any,
        progress_callback: ProgressCallback = None,
        conversation_history: Optional[List[Any]] = None,
        llm_calls_accumulator: Optional[List[Any]] = None,
    ) -> RetryResult:
        """Build PLE from *exercise_data*, send to Platon, and auto-correct on failure.

        Mutates *exercise_data* and *generated_exercise* in-place when
        corrections are applied.

        After a successful builder preview, also runs the grader via
        evaluate_exercise so that grader runtime errors are caught and corrected
        in the same LLM round-trip as builder errors.
        """
        from src.services.workspace_service import workspace_service

        component_tags: List[str] = list(exercise_data.components or [])

        async def _preview() -> PreviewResult:
            ple_content = workspace_service.from_json_to_ple(exercise_data)

            # ----------------------------------------------------------------
            # Step 1 — Builder / syntax check via create_exercise_preview.
            # Raises SandboxError (HTTP error) or SandboxRuntimeError (runtime
            # logs) if the builder or the PLE file itself is broken.
            # ----------------------------------------------------------------
            self._logger.info("[SANDBOX CHECK] Step 1/2 — running builder/syntax preview...")
            preview_result = await platon_service.create_exercise_preview(ple=ple_content, plo=None)
            self._logger.info(
                "[SANDBOX CHECK] Step 1/2 — builder/syntax preview PASSED (resource_id=%s, session_id=%s).",
                getattr(preview_result.state, "resource_id", "?"),
                getattr(preview_result.state, "session_id", "?"),
            )

            # ----------------------------------------------------------------
            # Step 2 — Grader check via evaluate_exercise.
            # ----------------------------------------------------------------
            session_id = preview_result.state.session_id if preview_result.state else None

            if not session_id:
                self._logger.warning(
                    "[SANDBOX CHECK] Step 2/2 — skipping grader check: session_id is empty after builder preview."
                )
                return preview_result

            self._logger.info(
                "[SANDBOX CHECK] Step 2/2 — running grader check (session_id=%s)...", session_id
            )
            try:
                await platon_service.evaluate_exercise(session_id)
                self._logger.info("[SANDBOX CHECK] Step 2/2 — grader check PASSED.")
            except (SandboxRuntimeError, SandboxError) as grader_exc:
                self._logger.warning(
                    "[SANDBOX CHECK] Step 2/2 — grader check FAILED: %s", grader_exc
                )
                raise
            except Exception as exc:
                self._logger.error(
                    "[SANDBOX CHECK] Step 2/2 — grader check raised an unexpected error"
                    " (treating as grader failure, will attempt correction): %s",
                    exc,
                )
                raise SandboxRuntimeError(
                    [PlatonLogEntry(message=f"{type(exc).__name__}: {exc}", type="error")],
                    source="grader",
                )

            return preview_result

        async def _correction(error_msg: str, attempt: int, max_attempts: int) -> None:
            if error_msg.startswith("Grader runtime errors detected:"):
                error_type = "grader_runtime"
            elif error_msg.startswith("Sandbox runtime errors detected:"):
                error_type = "runtime"
            else:
                error_type = "compilation"

            self._logger.info(
                "[SANDBOX CORRECTION] Attempt %d/%d — error_type=%s — launching LLM correction.",
                attempt, max_attempts, error_type,
            )
            self._logger.debug("[SANDBOX CORRECTION] Error passed to LLM:\n%s", error_msg)

            corrected = await self._correct_pure_exercise(
                original_generated=generated_exercise,
                sandbox_error=error_msg,
                user_request=user_request,
                attempt_number=attempt,
                max_attempts=max_attempts,
                conversation_history=conversation_history,
                component_tags=component_tags,
                error_type=error_type,
                llm_calls_accumulator=llm_calls_accumulator,
            )
            generated_exercise.name = corrected.name
            generated_exercise.description = corrected.description
            generated_exercise.title = corrected.title
            generated_exercise.statement = corrected.statement
            generated_exercise.form = corrected.form
            generated_exercise.solution = corrected.solution
            generated_exercise.sandbox = corrected.sandbox
            generated_exercise.builder = corrected.builder
            generated_exercise.grader = corrected.grader
            generated_exercise.hint = corrected.hint
            generated_exercise.theories = corrected.theories
            generated_exercise.levels = corrected.levels
            generated_exercise.topics = corrected.topics
            generated_exercise.objectifs_pedagogiques = corrected.objectifs_pedagogiques
            generated_exercise.public_vise = corrected.public_vise
            generated_exercise.prerequis = corrected.prerequis
            generated_exercise.consignes = corrected.consignes
            generated_exercise.extra_fields = corrected.extra_fields
            apply_generated_to_exercise(exercise_data, corrected)
            self._logger.info(
                "[SANDBOX CORRECTION] Attempt %d/%d — LLM correction applied to exercise_data.",
                attempt, max_attempts,
            )

        def _on_retry(attempt: int, max_attempts: int, error_msg: str) -> None:
            if progress_callback is not None:
                result = progress_callback("sandbox_retry", {
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": error_msg,
                })
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)

        return await attempt_with_retry(
            preview_fn=_preview,
            correction_fn=_correction,
            on_retry=_on_retry,
        )

    async def preview_template_with_retry(
        self,
        exercise_data: Any,
        complete_vars: Dict[str, Any],
        user_request: str,
        platon_service: Any,
        progress_callback: ProgressCallback = None,
    ) -> RetryResult:
        """Build PLO from *complete_vars*, send to Platon, and auto-correct on failure.

        Mutates *complete_vars* in-place when corrections are applied.
        """
        async def _preview() -> PreviewResult:
            plo_content = json.dumps(complete_vars)
            ple_content = None
            if exercise_data.template_id:
                ple_content = platon_service.generate_ple_content(exercise_data.template_id)
            return await platon_service.create_exercise_preview(ple=ple_content, plo=plo_content)

        schema_config: List[Dict[str, Any]] = (
            exercise_data.config_variables.get("inputs", [])
            if exercise_data.config_variables
            else []
        )

        async def _correction(error_msg: str, attempt: int, max_attempts: int) -> None:
            corrected = await self._correct_config_variables(
                original_vars=dict(complete_vars),
                sandbox_error=error_msg,
                user_request=user_request,
                schema_config=schema_config,
                attempt_number=attempt,
                max_attempts=max_attempts,
            )
            complete_vars.clear()
            if exercise_data.config_variables and "inputs" in exercise_data.config_variables:
                for param in exercise_data.config_variables["inputs"]:
                    param_name = param.get("name")
                    param_value = param.get("value")
                    if param_name:
                        complete_vars[param_name] = param_value
            complete_vars.update(corrected)

        def _on_retry(attempt: int, max_attempts: int, error_msg: str) -> None:
            if progress_callback is not None:
                result = progress_callback("sandbox_retry", {
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": error_msg,
                })
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)

        return await attempt_with_retry(
            preview_fn=_preview,
            correction_fn=_correction,
            on_retry=_on_retry,
        )
