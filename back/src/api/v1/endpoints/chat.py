import asyncio
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.api.v1.dependencies import get_settings, get_session_id
from src.core.config_app import Settings
from src.core.sqlalchemy import get_db_session
from src.infra.db.redis import get_redis
from src.infra.llm.file_upload_logger import log_temp_file_deleted
from src.services.auth_service import auth_service
from src.services.models.api import (
    ChatRequest,
    ChatResponse,
    FileInfo,
    SessionFile,
    SessionFilesResponse,
    FileSupportResponse,
    UploadFileResponse,
    DeleteFilesResponse,
)
from src.workflows.workflow import handle_chat

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_FILES_PREFIX = "session_files:"


def _make_fcs(redis, app_settings: Settings):
    from src.infra.files.file_content_service import FileContentService
    return FileContentService(
        redis=redis,
        ttl_seconds=app_settings.SESSION_TTL_SECONDS,
        max_tokens=app_settings.FILE_CONTENT_MAX_TOKENS,
        summary_max_tokens=app_settings.FILE_SUMMARY_MAX_TOKENS,
    )


async def _get_session_files(redis, session_id: str) -> List[SessionFile]:
    raw = await redis.get(f"{_SESSION_FILES_PREFIX}{session_id}")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [SessionFile(file_id=f["file_id"], filename=f["filename"]) for f in data]
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("Could not parse session files for session %s: %s", session_id, exc)
        return []


async def _save_session_files(redis, session_id: str, files: List[SessionFile], ttl: int) -> None:
    key = f"{_SESSION_FILES_PREFIX}{session_id}"
    serialized = json.dumps([{"file_id": f.file_id, "filename": f.filename} for f in files])
    await redis.setex(key, ttl, serialized)


@router.get("/file-support", response_model=FileSupportResponse)
async def file_support_endpoint(
    app_settings: Settings = Depends(get_settings),
) -> FileSupportResponse:
    from src.core.di import get_llm_registry
    from src.infra.llm.providers import RagustaveProvider
    from src.services.runtime_config_service import runtime_config, SettingKey

    registry = get_llm_registry()
    provider = registry.default_provider

    # Both provider paths now accept all text files generically.
    # An empty accepted_extensions list signals to the frontend that no
    # extension allowlist is enforced — content probing is done server-side.
    logger.info(
        "File support check: provider=%s, accepted_extensions=(all text files)",
        provider.name,
    )
    return FileSupportResponse(
        supported=True,
        max_files=runtime_config.get_int(SettingKey.FILE_UPLOAD_MAX_COUNT),
        accepted_extensions=[],
    )


@router.get("/files", response_model=SessionFilesResponse)
async def get_session_files_endpoint(
    session_id: Optional[str] = Depends(get_session_id),
    redis=Depends(get_redis),
) -> SessionFilesResponse:
    if not session_id:
        return SessionFilesResponse(files=[])
    files = await _get_session_files(redis, session_id)
    return SessionFilesResponse(files=files)


@router.post("/upload-file", response_model=UploadFileResponse)
async def upload_file_endpoint(
    file: UploadFile = File(...),
    session_id: Optional[str] = Depends(get_session_id),
    redis=Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
) -> UploadFileResponse:
    from src.core.di import get_llm_registry
    from src.infra.files.file_content_service import FileTokenLimitExceededError
    from src.infra.llm.providers import RagustaveProvider
    from src.infra.files.parsers import is_extension_accepted

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    registry = get_llm_registry()
    provider = registry.default_provider
    is_ragustave = isinstance(provider, RagustaveProvider)

    if not is_ragustave:
        suffix = Path(file.filename).suffix.lower()
        if not is_extension_accepted(suffix):
            raise HTTPException(
                status_code=400,
                detail=f"File type '{suffix}' is a known binary format and cannot be submitted.",
            )

    if not session_id:
        raise HTTPException(status_code=401, detail="No active session")

    existing = await _get_session_files(redis, session_id)

    from src.services.runtime_config_service import runtime_config, SettingKey
    max_files = runtime_config.get_int(SettingKey.FILE_UPLOAD_MAX_COUNT)
    if len(existing) >= max_files:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {max_files} files already uploaded in this session",
        )

    logger.info("Receiving file upload: filename=%s, content_type=%s", file.filename, file.content_type)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)

    try:
        fcs = _make_fcs(redis, app_settings)

        if is_ragustave:
            logger.info("Uploading file to Ragustave: tmp_path=%s, original_name=%s", tmp_path, file.filename)
            file_id = await provider.upload_file(tmp_path, file.filename)
            logger.info("File uploaded to Ragustave: file_id=%s, original_name=%s", file_id, file.filename)
        else:
            import uuid as _uuid
            file_id = str(_uuid.uuid4())
            logger.info(
                "Provider '%s' does not support remote file upload -- using text extraction only, file_id=%s",
                provider.name, file_id,
            )

        try:
            summary_result = await fcs.store(file_id, tmp_path, file.filename, skip_extension_check=is_ragustave)
        except FileTokenLimitExceededError as exc:
            if is_ragustave:
                try:
                    await provider.delete_file(file_id, file.filename)
                except Exception as delete_exc:
                    logger.warning(
                        "Could not rollback Ragustave file '%s' after token-limit rejection: %s",
                        file_id, delete_exc,
                    )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Extracted file content has {exc.token_count} tokens, "
                    f"which exceeds FILE_CONTENT_MAX_TOKENS ({exc.max_tokens})."
                ),
            ) from exc
        if summary_result:
            logger.info(
                "File summarized: file_id=%s, summary_len=%d chars",
                file_id, len(summary_result.summary),
            )

        session_file = SessionFile(file_id=file_id, filename=file.filename)
        existing.append(session_file)
        await _save_session_files(redis, session_id, existing, app_settings.SESSION_TTL_SECONDS)
        logger.info("Session %s now has %d file(s)", session_id, len(existing))

        return UploadFileResponse(file_id=file_id, filename=file.filename)
    finally:
        try:
            tmp_path.unlink()
            log_temp_file_deleted(tmp_path)
        except OSError as e:
            logger.warning("Could not delete temp file %s: %s", tmp_path, e)


