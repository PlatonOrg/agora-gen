"""
High-level LLM interaction layer.

All application code calls functions in this module to talk to an LLM.
The actual provider dispatch is handled by the ``LLMProviderRegistry``
so there is *zero* vendor-specific branching here.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.di import get_llm_registry
from src.infra.llm.json_facility import (
    build_fixed_exercise_json_schema,
    build_json_schema_from_config,
)
from src.infra.llm.llm import LLMChatResult
from src.services.models.api import LLMResult, LLMTextResult

logger = logging.getLogger(__name__)


async def chat_with_llm(
    system_prompt: str,
    user_request: str,
    temperature: float,
    schema_config: Optional[List[Dict[str, Any]]] = None,
    use_fixed_schema: bool = False,
    include_properties: Optional[List[str]] = None,
    file_paths: Optional[List[Path]] = None,
    file_ids: Optional[List[str]] = None,
    raw_json_schema: Optional[Dict[str, Any]] = None,
    llm_calls_accumulator: Optional[List[Dict[str, Any]]] = None,
    call_type: str = "generation",
) -> LLMResult:

    logger.info(f"system prompt : {system_prompt}")

    registry = get_llm_registry()
    provider = registry.default_provider
    model = registry.default_model_for(provider.name)

    built_schema: Optional[Dict[str, Any]] = None
    if raw_json_schema is not None:
        built_schema = raw_json_schema
    elif use_fixed_schema:
        built_schema = build_fixed_exercise_json_schema(include_properties=include_properties)
    elif schema_config:
        built_schema = build_json_schema_from_config(schema_config, include_properties=include_properties)

    raw_schema = built_schema

    wrapped_schema: Optional[Dict[str, Any]] = None
    if raw_schema is not None:
        wrapped_schema = provider.wrap_json_schema(raw_schema)

    chat_result = await provider.chat(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_request,
        json_schema=wrapped_schema,
        temperature=temperature,
        file_paths=file_paths,
        file_ids=file_ids,
    )

    if isinstance(chat_result, LLMChatResult):
        raw_content = chat_result.content
        raw_text = chat_result.raw_text
        usage = chat_result.usage
    else:
        raw_content = chat_result
        raw_text = str(chat_result) if chat_result else ""
        from src.infra.llm.llm import LLMUsageMetrics
        usage = LLMUsageMetrics()

    system_chars = len(system_prompt)
    user_chars = len(user_request)
    logger.info(
        "[TOKEN USAGE] call_type=%s provider=%s model=%s | input=%s output=%s | "
        "system_prompt=%d chars (~%d tokens) user_prompt=%d chars (~%d tokens)",
        call_type, provider.name, model,
        usage.input_tokens, usage.output_tokens,
        system_chars, system_chars // 4,
        user_chars, user_chars // 4,
    )

    if llm_calls_accumulator is not None:
        llm_calls_accumulator.append({
            "call_type": call_type,
            "provider": provider.name,
            "model": model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "system_prompt_chars": system_chars,
            "user_prompt_chars": user_chars,
        })

    if isinstance(raw_content, str):
        logger.error(
            "LLM response could not be parsed as JSON (provider=%s, model=%s). "
            "The exercise will be empty. Check provider logs for details.",
            provider.name,
            model,
        )
        parsed: Dict[str, Any] = {}
    else:
        parsed = raw_content

    return LLMResult(
        parsed=parsed,
        provider=provider.name,
        model=model,
        raw_text=raw_text,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        request_count=usage.request_count,
    )


async def chat_text_with_llm(
    system_prompt: str,
    user_request: str,
    temperature: float = 0.0,
) -> LLMTextResult:
    registry = get_llm_registry()
    provider = registry.default_provider
    model = registry.default_model_for(provider.name)

    chat_result = await provider.chat(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_request,
        json_schema=None,
        temperature=temperature,
    )

    if isinstance(chat_result, LLMChatResult):
        raw_text = chat_result.raw_text or (chat_result.content if isinstance(chat_result.content, str) else "")
        text = chat_result.content if isinstance(chat_result.content, str) else str(chat_result.content)
        usage = chat_result.usage
    else:
        raw_text = str(chat_result) if chat_result else ""
        text = raw_text
        from src.infra.llm.llm import LLMUsageMetrics
        usage = LLMUsageMetrics()

    return LLMTextResult(
        text=text.strip(),
        raw_text=raw_text,
        provider=provider.name,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
