import asyncio
import inspect
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from src.services.sandbox_correction_service import (
    SandboxCorrectionService,
    apply_generated_to_exercise,
    ProgressCallback,
)
from src.infra.log.db_logger import log_exo_generation
from src.infra.log.models import ExoGenerationLog
from src.services.models.api import ChatRequest, ChatResponse, ExerciseVariant, WorkflowResult
from src.services.models.rag import RetrievedChunk


_UNIVERSAL_TEMPLATE_ID = "95668f95-997f-4ca8-8ba6-2ddb89eb1634" # CHANGER BIEN SÛR, ON LE METTRA DANS LA BDD ET DANS L'INTERFACE ADMIN


def _apply_context_metadata(exercise_data, generation_context) -> None:
    """Override exercise metadata with values from the landing form (generation_context).

    User form inputs are authoritative — levels, domains, and pedagogical objectives
    collected in Step 1 are more reliable than what the LLM guesses from the request.
    Called after apply_generated_to_exercise so context values always win.
    """
    if not generation_context:
        return
    from src.services.models.api import ExerciseMetadata

    existing = exercise_data.metadata or ExerciseMetadata()
    levels = generation_context.niveaux or existing.levels
    topics = generation_context.domaines or existing.topics

    readme = existing.readme
    if not readme:
        lines = []
        if generation_context.objectifs_pedagogiques:
            lines.append(f"## Objectifs pédagogiques\n\n{generation_context.objectifs_pedagogiques}")
        if generation_context.public_vise:
            lines.append(f"## Public visé\n\n{generation_context.public_vise}")
        if generation_context.prerequis:
            lines.append(f"## Prérequis\n\n{generation_context.prerequis}")
        if generation_context.difficulte:
            lines.append(f"## Difficulté\n\n{generation_context.difficulte.capitalize()}")
        readme = "\n\n".join(lines) or None

    exercise_data.metadata = ExerciseMetadata(levels=levels, topics=topics, readme=readme)

_STEP_LOG_DIR = Path("/tmp/agora_steps")


def _write_step_log(component: str, step: str, lines: List[str]) -> None:
    """Write a plain-text debug log for one generation step."""
    try:
        _STEP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        safe_comp = component.replace("/", "_").replace(" ", "_")
        path = _STEP_LOG_DIR / f"{step}__{safe_comp}__{ts}.log"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        logger.info("[STEP LOG] %s", path)
    except Exception as exc:
        logger.warning("[STEP LOG] write failed: %s", exc)


@dataclass(frozen=True)
class WorkflowConfig:
    """Immutable snapshot of all settings the workflow layer needs."""
    platon_base_url: str
    template_score_threshold: float
    num_example_exercises: int
    rag_table_name: str
    rag_log_top_k: int
    generation_temperature: float


def _load_workflow_config() -> WorkflowConfig:
    """Build config using runtime-tuneable values from the database-backed store."""
    from src.core.config_app import settings
    from src.services.runtime_config_service import runtime_config, SettingKey

    return WorkflowConfig(
        platon_base_url=settings.PLATON_BASE_URL,
        template_score_threshold=runtime_config.get_float(SettingKey.TEMPLATE_SCORE_THRESHOLD),
        num_example_exercises=runtime_config.get_int(SettingKey.NUM_EXAMPLE_EXERCISES),
        rag_table_name=settings.RAG_TABLE_NAME,
        rag_log_top_k=runtime_config.get_int(SettingKey.RAG_LOG_TOP_K),
        generation_temperature=runtime_config.get_float(SettingKey.TEMP_GENERATION),
    )


def _get_config() -> WorkflowConfig:
    """Return a fresh config snapshot on every call so runtime changes take effect."""
    return _load_workflow_config()

async def _emit_progress(progress_cb, event: str, data: dict | None = None) -> None:
    if not progress_cb:
        return
    try:
        result = progress_cb(event, data or {})
        if inspect.isawaitable(result):
            await result
    except Exception as e:
        logger.debug(f"Progress callback failed for {event}: {e}")


def _build_resource_overview_url(resource_id: str) -> str:
    cfg = _get_config()
    base = cfg.platon_base_url.rstrip("/")
    if "/api/" in base:
        base = base.split("/api/", 1)[0]
    return f"{base}/resources/{resource_id}/overview"


def _extract_top_resources(chunks, limit: int = 3) -> list[dict]:
    items: list[dict] = []
    for chunk in chunks[:limit]:
        md = getattr(chunk, "metadata", None) or {}
        resource_id = md.get("resource_id") or md.get("platon_id")
        name = md.get("name") or md.get("title")
        if isinstance(resource_id, str) and resource_id.strip():
            rid = resource_id.strip()
            items.append(
                {
                    "resource_id": rid,
                    "name": (name.strip() if isinstance(name, str) and name.strip() else rid),
                    "url": _build_resource_overview_url(rid),
                }
            )
    return items


async def _resolve_top_resource_names(top_resources: list[dict], platon, user_token: str | None) -> list[dict]:
    resolved: list[dict] = []
    for item in top_resources:
        rid = item.get("resource_id")
        name = item.get("name")
        if not isinstance(rid, str) or not rid:
            continue
        final_name = name if isinstance(name, str) and name and name != rid else rid
        if final_name == rid:
            try:
                resource = await platon.get_resource(rid, token=user_token)
                fetched_name = resource.get("name") if isinstance(resource, dict) else None
                if isinstance(fetched_name, str) and fetched_name.strip():
                    final_name = fetched_name.strip()
            except Exception as e:
                logger.debug(f"Could not resolve resource name for {rid}: {e}")
        resolved.append(
            {
                "resource_id": rid,
                "name": final_name,
                "url": item.get("url"),
            }
        )
    return resolved

def _workflow_result_to_response(result: WorkflowResult, fallback_exercise_data, conversation_mode: str | None = None) -> ChatResponse:
    if result.error:
        return ChatResponse(
            error=result.error,
            exercise_data=fallback_exercise_data,
            retry_count=result.retry_count,
            retry_errors=result.retry_errors,
            conversation_mode=conversation_mode,
        )
    return ChatResponse(
        exercise_data=result.exercise_data,
        url=result.url,
        message=result.message,
        retry_count=result.retry_count,
        retry_errors=result.retry_errors,
        conversation_mode=conversation_mode,
    )


def _find_best_template(
    retrieved: List[RetrievedChunk],
    selected_components: Optional[List[str]] = None,
) -> Optional[RetrievedChunk]:
    from src.services.rag.embedding_types import EmbeddingKind
    templates = [
        chunk for chunk in retrieved
        if chunk.metadata.get("kind") == EmbeddingKind.TEMPLATE.value
    ]
    if not templates:
        return None

    if selected_components:
        # Keep only templates whose embedded text declares the selected components.
        # build_exercise_text() writes "Les composants utilisés dans l'exercice: wc-radio-group, …"
        # so a simple substring check is reliable.
        matching = [t for t in templates if any(comp in t.content for comp in selected_components)]
        if not matching:
            logger.info(
                "No template found using selected component(s) %s — falling through to pure generation.",
                selected_components,
            )
            return None
        best = matching[0]
        logger.info(
            "Found %d template(s) matching component(s) %s. Best: name=%s score=%s",
            len(matching), selected_components, best.metadata.get("name"), best.score,
        )
    else:
        best = templates[0]
        logger.info(
            "Found %d template(s) among retrieved resources. Best score: %s, metadata: %s",
            len(templates), best.score, best.metadata,
        )

    if (best.score is not None) and (best.score >= _get_config().template_score_threshold):
        logger.info("Using template score=%.4f name=%s", best.score, best.metadata.get("name"))
        return best
    logger.info(
        "Best template score %.4f below threshold %.4f — falling through to pure generation.",
        best.score or 0.0, _get_config().template_score_threshold,
    )
    return None


