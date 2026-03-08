from __future__ import annotations

import logging
from typing import Optional

from src.infra.files.models import FileSummaryResult
from src.infra.files.truncation import truncate_to_tokens

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = (
    "Tu es un assistant technique. "
    "Résume le contenu du fichier fourni de manière concise et précise en français. "
    "Limite-toi à l'essentiel : type de document, thème principal, informations clés. "
    "La réponse doit être un texte simple, sans mise en forme."
)

_SUMMARY_REDIS_PREFIX = "file_summary:"


async def summarize_file_content(
    file_id: str,
    filename: str,
    extracted_text: str,
    max_summary_tokens: int,
) -> FileSummaryResult:
    from src.infra.llm.llm_wrapper import chat_text_with_llm

    truncated_for_summary = truncate_to_tokens(extracted_text, max_summary_tokens * 4)

    user_prompt = f"Fichier : {filename}\n\nContenu :\n{truncated_for_summary}"

    try:
        llm_result = await chat_text_with_llm(
            system_prompt=_SUMMARY_SYSTEM_PROMPT,
            user_request=user_prompt,
            temperature=0.0,
        )
        summary = llm_result.text
        logger.info(
            "FileSummarizer: summary generated for file_id=%s, summary_len=%d chars",
            file_id, len(summary),
        )
    except Exception as exc:
        logger.warning(
            "FileSummarizer: LLM summary failed for file_id=%s (%s): %s",
            file_id, filename, exc,
        )
        summary = f"[Résumé indisponible — erreur LLM: {exc}]"

    return FileSummaryResult(
        file_id=file_id,
        filename=filename,
        extracted_text=extracted_text,
        summary=summary,
    )


async def store_summary(redis, file_id: str, summary: str, ttl_seconds: int) -> None:
    key = f"{_SUMMARY_REDIS_PREFIX}{file_id}"
    await redis.setex(key, ttl_seconds, summary)
    logger.info("FileSummarizer: stored summary for file_id=%s", file_id)


async def get_summary(redis, file_id: str) -> Optional[str]:
    key = f"{_SUMMARY_REDIS_PREFIX}{file_id}"
    raw = await redis.get(key)
    if raw is None:
        return None
    return raw if isinstance(raw, str) else raw.decode("utf-8")


async def delete_summary(redis, file_id: str) -> None:
    key = f"{_SUMMARY_REDIS_PREFIX}{file_id}"
    await redis.delete(key)
    logger.info("FileSummarizer: deleted summary for file_id=%s", file_id)


async def get_many_summaries(redis, file_ids: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for fid in file_ids:
        summary = await get_summary(redis, fid)
        if summary:
            result[fid] = summary
    return result