@router.delete("/files", response_model=DeleteFilesResponse)
async def delete_session_files_endpoint(
    session_id: Optional[str] = Depends(get_session_id),
    redis=Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
) -> DeleteFilesResponse:
    from src.core.di import get_llm_registry
    from src.infra.llm.providers import RagustaveProvider

    if not session_id:
        return DeleteFilesResponse(deleted=0)

    files = await _get_session_files(redis, session_id)
    if not files:
        return DeleteFilesResponse(deleted=0)

    registry = get_llm_registry()
    provider = registry.default_provider
    fcs = _make_fcs(redis, app_settings)

    deleted = 0
    failed: List[str] = []

    for entry in files:
        try:
            if isinstance(provider, RagustaveProvider):
                await provider.delete_file(entry.file_id, entry.filename)
            await fcs.delete(entry.file_id)
            deleted += 1
        except Exception as exc:
            logger.warning(
                "Could not delete file id=%s from provider: %s", entry.file_id, exc,
            )
            failed.append(entry.file_id)

    await redis.delete(f"{_SESSION_FILES_PREFIX}{session_id}")
    logger.info(
        "Session %s: deleted %d file(s), %d failed: %s",
        session_id, deleted, len(failed), failed,
    )
    return DeleteFilesResponse(deleted=deleted, failed=failed)