async def _load_template_into_exercise(exercise_data, resource_id: str, platon, user_token: str) -> Optional[str]:
    try:
        plc_content = await platon.get_file_content(
            resource_id=resource_id, filename="main.plc", token=user_token
        )
        exercise_data.template_id = resource_id
        exercise_data.config_variables = json.loads(plc_content)
        return None
    except Exception as e:
        return f"Failed to load template config: {str(e)}"


async def _collect_examples(retrieved: List[RetrievedChunk], platon, user_token: str) -> List[Dict[str, Any]]:
    from src.services.rag.embedding_types import EmbeddingKind
    from src.services.workspace_service import truncate_compiled_variables

    examples: List[Dict[str, Any]] = []
    for chunk in retrieved[:_get_config().num_example_exercises]:
        resource_id = chunk.metadata.get("platon_id") if chunk.metadata else None
        if not resource_id:
            logger.warning("Chunk missing platon_id in metadata: %s", chunk.metadata)
            continue
        try:
            compiled_data = await platon.compile_resource_json(resource_id, token=user_token)
            compile_vars = compiled_data.get("variables", {})
            if chunk.metadata.get("kind") == EmbeddingKind.TEMPLATE.value:
                plc_content = await platon.get_file_content(
                    resource_id=resource_id, filename="main.plc", token=user_token
                )
                compile_vars.update(json.loads(plc_content))
            examples.append(truncate_compiled_variables(compile_vars))
        except Exception as e:
            logger.warning("Could not get compile vars for %s: %s", resource_id, e)
    return examples


async def _generate_pure_exercise(
    exercise_data,
    chat_request: ChatRequest,
    platon,
    user_token: str,
    progress_callback: ProgressCallback,
    examples_retrieved: list,
    session_id: str = None,
    is_modification: bool = False,
    conversation_id: str = None,
    username: str = None,
    cancellation_event: asyncio.Event = None,
    generation_context=None,
    pre_selection_result=None,
    pre_llm_calls=None,
) -> ChatResponse:
    from src.services.generation_service import GenerationService
    from src.services.rag.retrieval_service import get_embed_model
    from src.services.component_selection_service import select_components_for_request
    from src.infra.log.models import ComponentSelectionLog

    def _check_cancelled() -> None:
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError("Generation cancelled by user.")

    request_received_at = datetime.now(timezone.utc)
    rag_query = _build_examples_query(chat_request.user_request, exercise_data.components or [])

    llm_calls: List[Dict[str, Any]] = []

    selection_result = None
    component_selection_log = None
    gen_result = None

    try:
        return await _generate_pure_exercise_inner(
            exercise_data, chat_request, platon, user_token, progress_callback,
            examples_retrieved, session_id, is_modification, conversation_id, username,
            cancellation_event, request_received_at, rag_query, llm_calls,
            generation_context=generation_context,
            pre_selection_result=pre_selection_result,
            pre_llm_calls=pre_llm_calls,
        )
    except asyncio.CancelledError:
        raise  # Let cancellation propagate without logging
    except Exception as exc:
        logger.error("Internal error during pure exercise generation: %s", exc, exc_info=True)
        try:
            embed_model = get_embed_model()
            embed_model_name = getattr(embed_model, "model_name", str(embed_model))
        except Exception:
            embed_model_name = "unknown"
        asyncio.ensure_future(log_exo_generation(ExoGenerationLog(
            user_request=chat_request.user_request,
            components=exercise_data.components or [],
            fields_to_modify=chat_request.fields_to_modify or [],
            variables=None,
            file_names=list(chat_request.file_ids or []),
            file_summaries=list(chat_request.file_infos or []),
            conversation_history=list(chat_request.conversation_history or []),
            current_exercise_state=exercise_data.model_dump(),
            retrieved_chunks=examples_retrieved,
            embedding_model=embed_model_name,
            vector_table=_get_config().rag_table_name,
            rag_query=rag_query,
            examples_used=[],
            system_prompt_name="pure_exercise_modification" if is_modification else "pure_exercise",
            llm_raw_output=None,
            llm_output=None,
            llm_provider="unknown",
            llm_model="unknown",
            session_id=session_id,
            conversation_id=conversation_id,
            username=username,
            preview_url=None,
            retry_count=None,
            retry_errors=[str(exc)],
            request_received_at=request_received_at,
            status="error",
            input_tokens=None,
            output_tokens=None,
            llm_request_count=0,
            llm_calls=llm_calls or None,
        )))
        raise


