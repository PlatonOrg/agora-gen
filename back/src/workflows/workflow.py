import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from src.services.sandbox_correction_service import (
    SandboxCorrectionService,
    apply_generated_to_exercise,
    ProgressCallback,
)
from src.infra.log.db_logger import log_exo_generation
from src.infra.log.models import ExoGenerationLog
from src.services.models.api import ChatRequest, ChatResponse, WorkflowResult
from src.services.models.rag import RetrievedChunk


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
        template_score_threshold=settings.TEMPLATE_SCORE_THRESHOLD,
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


def _find_best_template(retrieved: List[RetrievedChunk]) -> Optional[RetrievedChunk]:
    from src.services.rag.embedding_types import EmbeddingKind
    templates = [
        chunk for chunk in retrieved
        if chunk.metadata.get("kind") == EmbeddingKind.TEMPLATE.value
    ]
    if not templates:
        return None
    best = templates[0]
    logger.info(f"Found {len(templates)} template(s) among retrieved resources. Best score: {best.score}, metadata: {best.metadata}")
    if (best.score is not None) and (best.score >= _get_config().template_score_threshold):
        logger.info("returning best template with score %.2f and metadata %s", best.score, best.metadata)
        return best
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
    retrieved: list,
    session_id: str = None,
    is_modification: bool = False,
    conversation_id: str = None,
    username: str = None,
    cancellation_event: asyncio.Event = None,
) -> ChatResponse:
    from src.services.generation_service import GenerationService
    from src.services.rag.retrieval_service import get_embed_model
    from src.services.component_selection_service import select_components_for_request
    from src.infra.log.models import ComponentSelectionLog

    def _check_cancelled() -> None:
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError("Generation cancelled by user.")

    request_received_at = datetime.now(timezone.utc)
    query = chat_request.user_request + " " + " ".join(exercise_data.components or [])

    llm_calls: List[Dict[str, Any]] = []

    selection_result = None
    component_selection_log = None

    if not is_modification:
        await _emit_progress(progress_callback, "component_selection_started", {"value": "Selecting best components for this exercise..."})
        try:
            file_summaries = [
                fi["summary"]
                for fi in (chat_request.file_infos or [])
                if isinstance(fi.get("summary"), str) and fi["summary"].strip()
            ]
            selection_result = await select_components_for_request(
                user_request=chat_request.user_request,
                user_priority_tags=chat_request.user_selected_components or [],
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

    _check_cancelled()

    if is_modification:
        established = list(exercise_data.components or [])
        newly_attached = [t for t in (chat_request.user_selected_components or []) if t not in established]
        if newly_attached:
            exercise_data.components = established + newly_attached
            logger.info("Modification: merged %d newly attached component(s): %s", len(newly_attached), newly_attached)
        mandatory_tags = newly_attached
        historical_tags = established

    examples = []
    if not is_modification:
        await _emit_progress(progress_callback, "examples_started", {"value": "Collecting example resources..."})
        examples = await _collect_examples(retrieved[:_get_config().num_example_exercises], platon, user_token)
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
        mandatory_tags=mandatory_tags if is_modification else (selection_result.user_priority_tags if selection_result else []),
        indicative_tags=historical_tags if is_modification else (selection_result.llm_only_tags if selection_result else []),
        llm_reasoning="" if is_modification else (selection_result.reasoning if selection_result else ""),
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
            retrieved_chunks=retrieved,
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
        retrieved_chunks=retrieved,
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
            )
            return _workflow_result_to_response(result, exercise_data, conversation_mode=locked_mode)

        return await _generate_pure_exercise(
            exercise_data, chat_request, platon, user_token, progress_callback,
            retrieved=[],
            session_id=session_id,
            is_modification=True,
            conversation_id=conversation_id,
            username=username,
            cancellation_event=cancellation_event,
        )

    query = chat_request.user_request + " " + " ".join(exercise_data.components or [])
    await _emit_progress(progress_callback, "retrieval_started", {"value": "Searching similar resources..."})

    _check_cancelled()

    retrieve_k = max(_get_config().rag_log_top_k, _get_config().num_example_exercises)
    retrieved = retrieval_service.retrieve_resources(query=query, top_k=retrieve_k)

    if not retrieved:
        return ChatResponse(error="No similar resources found for generation.", exercise_data=exercise_data)

    top_resources = _extract_top_resources(retrieved, limit=3)
    top_resources = await _resolve_top_resource_names(top_resources, platon, user_token)
    await _emit_progress(
        progress_callback,
        "retrieval_completed",
        {"value": f"Retrieved {len(retrieved)} resources.", "top_resources": top_resources},
    )

    _check_cancelled()

    if chat_request.force_pure_exercise:
        logger.info("force_pure_exercise=True — skipping template selection, proceeding with pure exercise generation")
        await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_sans_template", "mode_label": "exercise sans template"})
        return await _generate_pure_exercise(
            exercise_data, chat_request, platon, user_token, progress_callback,
            retrieved=retrieved,
            session_id=session_id,
            is_modification=False,
            conversation_id=conversation_id,
            username=username,
            cancellation_event=cancellation_event,
        )

    best_template = _find_best_template(retrieved)
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
        )
        return _workflow_result_to_response(result, exercise_data, conversation_mode="template")

    await _emit_progress(progress_callback, "generation_mode", {"mode": "exercise_sans_template", "mode_label": "exercise sans template"})
    return await _generate_pure_exercise(
        exercise_data, chat_request, platon, user_token, progress_callback,
        retrieved=retrieved,
        session_id=session_id,
        is_modification=False,
        conversation_id=conversation_id,
        username=username,
        cancellation_event=cancellation_event,
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
) -> WorkflowResult:
    from src.services.generation_service import GenerationService
    from src.services.rag.retrieval_service import retrieval_service, get_embed_model

    def _check_cancelled() -> None:
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError("Generation cancelled by user.")

    generation_service = GenerationService(temperature=_get_config().generation_temperature)
    await _emit_progress(progress_callback, "llm_generation_started", {"value": "Generating template parameters with AI..."})
    gen_result = await generation_service.generate_config_variables(
        exercise_data=exercise_data,
        user_request=user_request,
        conversation_history=conversation_history,
        fields_to_modify=fields_to_modify,
        is_modification=is_modification,
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
        preview_url=workflow_result.url if not workflow_result.error else None,
        retry_count=workflow_result.retry_count,
        retry_errors=workflow_result.retry_errors,
        status="completed" if not workflow_result.error else "failed",
        input_tokens=gen_result.llm.input_tokens,
        output_tokens=gen_result.llm.output_tokens,
        llm_request_count=gen_result.llm.request_count,
    )))

    return workflow_result