@router.delete("/files/{file_id}")
async def delete_single_file_endpoint(
    file_id: str,
    session_id: Optional[str] = Depends(get_session_id),
    redis=Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
) -> dict:
    """Remove a single uploaded file from the session."""
    from src.core.di import get_llm_registry
    from src.infra.llm.providers import RagustaveProvider

    if not session_id:
        raise HTTPException(status_code=401, detail="No active session")

    files = await _get_session_files(redis, session_id)
    target = next((f for f in files if f.file_id == file_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="File not found in session")

    registry = get_llm_registry()
    provider = registry.default_provider
    fcs = _make_fcs(redis, app_settings)

    try:
        if isinstance(provider, RagustaveProvider):
            await provider.delete_file(target.file_id, target.filename)
        await fcs.delete(target.file_id)
    except Exception as exc:
        logger.warning("Could not delete file id=%s: %s", file_id, exc)

    remaining = [f for f in files if f.file_id != file_id]
    await _save_session_files(redis, session_id, remaining, app_settings.SESSION_TTL_SECONDS)
    logger.info("Session %s: removed file %s, %d file(s) remaining", session_id, file_id, len(remaining))

    return {"deleted": True, "file_id": file_id}


_STOP_KEY_PREFIX = "generation_stop:"
_STOP_KEY_TTL = 600


@router.post("/stop")
async def stop_generation_endpoint(
    session_id: Optional[str] = Depends(get_session_id),
    redis=Depends(get_redis),
) -> dict:
    if not session_id:
        raise HTTPException(status_code=401, detail="No active session")
    await redis.setex(f"{_STOP_KEY_PREFIX}{session_id}", _STOP_KEY_TTL, "1")
    logger.info("Stop signal set for session %s", session_id)
    return {"stopped": True}


@router.post("/", response_model=ChatResponse)
async def chat_endpoint(
    http_request: Request,
    request: ChatRequest,
    session_id: Optional[str] = Depends(get_session_id),
    redis=Depends(get_redis),
    app_settings: Settings = Depends(get_settings),
    db_session=Depends(get_db_session),
) -> StreamingResponse:
    from src.core.di import get_llm_registry
    from src.infra.llm.providers import RagustaveProvider

    user_token = None
    user_profile = None
    if session_id:
        session_data = await auth_service.get_session_user(redis, session_id)
        if session_data:
            user_token = session_data.get("platon_access")
            user_profile = session_data

    current_message_file_ids: set[str] = set(request.file_ids)

    session_file_ids: List[str] = []
    session_files_map: dict[str, str] = {}
    if session_id:
        session_files = await _get_session_files(redis, session_id)
        if session_files:
            from src.services.runtime_config_service import runtime_config, SettingKey
            file_limit = runtime_config.get_int(SettingKey.FILE_UPLOAD_MAX_COUNT)
            recent = session_files[-file_limit:]
            session_file_ids = [f.file_id for f in recent]
            session_files_map = {f.file_id: f.filename for f in recent}
            logger.info(
                "Session %s has %d file(s): %s",
                session_id, len(session_file_ids), session_file_ids,
            )

    merged_file_ids = list(dict.fromkeys(request.file_ids + session_file_ids))
    from src.services.runtime_config_service import runtime_config, SettingKey
    _max_files = runtime_config.get_int(SettingKey.FILE_UPLOAD_MAX_COUNT)
    if len(merged_file_ids) > _max_files:
        merged_file_ids = merged_file_ids[-_max_files:]

    # Clear the session file list now that the files have been consumed by this
    # prompt. This resets the upload slot so the user can attach new files on
    # the next message without hitting the per-session limit.
    if session_id and session_file_ids:
        await redis.delete(f"{_SESSION_FILES_PREFIX}{session_id}")
        logger.info(
            "Session %s: cleared %d session file(s) after consuming them in prompt.",
            session_id, len(session_file_ids),
        )

    updates: dict = {"file_ids": merged_file_ids}

    registry = get_llm_registry()
    provider = registry.default_provider
    fcs = _make_fcs(redis, app_settings)

    if merged_file_ids and not isinstance(provider, RagustaveProvider):
        file_contents: List[str] = []
        file_infos: List[FileInfo] = []

        for fid in merged_file_ids:
            filename = session_files_map.get(fid, fid)
            if fid in current_message_file_ids:
                text = await fcs.get(fid)
                if text:
                    file_contents.append(text)
                    excerpt = text[:500] if len(text) > 500 else text
                    summary = await fcs.get_many_summaries([fid])
                    file_infos.append(FileInfo(
                        file_id=fid,
                        filename=filename,
                        text_excerpt=excerpt,
                        summary=summary.get(fid),
                    ))
                    logger.info("File %s (%s): injecting full text (%d chars)", fid, filename, len(text))
            else:
                summaries = await fcs.get_many_summaries([fid])
                summary_text = summaries.get(fid)
                if summary_text:
                    file_contents.append(f"[Resume de {filename}]: {summary_text}")
                    file_infos.append(FileInfo(
                        file_id=fid,
                        filename=filename,
                        text_excerpt=None,
                        summary=summary_text,
                    ))
                    logger.info("File %s (%s): injecting summary (%d chars)", fid, filename, len(summary_text))
                else:
                    text = await fcs.get(fid)
                    if text:
                        file_contents.append(text)
                        excerpt = text[:500] if len(text) > 500 else text
                        file_infos.append(FileInfo(
                            file_id=fid,
                            filename=filename,
                            text_excerpt=excerpt,
                            summary=None,
                        ))
                        logger.warning("File %s (%s): no summary found, falling back to full text", fid, filename)

        if file_contents:
            updates["file_contents"] = file_contents
            updates["file_infos"] = [fi.model_dump() for fi in file_infos]
            logger.info(
                "Injecting %d file content(s) into prompt for session %s",
                len(file_contents), session_id,
            )
    elif merged_file_ids and isinstance(provider, RagustaveProvider):
        summaries_map = await fcs.get_many_summaries(merged_file_ids)
        file_infos_ragustave: List[FileInfo] = []
        for fid in merged_file_ids:
            filename = session_files_map.get(fid, fid)
            file_infos_ragustave.append(FileInfo(
                file_id=fid,
                filename=filename,
                text_excerpt=None,
                summary=summaries_map.get(fid),
            ))
        updates["file_infos"] = [fi.model_dump() for fi in file_infos_ragustave]

    request = request.model_copy(update=updates)

    progress_queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    async def progress_callback(event_type: str, data: dict) -> None:
        await progress_queue.put((event_type, data))

    async def event_generator():
        stop_key = f"{_STOP_KEY_PREFIX}{session_id}" if session_id else None
        if stop_key:
            await redis.delete(stop_key)

        logger.info(
            "[SSE] Stream opened for session=%s, request=%r",
            session_id,
            request.user_request[:120] if request.user_request else "",
        )

        try:
            yield f"event: generation_started\ndata: {json.dumps({'value': 'Generation en cours', 'state': 'in_progress'})}\n\n"

            cancellation_event = asyncio.Event()

            task = asyncio.create_task(handle_chat(
                request,
                db_session,
                user_token,
                progress_callback=progress_callback,
                session_id=session_id,
                conversation_id=getattr(request, "conversation_id", None),
                username=user_profile.get("username") if isinstance(user_profile, dict) else None,
                cancellation_event=cancellation_event,
            ))

            async def _is_cancelled() -> tuple[bool, str]:
                if await http_request.is_disconnected():
                    logger.info("Client disconnected — cancelling generation for session %s", session_id)
                    return True, "disconnected"
                if stop_key:
                    stop_flag = await redis.get(stop_key)
                    if stop_flag:
                        logger.info("Stop flag detected — cancelling generation for session %s", session_id)
                        await redis.delete(stop_key)
                        return True, "stop_signal"
                return False, ""

            def _abort(cancel_reason: str) -> None:
                cancellation_event.set()
                task.cancel()
                while not progress_queue.empty():
                    try:
                        progress_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            while not task.done() or not progress_queue.empty():
                should_cancel, cancel_reason = await _is_cancelled()
                if should_cancel:
                    _abort(cancel_reason)
                    if cancel_reason == "stop_signal":
                        yield f"event: stopped\ndata: {json.dumps({'value': 'Génération interrompue.', 'state': 'stopped'})}\n\n"
                    return

                try:
                    event_name, event_data = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                    payload = event_data or {}
                    payload.setdefault("timestamp", time.time())
                    yield f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'timestamp': time.time()})}\n\n"

            should_cancel_final, cancel_reason_final = await _is_cancelled()
            if should_cancel_final:
                _abort(cancel_reason_final)
                if cancel_reason_final == "stop_signal":
                    yield f"event: stopped\ndata: {json.dumps({'value': 'Génération interrompue.', 'state': 'stopped'})}\n\n"
                return

            try:
                response = await task
            except asyncio.CancelledError:
                logger.info("[SSE] Task cancelled for session=%s.", session_id)
                return
            except Exception as exc:
                logger.exception("[SSE] Unhandled exception in handle_chat task for session=%s.", session_id)
                message = str(exc)
                if "429" in message:
                    message = "LLM rate limit reached (429). Please retry in a few seconds."
                yield f"event: error\ndata: {json.dumps({'value': message, 'state': 'error', 'exercise_data': None, 'url': None, 'message': None})}\n\n"
                return

            if hasattr(response, 'error') and response.error:
                logger.warning("[SSE] Generation completed with error for session=%s: %s", session_id, response.error)
                error_payload: dict = {'value': response.error, 'state': 'error'}
                if response.retry_count is not None:
                    error_payload['retry_count'] = response.retry_count
                if response.retry_errors:
                    error_payload['retry_errors'] = response.retry_errors
                if response.exercise_data:
                    error_payload["exercise_data"] = response.exercise_data.model_dump()
                if response.conversation_mode:
                    error_payload["conversation_mode"] = response.conversation_mode
                yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            else:
                logger.info("[SSE] Generation completed successfully for session=%s.", session_id)
                final_data: dict = {
                    'exercise_data': response.exercise_data.model_dump(),
                    'url': response.url,
                    'message': response.message,
                }
                if response.retry_count is not None:
                    final_data['retry_count'] = response.retry_count
                if response.retry_errors:
                    final_data['retry_errors'] = response.retry_errors
                if response.conversation_mode:
                    final_data['conversation_mode'] = response.conversation_mode
                yield f"event: complete\ndata: {json.dumps(final_data)}\n\n"

        except asyncio.CancelledError:
            logger.info("[SSE] Stream cancelled for session=%s.", session_id)
            raise
        except Exception:
            logger.exception(
                "[SSE] FATAL unhandled exception inside event_generator for session=%s."
                " This would have silently killed the worker.",
                session_id,
            )
            try:
                yield f"event: error\ndata: {json.dumps({'value': 'Internal server error during generation.', 'state': 'error'})}\n\n"
            except Exception:
                pass
        finally:
            logger.info("[SSE] Stream closed for session=%s.", session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