async def _generate_pure_exercise_inner(
    exercise_data,
    chat_request: ChatRequest,
    platon,
    user_token: str,
    progress_callback: ProgressCallback,
    examples_retrieved: list,
    session_id: str,
    is_modification: bool,
    conversation_id: str,
    username: str,
    cancellation_event: asyncio.Event,
    request_received_at: datetime,
    query: str,
    llm_calls: List[Dict[str, Any]],
    generation_context=None,
    pre_selection_result=None,
    pre_llm_calls=None,
) -> ChatResponse:
    from src.services.generation_service import GenerationService
    from src.services.rag.retrieval_service import get_embed_model
    from src.services.component_selection_service import select_components_for_request
    from src.infra.log.models import ComponentSelectionLog

    def _check_cancelled() -> None:
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError("Generation cancelled by user.")

    if pre_llm_calls:
        llm_calls.extend(pre_llm_calls)

    selection_result = None
    component_selection_log = None

    # Run component selection only when no components are already attached
    # (neither historical components on the exercise nor user-selected ones).
    has_components = bool(exercise_data.components) or bool(chat_request.user_selected_components)

    if not has_components:
        await _emit_progress(progress_callback, "component_selection_started", {"value": "Selecting best components for this exercise..."})
        try:
            if pre_selection_result is not None:
                selection_result = pre_selection_result
            else:
                file_summaries = [
                    fi["summary"]
                    for fi in (chat_request.file_infos or [])
                    if isinstance(fi.get("summary"), str) and fi["summary"].strip()
                ]
                comp_request = _build_comp_request(chat_request.user_request, generation_context)
                selection_result = await select_components_for_request(
                    user_request=comp_request,
                    user_priority_tags=[],
                    file_summaries=file_summaries or None,
                    current_components=None,
                    llm_calls_accumulator=llm_calls,
                )
            all_tags = selection_result.all_tags
            if all_tags:
                exercise_data.components = all_tags
            await _emit_progress(
                progress_callback,
                "component_selection_completed",
                {
                    "value": f"Selected {len(all_tags)} component(s).",
                    "selected_tags": all_tags,
                    "user_priority_tags": selection_result.user_priority_tags,
                    "llm_only_tags": selection_result.llm_only_tags,
                },
            )
            component_selection_log = ComponentSelectionLog(
                user_request=chat_request.user_request,
                user_priority_tags=selection_result.user_priority_tags,
                selected_tags=all_tags,
                llm_provider=selection_result.llm_provider,
                llm_model=selection_result.llm_model,
                reasoning=selection_result.reasoning,
            )
        except Exception as exc:
            logger.warning("Component selection step failed, continuing without it: %s", exc)
            selection_result = None
            component_selection_log = None
    else:
        logger.info(
            "Skipping component selection — components already present "
            "(exercise=%s, user_selected=%s).",
            exercise_data.components,
            chat_request.user_selected_components,
        )
        selection_result = None
        component_selection_log = None

    # When components are pre-selected (no LLM selection ran), use them directly
    # as mandatory tags so the component block is built with their documentation.
    explicit_mandatory_tags: List[str] = (
        selection_result.user_priority_tags if selection_result else
        chat_request.user_selected_components or exercise_data.components or []
    )

    _check_cancelled()


    examples = []
    if not is_modification:
        await _emit_progress(progress_callback, "examples_started", {"value": "Collecting example resources..."})
        examples = await _collect_examples(examples_retrieved, platon, user_token)
        await _emit_progress(progress_callback, "examples_completed", {"value": f"Prepared {len(examples)} examples."})

    _check_cancelled()

    if chat_request.file_ids:
        file_info_summary = [
            {"filename": fi.get("filename", fi.get("file_id", "?")), "summary": fi.get("summary")}
            for fi in (chat_request.file_infos or [])
        ]
        await _emit_progress(
            progress_callback,
            "files_summary",
            {"value": f"{len(chat_request.file_ids)} fichier(s) joint(s)", "files": file_info_summary},
        )
        logger.info("Files attached to chat request: %d file(s), ids=%s", len(chat_request.file_ids), chat_request.file_ids)

    generation_service = GenerationService(temperature=_get_config().generation_temperature)
    await _emit_progress(progress_callback, "llm_generation_started", {"value": "Generating exercise content with AI..."})

    gen_result = await generation_service.generate_pure_exercise_with_examples(
        exercise_data=exercise_data,
        user_request=chat_request.user_request,
        examples=examples,
        conversation_history=chat_request.conversation_history,
        fields_to_modify=chat_request.fields_to_modify or [],
        file_ids=chat_request.file_ids or [],
        file_contents=chat_request.file_contents or [],
        mandatory_tags=explicit_mandatory_tags,
        indicative_tags=selection_result.llm_only_tags if selection_result else [],
        llm_reasoning=selection_result.reasoning if selection_result else "",
        is_modification=is_modification,
        llm_calls_accumulator=llm_calls,
    )
    await _emit_progress(
        progress_callback,
        "llm_generation_completed",
        {"value": "AI generation completed.", "generated_keys": list(gen_result.generated_exercise.to_dict().keys())},
    )

    _check_cancelled()

    logger.info("Generated exercise: %s", gen_result.generated_exercise)
    await _emit_progress(progress_callback, "exercise_mapping_started", {"value": "Mapping generated fields into exercise data..."})
    apply_generated_to_exercise(exercise_data, gen_result.generated_exercise)
    _apply_context_metadata(exercise_data, generation_context)
    await _emit_progress(progress_callback, "exercise_mapping_completed", {"value": "Exercise fields mapped."})

    _check_cancelled()
    await _emit_progress(progress_callback, "preview_started", {"value": "Running sandbox preview validation..."})
    retry_result = await SandboxCorrectionService(temperature=_get_config().generation_temperature).preview_pure_exercise_with_retry(
        exercise_data=exercise_data,
        generated_exercise=gen_result.generated_exercise,
        user_request=chat_request.user_request,
        platon_service=platon,
        progress_callback=progress_callback,
        conversation_history=chat_request.conversation_history or [],
        llm_calls_accumulator=llm_calls,
    )

    conversation_mode = "pure"

    if not retry_result.success:
        embed_model = get_embed_model()
        embed_model_name = getattr(embed_model, "model_name", str(embed_model))
        asyncio.ensure_future(log_exo_generation(ExoGenerationLog(
            user_request=chat_request.user_request,
            components=exercise_data.components or [],
            fields_to_modify=chat_request.fields_to_modify or [],
            variables=None,
            file_names=list(chat_request.file_ids or []),
            file_summaries=list(chat_request.file_infos or []),
            conversation_history=list(chat_request.conversation_history or []),
            current_exercise_state=exercise_data.model_dump(),
            retrieved_chunks=examples_retrieved,
            embedding_model=embed_model_name,
            vector_table=_get_config().rag_table_name,
            rag_query=query,
            examples_used=examples,
            system_prompt_name="pure_exercise_modification" if is_modification else "pure_exercise",
            llm_raw_output=gen_result.llm.raw_text or None,
            llm_output=gen_result.llm.parsed,
            llm_provider=gen_result.llm.provider,
            llm_model=gen_result.llm.model,
            session_id=session_id,
            conversation_id=conversation_id,
            username=username,
            preview_url=None,
            retry_count=retry_result.attempts_used if retry_result.attempts_used > 1 else None,
            retry_errors=retry_result.errors_encountered if retry_result.errors_encountered else None,
            component_selection=component_selection_log,
            request_received_at=request_received_at,
            status="failed",
            input_tokens=gen_result.llm.input_tokens,
            output_tokens=gen_result.llm.output_tokens,
            llm_request_count=gen_result.llm.request_count,
            llm_calls=llm_calls or None,
        )))
        return ChatResponse(
            error=f"Preview failed after {retry_result.attempts_used} attempt(s): {retry_result.error}",
            exercise_data=exercise_data,
            retry_count=retry_result.attempts_used,
            retry_errors=retry_result.errors_encountered,
            conversation_mode=conversation_mode,
        )

    await _emit_progress(progress_callback, "preview_completed", {"value": "Sandbox preview validated.", "url": retry_result.data.state.preview_url})
    exercise_data.exercise_id = retry_result.data.resource_id

    embed_model = get_embed_model()
    embed_model_name = getattr(embed_model, "model_name", str(embed_model))
    asyncio.ensure_future(log_exo_generation(ExoGenerationLog(
        user_request=chat_request.user_request,
        components=exercise_data.components or [],
        fields_to_modify=chat_request.fields_to_modify or [],
        variables=None,
        file_names=list(chat_request.file_ids or []),
        file_summaries=list(chat_request.file_infos or []),
        conversation_history=list(chat_request.conversation_history or []),
        current_exercise_state=exercise_data.model_dump(),
        retrieved_chunks=examples_retrieved,
        embedding_model=embed_model_name,
        vector_table=_get_config().rag_table_name,
        rag_query=query,
        examples_used=examples,
        system_prompt_name="pure_exercise_modification" if is_modification else "pure_exercise",
        llm_raw_output=gen_result.llm.raw_text or None,
        llm_output=gen_result.llm.parsed,
        llm_provider=gen_result.llm.provider,
        llm_model=gen_result.llm.model,
        session_id=session_id,
        conversation_id=conversation_id,
        username=username,
        preview_url=retry_result.data.state.preview_url,
        retry_count=retry_result.attempts_used if retry_result.attempts_used > 1 else None,
        retry_errors=retry_result.errors_encountered if retry_result.errors_encountered else None,
        component_selection=component_selection_log,
        request_received_at=request_received_at,
        status="completed",
        input_tokens=gen_result.llm.input_tokens,
        output_tokens=gen_result.llm.output_tokens,
        llm_request_count=gen_result.llm.request_count,
        llm_calls=llm_calls or None,
    )))

    return ChatResponse(
        exercise_data=exercise_data,
        url=retry_result.data.state.preview_url,
        message="Pure exercise generated successfully!" if not is_modification else "Exercise modified successfully!",
        retry_count=retry_result.attempts_used if retry_result.attempts_used > 1 else None,
        retry_errors=retry_result.errors_encountered if retry_result.errors_encountered else None,
        conversation_mode=conversation_mode,
    )




def _exercise_is_empty(exercise_data) -> bool:
    """Return True when the exercise has never been generated (no meaningful content).

    This is the authoritative, stateless way to decide whether an incoming
    request is a first-time generation or a subsequent modification.  It does
    NOT rely on any in-memory signal or conversation_mode field, so it remains
    correct even after the user closes the tab and comes back later.
    """
    has_content = any([
        exercise_data.titre,
        exercise_data.enonce,
        exercise_data.forme,
        exercise_data.construction,
        exercise_data.evaluation,
        bool(exercise_data.component_instances),
        bool(exercise_data.config_variables),
    ])
    return not has_content


def _build_enriched_query(
    user_request: str,
    components: List[str],
    generation_context,
) -> str:
    """Build a semantically rich RAG query for template selection.

    Combines the free-text request with all structured context fields so the
    embedding is close to real exercise/template documents (which contain
    topics, levels, component names, and pedagogical descriptions).
    """
    parts = [user_request]
    if generation_context:
        if generation_context.concept and generation_context.concept.strip():
            parts.append(generation_context.concept)
        parts.extend(generation_context.niveaux or [])
        parts.extend(generation_context.domaines or [])
        if generation_context.difficulte:
            parts.append(generation_context.difficulte)
        if generation_context.objectifs_pedagogiques:
            parts.append(generation_context.objectifs_pedagogiques)
        if generation_context.selected_component:
            parts.extend(generation_context.selected_component)
    parts.extend(components or [])
    return " ".join(p for p in parts if p and p.strip())


def _build_examples_query(user_request: str, components: List[str]) -> str:
    """Build a simpler query for example retrieval (concept + components)."""
    parts = [user_request] + list(components or [])
    return " ".join(p for p in parts if p and p.strip())


async def _generate_hyde_query(
    enriched_query: str,
    generation_context,
    components: List[str],
) -> str:
    """HyDE — Hypothetical Document Embedding for template retrieval.

    Generates a short hypothetical template description that mimics the format
    of real template texts in the vector store.  Its embedding is naturally
    closer to real template vectors than the raw user query, improving recall.
    Falls back to enriched_query silently on any failure.
    """
    from src.infra.llm.llm_wrapper import chat_text_with_llm

    ctx_lines: List[str] = []
    if generation_context:
        if generation_context.niveaux:
            ctx_lines.append(f"Niveaux : {', '.join(generation_context.niveaux)}")
        if generation_context.domaines:
            ctx_lines.append(f"Domaines : {', '.join(generation_context.domaines)}")
        if generation_context.difficulte:
            ctx_lines.append(f"Difficulté : {generation_context.difficulte}")
    if components:
        ctx_lines.append(f"Composants souhaités : {', '.join(components)}")
    ctx_str = "\n".join(ctx_lines)

    system_prompt = ( ## À VOIR SI ON PEUT CHANGER...
        "Tu génères la description d'un template d'exercice PLaTon correspondant à une demande pédagogique.\n"
        "Un template PLaTon est un exercice paramétrable : il a un nom, un concept pédagogique, "
        "des niveaux ciblés, des domaines, une description et des paramètres configurables "
        "(ex : question, réponse, difficulté).\n"
        "Réponds uniquement avec le texte de description structurée, sans introduction ni commentaire."
    )
    user_msg = (
        f"Demande : {enriched_query}"
        + (f"\n\nContexte :\n{ctx_str}" if ctx_str else "")
        + "\n\nGénère la description du template PLaTon correspondant."
    )

    try:
        result = await chat_text_with_llm(system_prompt, user_msg, temperature=0.0)
        if result.text and len(result.text.strip()) > 20:
            logger.debug("HyDE query generated (%d chars)", len(result.text))
            return result.text.strip()
    except Exception as exc:
        logger.warning("HyDE query generation failed — falling back to enriched_query: %s", exc)

    return enriched_query


def _build_universal_template_request(user_request: str, selected_components: List[str]) -> str:
    """Augment user_request with per-component v3 structural specs for the universal template.

    The universal template needs to know which component to generate for and how it
    should be structured.  We inject the system_prompt (role) and the JSON structure
    spec (extracted from phase3_fabrication) so the LLM fills the template variables
    with the right content for the selected component type.
    """
    from src.services.generation_service import _get_v3_component_specs, GenerationService

    specs = _get_v3_component_specs()
    spec_blocks: List[str] = []
    for comp in selected_components:
        tag = _name_to_tag(comp)
        v3 = specs.get(tag)
        if not v3:
            logger.warning("No v3 spec found for component '%s' (tag='%s') — skipping spec injection.", comp, tag)
            continue
        role = v3.get("system_prompt", "").strip()
        structure = GenerationService._extract_v3_structure_spec(v3.get("user_prompt", ""))
        block = f"Composant cible : {tag}"
        if role:
            block += f"\nRôle : {role}"
        if structure:
            block += f"\n{structure}"
        spec_blocks.append(block)

    if not spec_blocks:
        return user_request
    return user_request + "\n\n---\nSpécification du composant à générer :\n\n" + "\n\n".join(spec_blocks)


def _build_universal_ctx(user_request: str, selected_components: List[str], generation_context) -> str:
    """Build the extra_system_context for the universal template call.

    Puts pedagogical requirements from generation_context as explicit mandatory
    constraints so the LLM honours them even when component specs dominate the prompt.
    """
    tags = [_name_to_tag(c) for c in selected_components]
    first_tag = tags[0] if tags else "wc-component"
    lines = [
        "CONTRAINTES OBLIGATOIRES POUR LA GÉNÉRATION :",
        "",
        f"Composant(s) cible : {', '.join(tags)}",
        "",
        "IMPORTANT — Format de la variable JSONExercice :",
        "Tu dois générer un objet JSON respectant la spécification du composant ci-dessous,",
        "puis placer cet objet JSON SÉRIALISÉ EN STRING dans le champ `JSONExercice`.",
        f"Exemple de format attendu : \"JSONExercice\": \"{{\\\"type\\\": \\\"{first_tag}\\\", ...}}\"",
        "Ne laisse PAS `JSONExercice` vide.",
        "",
        "Génère un contenu 100 % original basé sur la demande ci-dessous — pas d'exemple Python.",
    ]

    if generation_context:
        if generation_context.niveaux:
            lines.append(f"Niveau(x) : {', '.join(generation_context.niveaux)}")
        if generation_context.domaines:
            lines.append(f"Domaine(s) : {', '.join(generation_context.domaines)}")
        if generation_context.difficulte:
            lines.append(f"Difficulté : {generation_context.difficulte}")
        if generation_context.objectifs_pedagogiques:
            lines.append(f"Objectifs pédagogiques : {generation_context.objectifs_pedagogiques}")
        if generation_context.public_vise:
            lines.append(f"Public visé : {generation_context.public_vise}")
        if generation_context.prerequis:
            lines.append(f"Prérequis : {generation_context.prerequis}")

    lines += [
        "",
        "Le contenu de l'exercice (questions, réponses, thème) DOIT refléter fidèlement",
        "la demande de l'utilisateur ci-dessous — pas un sujet générique :",
        f'  « {user_request[:400]} »',
    ]

    return "\n".join(lines)


def _build_comp_request(user_request: str, generation_context) -> str:
    """Build the enriched request string for component selection."""
    parts = [user_request]
    if generation_context:
        if generation_context.concept and generation_context.concept.strip():
            parts.append(generation_context.concept)
        if generation_context.selected_component:
            parts.append(
                f"Composants souhaités par l'enseignant: {', '.join(generation_context.selected_component)}"
            )
        parts.extend(generation_context.niveaux or [])
        parts.extend(generation_context.domaines or [])
        if generation_context.objectifs_pedagogiques:
            parts.append(generation_context.objectifs_pedagogiques)
    return "\n".join(p for p in parts if p and p.strip())


def _tag_to_name(tag: str) -> str:
    """Return a human-readable component name from its tag, falling back to the tag itself."""
    from src.core import path_constants
    import json as _json
    try:
        with open(path_constants.COMPONENT_METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = _json.load(f)
        entry = next((c for c in metadata if c.get("tag") == tag), None)
        return entry["name"] if entry else tag
    except Exception:
        return tag


def _name_to_tag(name: str) -> str:
    """Return the component tag (e.g. 'wc-checkbox-group') from a name ('CheckboxGroup').

    Falls back to the input unchanged so callers that already hold a tag still work.
    """
    from src.core import path_constants
    import json as _json
    try:
        with open(path_constants.COMPONENT_METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = _json.load(f)
        entry = next(
            (c for c in metadata if c.get("name") == name or c.get("tag") == name),
            None,
        )
        return entry["tag"] if entry else name
    except Exception:
        return name


async def _generate_one_variant(
    component_tag: str,
    base_exercise_data,
    chat_request: ChatRequest,
    user_token: str,
    generation_context,
    templates_retrieved: Optional[List[RetrievedChunk]] = None,
    cancellation_event: asyncio.Event = None,
    session_id: str = None,
    conversation_id: str = None,
    username: str = None,
) -> ExerciseVariant:
    """Generate one exercise variant for a single component.

    Process (mirrors the single-component path in handle_chat):
    1. Find the best specific template for this component in templates_retrieved.
    2. If found: load it and generate with it.
    3. If not: try the universal template.
    4. If that also fails: fall through to pure exercise generation.
    """
    from src.services.models.api import ExerciseData
    from src.services.platon_service import platon_service as platon

    exercise_copy = ExerciseData(**base_exercise_data.model_dump())
    component_name = _tag_to_name(component_tag)

    def _err(msg: str) -> ExerciseVariant:
        return ExerciseVariant(component_tag=component_tag, component_name=component_name,
                               exercise_data=exercise_copy, url="", error=msg)

    # Step 1 — look for a component-specific template in the already-retrieved results.
    best_template = _find_best_template(templates_retrieved or [], selected_components=[component_tag])

    _write_step_log(component_tag, "1_rag", [
        f"=== RAG TEMPLATE SEARCH ===",
        f"Component : {component_tag}",
        f"User request : {chat_request.user_request}",
        f"",
        f"Total templates retrieved (shared pool): {len(templates_retrieved or [])}",
        f"",
        f"--- ALL RETRIEVED TEMPLATES ---",
        *[
            f"  [{i+1}] score={c.score:.3f}  id={c.metadata.get('platon_id') or c.metadata.get('resource_id')}  "
            f"kind={c.metadata.get('kind')}  content={c.content[:120]!r}"
            for i, c in enumerate(templates_retrieved or [])
        ],
        f"",
        f"--- BEST MATCH FOR COMPONENT '{component_tag}' ---",
        (
            f"  resource_id={best_template.metadata.get('resource_id') or best_template.metadata.get('platon_id')}  "
            f"score={best_template.score:.3f}  content={best_template.content[:200]!r}"
            if best_template else "  No matching template found."
        ),
    ])

    if best_template is not None:
        resource_id = best_template.metadata.get("resource_id") or best_template.metadata.get("platon_id")
        if resource_id:
            load_err = await _load_template_into_exercise(exercise_copy, resource_id, platon, user_token)
            if not load_err:
                try:
                    result = await generate_and_process_template(
                        exercise_copy, chat_request.user_request,
                        chat_request.conversation_history, chat_request.fields_to_modify or [],
                        user_token, progress_callback=None,
                        session_id=session_id, is_modification=False,
                        cancellation_event=cancellation_event,
                        conversation_id=conversation_id, username=username,
                    )
                    if not result.error:
                        return ExerciseVariant(component_tag=component_tag, component_name=component_name,
                                              exercise_data=result.exercise_data, url=result.url or "",
                                              error=None)
                    logger.warning("Variant %s: specific template returned sandbox error (%s) — trying universal.", component_tag, result.error)
                except Exception as exc:
                    logger.warning("Variant %s: specific template generation failed (%s) — trying universal.", component_tag, exc)
                exercise_copy = ExerciseData(**base_exercise_data.model_dump())

    # Step 2 — fall back to the universal template.
    enriched_request = _build_universal_template_request(chat_request.user_request, [component_tag])
    universal_ctx = _build_universal_ctx(chat_request.user_request, [component_tag], generation_context)
    universal_err = await _load_template_into_exercise(exercise_copy, _UNIVERSAL_TEMPLATE_ID, platon, user_token)

    _univ_result_lines: List[str] = []
    _univ_result: Optional[Any] = None
    if not universal_err:
        try:
            _univ_result = await generate_and_process_template(
                exercise_copy, enriched_request,
                chat_request.conversation_history, chat_request.fields_to_modify or [],
                user_token, progress_callback=None,
                session_id=session_id, is_modification=False,
                cancellation_event=cancellation_event,
                conversation_id=conversation_id, username=username,
                extra_system_context=universal_ctx, skip_default_values=True,
            )
            if _univ_result.error:
                _univ_result_lines = [f"RESULT : FAILED", f"ERROR  : {_univ_result.error}"]
                logger.warning("Variant %s: universal template returned sandbox error (%s) — trying pure.", component_tag, _univ_result.error)
            else:
                _write_step_log(component_tag, "2_universal_template", [
                    f"=== UNIVERSAL TEMPLATE GENERATION ===",
                    f"Component      : {component_tag}",
                    f"Template ID    : {_UNIVERSAL_TEMPLATE_ID}",
                    f"Load error     : None",
                    f"",
                    f"--- ENRICHED REQUEST ---",
                    enriched_request,
                    f"",
                    f"--- RESULT ---",
                    f"RESULT : SUCCESS",
                    f"URL    : {_univ_result.url}",
                ])
                return ExerciseVariant(component_tag=component_tag, component_name=component_name,
                                       exercise_data=_univ_result.exercise_data, url=_univ_result.url or "",
                                       error=None)
        except Exception as exc:
            _univ_result_lines = [f"RESULT : EXCEPTION", f"ERROR  : {exc}"]
            logger.warning("Variant %s: universal template generation failed (%s) — trying pure.", component_tag, exc)
    else:
        _univ_result_lines = [f"RESULT : LOAD FAILED", f"LOAD ERROR : {universal_err}"]

    _write_step_log(component_tag, "2_universal_template", [
        f"=== UNIVERSAL TEMPLATE GENERATION ===",
        f"Component      : {component_tag}",
        f"Template ID    : {_UNIVERSAL_TEMPLATE_ID}",
        f"Load error     : {universal_err or 'None'}",
        f"",
        f"--- ENRICHED REQUEST ---",
        enriched_request,
        f"",
        f"--- UNIVERSAL CONTEXT (first 800 chars) ---",
        (universal_ctx or "")[:800],
        f"",
        f"--- RESULT ---",
        *_univ_result_lines,
    ])
    exercise_copy = ExerciseData(**base_exercise_data.model_dump())

    # Step 3 — last resort: pure exercise generation (no template).
    try:
        exercise_copy.components = [component_tag]
        pure_request = ChatRequest(
            exercise_state=exercise_copy,
            user_request=chat_request.user_request,
            user_selected_components=[component_tag],
            conversation_history=chat_request.conversation_history,
            fields_to_modify=chat_request.fields_to_modify or [],
            file_ids=chat_request.file_ids or [],
            conversation_mode=chat_request.conversation_mode,
            force_pure_exercise=True,
            conversation_id=chat_request.conversation_id,
            generation_context=chat_request.generation_context,
        )
        pure_resp = await _generate_pure_exercise(
            exercise_copy, pure_request, platon, user_token, progress_callback=None,
            examples_retrieved=[], session_id=session_id, is_modification=False,
            conversation_id=conversation_id, username=username,
            cancellation_event=cancellation_event, generation_context=generation_context,
        )
        ex_dump = {}
        try:
            ex_dump = (pure_resp.exercise_data or exercise_copy).model_dump()
        except Exception:
            pass
        _write_step_log(component_tag, "3_pure_generation", [
            f"=== PURE EXERCISE GENERATION ===",
            f"Component      : {component_tag}",
            f"User request   : {chat_request.user_request}",
            f"Exercise components passed : {exercise_copy.components}",
            f"",
            f"--- RESULT ---",
            f"STATUS : {'SUCCESS' if not pure_resp.error else 'FAILED'}",
            f"URL    : {pure_resp.url or '(none)'}",
            f"ERROR  : {pure_resp.error or 'None'}",
            f"",
            f"--- GENERATED EXERCISE DATA ---",
            json.dumps(ex_dump, ensure_ascii=False, indent=2, default=str),
        ])
        return ExerciseVariant(component_tag=component_tag, component_name=component_name,
                               exercise_data=pure_resp.exercise_data or exercise_copy,
                               url=pure_resp.url or "", error=pure_resp.error)
    except Exception as exc:
        _write_step_log(component_tag, "3_pure_generation", [
            f"=== PURE EXERCISE GENERATION ===",
            f"Component      : {component_tag}",
            f"",
            f"--- RESULT ---",
            f"STATUS : EXCEPTION",
            f"ERROR  : {exc}",
        ])
        logger.exception("Variant generation failed for component %s", component_tag)
        return _err(str(exc))


async def handle_chat(
    chat_request: ChatRequest,
    user_token: str = None,
    progress_callback: ProgressCallback = None,
    session_id: str = None,
    conversation_id: str = None,
    username: str = None,
    cancellation_event: asyncio.Event = None,
) -> ChatResponse:
    from src.services.platon_service import platon_service as platon
    from src.services.rag.retrieval_service import retrieval_service
    from src.services.workspace_service import workspace_service

    def _check_cancelled() -> None:
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError("Generation cancelled by user.")

    logger.info("chat request: %s", chat_request.user_request)

    exercise_data = chat_request.exercise_state
    workspace_service.sanitise_exercise_data(exercise_data)

    is_subsequent = not _exercise_is_empty(exercise_data)

    logger.info(
        "is_subsequent=%s (data-driven) | force_pure_exercise=%s",
        is_subsequent,
        chat_request.force_pure_exercise,
    )

    if is_subsequent:
        locked_mode = "template" if exercise_data.config_variables else "pure"
        logger.info("Subsequent request — locked mode=%s (derived from exercise state)", locked_mode)
        await _emit_progress(progress_callback, "generation_mode", {"mode": locked_mode, "mode_label": locked_mode})

        _check_cancelled()

        if locked_mode == "template":
            result = await generate_and_process_template(
                exercise_data, chat_request.user_request,
                chat_request.conversation_history, chat_request.fields_to_modify or [],
                user_token, progress_callback=progress_callback,
                session_id=session_id,
                is_modification=True,
                cancellation_event=cancellation_event,
                conversation_id=conversation_id,
                username=username,
            )
            return _workflow_result_to_response(result, exercise_data, conversation_mode=locked_mode)

        return await _generate_pure_exercise(
            exercise_data, chat_request, platon, user_token, progress_callback,
            examples_retrieved=[],
            session_id=session_id,
            is_modification=True,
            conversation_id=conversation_id,
            username=username,
            cancellation_event=cancellation_event,
        )

    ctx = chat_request.generation_context
    enriched_query = _build_enriched_query(
        chat_request.user_request, exercise_data.components or [], ctx
    )
    examples_query = _build_examples_query(chat_request.user_request, exercise_data.components or [])

    ctx_components = ctx.selected_component if ctx else []
    has_components = (
        bool(exercise_data.components)
        or bool(chat_request.user_selected_components)
        or bool(ctx_components)
    )
    # Pre-populate exercise components from the landing form if not yet set.
    if ctx_components and not exercise_data.components:
        exercise_data.components = list(ctx_components)
    comp_request = _build_comp_request(chat_request.user_request, ctx)
    file_summaries_for_comp = [
        fi["summary"]
        for fi in (chat_request.file_infos or [])
        if isinstance(fi.get("summary"), str) and fi["summary"].strip()
    ]
    pre_llm_calls: List[Dict[str, Any]] = []

    async def _run_comp_selection():
        if has_components:
            return None
        from src.services.component_selection_service import select_components_for_request as _sel
        return await _sel(
            user_request=comp_request,
            user_priority_tags=[],
            file_summaries=file_summaries_for_comp or None,
            current_components=None,
            llm_calls_accumulator=pre_llm_calls,
        )

    await _emit_progress(progress_callback, "retrieval_started", {"value": "Searching similar resources..."})
    _check_cancelled()

    cfg = _get_config()

    async def _retrieve_templates_with_hyde() -> list:
        # HyDE: generate a hypothetical template description, then search with it.
        # Runs in the same gather arm as examples + comp selection — no added latency.
        hyde_q = await _generate_hyde_query(
            enriched_query, ctx, exercise_data.components or []
        )
        return await asyncio.to_thread(
            retrieval_service.retrieve_templates,
            query=hyde_q,
            top_k=cfg.rag_log_top_k,
        )

    # Template retrieval (with HyDE), example retrieval, and component selection run in parallel.
    # HyDE + template search is one async arm — its LLM call (~1s) is hidden behind comp_selection (~3s).
    templates_retrieved, examples_retrieved, pre_selection_result = await asyncio.gather(
        _retrieve_templates_with_hyde(),
        asyncio.to_thread(
            retrieval_service.retrieve_examples,
            query=examples_query,
            top_k=cfg.num_example_exercises,
        ),
        _run_comp_selection(),
    )

    if not templates_retrieved and not examples_retrieved:
        return ChatResponse(error="No similar resources found for generation.", exercise_data=exercise_data)

    top_resources = _extract_top_resources(templates_retrieved or examples_retrieved, limit=3)
    top_resources = await _resolve_top_resource_names(top_resources, platon, user_token)
    await _emit_progress(
        progress_callback,
        "retrieval_completed",
        {
            "value": f"Retrieved {len(templates_retrieved)} template(s), {len(examples_retrieved)} example(s).",
            "top_resources": top_resources,
        },
    )

    _check_cancelled()

    if chat_request.force_pure_exercise:
        logger.info("force_pure_exercise=True — skipping template selection")
        await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_sans_template", "mode_label": "exercise sans template"})
        return await _generate_pure_exercise(
            exercise_data, chat_request, platon, user_token, progress_callback,
            examples_retrieved=examples_retrieved,
            session_id=session_id,
            is_modification=False,
            conversation_id=conversation_id,
            username=username,
            cancellation_event=cancellation_event,
            generation_context=ctx,
            pre_selection_result=pre_selection_result,
            pre_llm_calls=pre_llm_calls,
        )

    effective_components = (
        pre_selection_result.all_tags
        if pre_selection_result and pre_selection_result.all_tags
        else (exercise_data.components or [])
    ) or None

    # Multiple components → always generate one variant per component in parallel,
    # regardless of whether a specific template was found. Each variant uses the
    # universal template independently so components don't interfere with each other.
    if effective_components and len(effective_components) > 1:
        _check_cancelled()
        await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_avec_template", "mode_label": "exercise avec template universel"})
        await _emit_progress(
            progress_callback,
            "template_loading_started",
            {"value": f"Generating {len(effective_components)} exercise variants in parallel…"},
        )
        await _emit_progress(
            progress_callback,
            "template_loading_completed",
            {"value": f"Generating {len(effective_components)} exercise variants in parallel…"},
        )
        _check_cancelled()
        tasks = [
            _generate_one_variant(
                tag, exercise_data, chat_request, user_token, ctx,
                templates_retrieved=templates_retrieved,
                cancellation_event=cancellation_event,
                session_id=session_id,
                conversation_id=conversation_id,
                username=username,
            )
            for tag in effective_components
        ]
        variants: List[ExerciseVariant] = list(await asyncio.gather(*tasks))
        successful = [v for v in variants if not v.error]
        logger.info("Parallel variant generation: %d/%d succeeded", len(successful), len(variants))
        await _emit_progress(progress_callback, "variants_generated", {"count": len(successful), "total": len(variants)})
        if not successful:
            return ChatResponse(error="All parallel variant generations failed.", exercise_data=exercise_data)
        return ChatResponse(
            variants=variants,
            exercise_data=successful[0].exercise_data,
            url=successful[0].url,
            message=f"{len(successful)} variante(s) générée(s) avec succès.",
            conversation_mode="template",
        )

    # Single component — try best specific template first, then universal, then pure.
    best_template = _find_best_template(templates_retrieved, selected_components=effective_components)
    if best_template is not None:
        resource_id = best_template.metadata.get("resource_id") or best_template.metadata.get("platon_id")
        if not resource_id:
            return ChatResponse(error="Template found but missing resource_id in metadata", exercise_data=exercise_data)
        logger.info("Best template match: resource_id=%s, score=%.2f", resource_id, best_template.score or 0)
        await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_avec_template", "mode_label": "exercise avec template"})
        await _emit_progress(progress_callback, "template_loading_started", {"value": f"Loading template {resource_id}..."})

        _check_cancelled()

        error = await _load_template_into_exercise(exercise_data, resource_id, platon, user_token)
        if error:
            return ChatResponse(error=error, exercise_data=exercise_data)
        await _emit_progress(progress_callback, "template_loading_completed", {"value": "Template configuration loaded."})

        _check_cancelled()

        result = await generate_and_process_template(
            exercise_data, chat_request.user_request,
            chat_request.conversation_history, chat_request.fields_to_modify or [],
            user_token, progress_callback=progress_callback,
            session_id=session_id,
            is_modification=False,
            cancellation_event=cancellation_event,
            conversation_id=conversation_id,
            username=username,
        )
        return _workflow_result_to_response(result, exercise_data, conversation_mode="template")

    # No specific template — try universal template for single component.
    if effective_components:
        _check_cancelled()
        await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_avec_template", "mode_label": "exercise avec template universel"})
        await _emit_progress(progress_callback, "template_loading_started", {"value": f"Loading universal template {_UNIVERSAL_TEMPLATE_ID}..."})
        universal_error = await _load_template_into_exercise(
            exercise_data, _UNIVERSAL_TEMPLATE_ID, platon, user_token
        )
        if not universal_error:
            await _emit_progress(progress_callback, "template_loading_completed", {"value": "Universal template configuration loaded."})
            _check_cancelled()
            enriched_request = _build_universal_template_request(
                chat_request.user_request, effective_components
            )
            universal_ctx = _build_universal_ctx(
                chat_request.user_request, effective_components, ctx
            )
            result = await generate_and_process_template(
                exercise_data, enriched_request,
                chat_request.conversation_history, chat_request.fields_to_modify or [],
                user_token, progress_callback=progress_callback,
                session_id=session_id,
                is_modification=False,
                cancellation_event=cancellation_event,
                conversation_id=conversation_id,
                username=username,
                extra_system_context=universal_ctx,
                skip_default_values=True,
            )
            if not result.error:
                return _workflow_result_to_response(result, exercise_data, conversation_mode="template")
            logger.warning(
                "Universal template %s returned sandbox error (%s) — falling through to pure generation.",
                _UNIVERSAL_TEMPLATE_ID, result.error,
            )
            exercise_data.template_id = None
            exercise_data.config_variables = {}
        else:
            logger.warning(
                "Universal template %s failed to load (%s) — falling through to pure generation.",
                _UNIVERSAL_TEMPLATE_ID, universal_error,
            )

    await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_sans_template", "mode_label": "exercise sans template"})
    return await _generate_pure_exercise(
        exercise_data, chat_request, platon, user_token, progress_callback,
        examples_retrieved=examples_retrieved,
        session_id=session_id,
        is_modification=False,
        conversation_id=conversation_id,
        username=username,
        cancellation_event=cancellation_event,
        generation_context=ctx,
        pre_selection_result=pre_selection_result,
        pre_llm_calls=pre_llm_calls,
    )



async def process_exercise_generation(
    exercise_data,
    generated_vars: Any,
    user_request: str = "",
    user_token: str = None,
    progress_callback: ProgressCallback = None,
) -> WorkflowResult:
    from src.services.platon_service import platon_service as platon

    await _emit_progress(progress_callback, "exercise_mapping_started", {"value": "Merging generated template variables..."})
    complete_vars: Dict[str, Any] = {}
    if exercise_data.config_variables and "inputs" in exercise_data.config_variables:
        for param in exercise_data.config_variables["inputs"]:
            param_name = param.get("name")
            if param_name:
                complete_vars[param_name] = param.get("value")
    complete_vars.update(generated_vars)
    await _emit_progress(progress_callback, "exercise_mapping_completed", {"value": f"Merged {len(complete_vars)} variables."})

    await _emit_progress(progress_callback, "preview_started", {"value": "Running sandbox preview validation..."})
    retry_result = await SandboxCorrectionService(temperature=_get_config().generation_temperature).preview_template_with_retry(
        exercise_data=exercise_data,
        complete_vars=complete_vars,
        user_request=user_request,
        platon_service=platon,
        progress_callback=progress_callback,
    )

    if not retry_result.success:
        return WorkflowResult(
            exercise_data=exercise_data,
            url="",
            message="",
            error=f"Preview failed after {retry_result.attempts_used} attempt(s): {retry_result.error}",
            retry_count=retry_result.attempts_used,
            retry_errors=retry_result.errors_encountered,
        )

    await _emit_progress(progress_callback, "preview_completed", {"value": "Sandbox preview validated.", "url": retry_result.data.state.preview_url})

    if exercise_data.config_variables and "inputs" in exercise_data.config_variables:
        for param in exercise_data.config_variables["inputs"]:
            param_name = param.get("name")
            if param_name in complete_vars:
                param["value"] = complete_vars[param_name]

    exercise_data.exercise_id = retry_result.data.resource_id
    logger.info("Complete vars (existing + generated): %s", complete_vars)

    return WorkflowResult(
        exercise_data=exercise_data,
        url=retry_result.data.state.preview_url,
        message="les nouveaux paramètres du modèles sont générés avec success !",
        retry_count=retry_result.attempts_used if retry_result.attempts_used > 1 else None,
        retry_errors=retry_result.errors_encountered if retry_result.errors_encountered else None,
    )


async def generate_and_process_template(
    exercise_data,
    user_request: str,
    conversation_history,
    fields_to_modify: List[str],
    user_token: str,
    progress_callback: ProgressCallback = None,
    session_id: str = None,
    is_modification: bool = False,
    cancellation_event: asyncio.Event = None,
    conversation_id: str = None,
    username: str = None,
    extra_system_context: str = None,
    skip_default_values: bool = False,
) -> WorkflowResult:
    from src.services.generation_service import GenerationService
    from src.services.rag.retrieval_service import retrieval_service, get_embed_model

    def _check_cancelled() -> None:
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError("Generation cancelled by user.")

    request_received_at = datetime.now(timezone.utc)

    try:
        generation_service = GenerationService(temperature=_get_config().generation_temperature)
        await _emit_progress(progress_callback, "llm_generation_started", {"value": "Generating template parameters with AI..."})
        gen_result = await generation_service.generate_config_variables(
            exercise_data=exercise_data,
            user_request=user_request,
            conversation_history=conversation_history,
            fields_to_modify=fields_to_modify,
            is_modification=is_modification,
            extra_system_context=extra_system_context,
            skip_default_values=skip_default_values,
        )
        await _emit_progress(
            progress_callback,
            "llm_generation_completed",
            {"value": "Template parameter generation completed.", "generated_keys": list(gen_result.variables.keys()) if isinstance(gen_result.variables, dict) else []},
        )
        logger.info("Generated config variables: %s", gen_result.variables)

        _check_cancelled()

        query = user_request + " " + " ".join(exercise_data.components or [])
        retrieve_k = max(_get_config().rag_log_top_k, _get_config().num_example_exercises)
        retrieved = retrieval_service.retrieve_resources(query=query, top_k=retrieve_k)

        embed_model = get_embed_model()
        embed_model_name = getattr(embed_model, "model_name", str(embed_model))

        workflow_result = await process_exercise_generation(
            exercise_data,
            gen_result.variables,
            user_request=user_request,
            user_token=user_token,
            progress_callback=progress_callback,
        )

        system_prompt_name = "template_exercise_modification" if is_modification else "template_exercise"
        asyncio.ensure_future(log_exo_generation(ExoGenerationLog(
            user_request=user_request,
            components=exercise_data.components or [],
            fields_to_modify=fields_to_modify or [],
            variables=exercise_data.config_variables,
            file_names=[],
            file_summaries=[],
            conversation_history=list(conversation_history or []),
            current_exercise_state=exercise_data.model_dump(),
            retrieved_chunks=retrieved,
            embedding_model=embed_model_name,
            vector_table=_get_config().rag_table_name,
            rag_query=query,
            examples_used=[],
            system_prompt_name=system_prompt_name,
            llm_raw_output=gen_result.llm.raw_text or None,
            llm_output=gen_result.variables if isinstance(gen_result.variables, dict) else None,
            llm_provider=gen_result.llm.provider,
            llm_model=gen_result.llm.model,
            session_id=session_id,
            conversation_id=conversation_id,
            username=username,
            preview_url=workflow_result.url if not workflow_result.error else None,
            retry_count=workflow_result.retry_count,
            retry_errors=workflow_result.retry_errors,
            request_received_at=request_received_at,
            status="completed" if not workflow_result.error else "failed",
            input_tokens=gen_result.llm.input_tokens,
            output_tokens=gen_result.llm.output_tokens,
            llm_request_count=gen_result.llm.request_count,
        )))

        return workflow_result

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Internal error during template generation: %s", exc, exc_info=True)
        try:
            embed_model = get_embed_model()
            embed_model_name = getattr(embed_model, "model_name", str(embed_model))
        except Exception:
            embed_model_name = "unknown"
        query = user_request + " " + " ".join(exercise_data.components or [])
        asyncio.ensure_future(log_exo_generation(ExoGenerationLog(
            user_request=user_request,
            components=exercise_data.components or [],
            fields_to_modify=fields_to_modify or [],
            variables=exercise_data.config_variables,
            file_names=[],
            file_summaries=[],
            conversation_history=list(conversation_history or []),
            current_exercise_state=exercise_data.model_dump(),
            retrieved_chunks=[],
            embedding_model=embed_model_name,
            vector_table=_get_config().rag_table_name,
            rag_query=query,
            examples_used=[],
            system_prompt_name="template_exercise_modification" if is_modification else "template_exercise",
            llm_raw_output=None,
            llm_output=None,
            llm_provider="unknown",
            llm_model="unknown",
            session_id=session_id,
            conversation_id=conversation_id,
            username=username,
            preview_url=None,
            retry_count=None,
            retry_errors=[str(exc)],
            request_received_at=request_received_at,
            status="error",
            input_tokens=None,
            output_tokens=None,
            llm_request_count=0,
        )))
        raise

