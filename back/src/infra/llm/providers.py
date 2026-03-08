"""
Concrete LLM provider adapters.

Each class wraps a specific LLM vendor HTTP API behind the generic
``LLMProvider`` protocol so the rest of the codebase never touches
vendor-specific logic.

Adding a new provider:
    1. Create a class that satisfies ``LLMProvider``.
    2. Register it in ``di.py`` via the ``LLMProviderRegistry``.
    3. Set the corresponding env vars.
    That is all -- zero changes required in the wrapper or service layers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)

from src.infra.llm.file_upload_logger import log_file_uploaded, log_file_deleted
from src.infra.llm.llm import LLMChatResult, LLMUsageMetrics


# ---------------------------------------------------------------------------
# Shared JSON parsing utility
# ---------------------------------------------------------------------------

def _extract_openai_usage(result: Dict[str, Any]) -> LLMUsageMetrics:
    usage = result.get("usage") or {}
    return LLMUsageMetrics(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        request_count=1,
    )


def _resolve_json_content(
    content: str,
    provider_name: str,
) -> Union[Dict[str, Any], str]:
    """Parse the LLM output string into a Python object.

    Strategy (in order):
    1. Direct ``json.loads`` — handles well-behaved responses.
    2. Markdown code-block extraction — some models wrap JSON inside
       `` ```json ... ``` `` even when a structured schema is enforced.
       Only attempted when direct parse fails, which prevents the
       extractor from mistakenly grabbing a code block that appears
       *inside* a valid JSON string (e.g. inside a ``reasoning`` field).
    3. Structural repair of truncated JSON.
    4. Return raw string and log an error so the caller can decide.
    """
    stripped = content.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    repaired = _repair_truncated_json(stripped)
    if repaired is not None:
        try:
            result = json.loads(repaired)
            logger.info("[%s] JSON repair succeeded — partial response recovered.", provider_name)
            return result
        except json.JSONDecodeError as exc:
            logger.error("[%s] JSON repair attempt failed: %s", provider_name, exc)

    logger.error(
        "[%s] Could not parse LLM response as JSON — returning raw string. "
        "Content (first 500 chars): %s",
        provider_name,
        content[:500],
    )
    return content


def _repair_truncated_json(content: str) -> Optional[str]:
    """Close any open JSON structures left by a truncated LLM response.

    Handles:
    - Unclosed strings (strips the partial value entirely)
    - Trailing commas before closing brackets
    - Unclosed objects / arrays (appends the required closing chars)

    Returns the repaired string, or None if the content is too broken to repair.
    """
    if not content or not content.strip():
        return None

    text = content.rstrip()

    # Strip a trailing partial string value (no closing quote).
    # e.g.  "key": "partial val   →  "key": ""
    # We look for a quote that opens a value but has no matching close.
    # Simple heuristic: if the text ends inside a string, cut back to the colon.
    in_string = False
    escape_next = False
    last_string_open = -1
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            if in_string:
                in_string = False
                last_string_open = -1
            else:
                in_string = True
                last_string_open = i

    if in_string and last_string_open != -1:
        # Cut off everything from the unclosed quote onward.
        text = text[:last_string_open].rstrip().rstrip(',').rstrip()

    # Remove trailing commas before closing brackets.
    text = re.sub(r',\s*$', '', text)

    # Count unclosed objects and arrays.
    opens: List[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            opens.append(ch)
        elif ch == '}':
            if opens and opens[-1] == '{':
                opens.pop()
        elif ch == ']':
            if opens and opens[-1] == '[':
                opens.pop()

    # Append closing characters in reverse order.
    closing = ''.join(
        '}' if ch == '{' else ']'
        for ch in reversed(opens)
    )
    return text + closing if (closing or text != content.rstrip()) else None


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (covers Groq, Ragustave, vLLM, LiteLLM, ...)
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider:
    """Adapter for any endpoint that follows the OpenAI ``/chat/completions``
    contract.  Groq and Ragustave are both instances of this class
    configured with different ``base_url`` / ``api_key`` values.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._name = provider_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds)

    # -- LLMProvider interface -------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        """OpenAI-compatible APIs expect ``response_format`` with a
        ``json_schema`` envelope."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
            },
        }

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        file_paths: Optional[List[Path]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Any:
        if file_paths or file_ids:
            logger.warning(
                "[%s] File upload is not supported by this provider -- ignoring %d file(s) / %d id(s)",
                self._name, len(file_paths or []), len(file_ids or []),
            )
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        data: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_schema:
            data["response_format"] = json_schema

        logger.info(
            "OpenAI-compatible [%s] request -- model=%s, temperature=%s, json_schema=%s",
            self._name, model, temperature, json_schema is not None,
        )

        max_attempts = 4
        attempt = 0
        result: Dict[str, Any]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                attempt += 1
                try:
                    response = await client.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    result = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    should_retry = status_code == 429 or 500 <= status_code < 600
                    if not should_retry or attempt >= max_attempts:
                        raise

                    retry_after_raw = exc.response.headers.get("retry-after")
                    retry_delay: float
                    try:
                        retry_delay = float(retry_after_raw) if retry_after_raw else 0.0
                    except ValueError:
                        retry_delay = 0.0
                    if retry_delay <= 0.0:
                        # Exponential backoff: 1s, 2s, 4s...
                        retry_delay = float(2 ** (attempt - 1))
                    retry_delay = min(retry_delay, 20.0)

                    logger.warning(
                        "[%s] HTTP %s from upstream (attempt %s/%s). Retrying in %.2fs.",
                        self._name,
                        status_code,
                        attempt,
                        max_attempts,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                    if attempt >= max_attempts:
                        raise
                    retry_delay = min(float(2 ** (attempt - 1)), 10.0)
                    logger.warning(
                        "[%s] transient network error (%s) attempt %s/%s. Retrying in %.2fs.",
                        self._name,
                        exc.__class__.__name__,
                        attempt,
                        max_attempts,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"[{self._name}] Unexpected response structure: {result}"
            ) from exc

        logger.info("[%s] Raw output: %s", self._name, content)

        usage = _extract_openai_usage(result)

        raw_text = content

        if not json_schema:
            return LLMChatResult(content=content, usage=usage, raw_text=raw_text)

        return LLMChatResult(content=_resolve_json_content(content, self._name), usage=usage, raw_text=raw_text)


# ---------------------------------------------------------------------------
# Ragustave provider (Open-WebUI compatible, supports file upload)
# ---------------------------------------------------------------------------

class RagustaveProvider:
    """Adapter for the Ragustave (Open-WebUI) API.

    Unlike the generic ``OpenAICompatibleProvider``, this class supports
    uploading a local file and attaching it to the chat request so the
    LLM can reason over its content.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds)

    @property
    def name(self) -> str:
        return "ragustave"

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
            },
        }

    async def fetch_available_models(self) -> List[str]:
        url = f"{self._base_url}/models"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        models: List[str] = []
        for entry in payload.get("data", []):
            info = entry.get("info") or {}
            if info.get("base_model_id") is not None:
                continue
            model_id = entry.get("id")
            if model_id:
                models.append(model_id)

        logger.info(
            "Ragustave: fetched %d original model(s) from remote API.",
            len(models),
        )
        return models

    async def upload_file(self, file_path: Path, original_name: str) -> str:
        """Upload a file to Ragustave and return its file ID.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            httpx.HTTPStatusError: On a non-2xx response.
            ValueError: If the response does not contain an ``id`` field.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        url = f"{self._base_url}/v1/files/"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        logger.info("Ragustave: uploading file '%s' (original name: %s)", file_path, original_name)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            with file_path.open("rb") as fh:
                response = await client.post(
                    url,
                    headers=headers,
                    files={"file": (original_name, fh)},
                )
            response.raise_for_status()

        result = response.json()
        try:
            file_id: str = result["id"]
        except KeyError as exc:
            raise ValueError(
                f"Ragustave file upload response missing 'id': {result}"
            ) from exc

        log_file_uploaded(original_name, file_id)
        return file_id

    async def delete_file(self, file_id: str, original_name: str = "") -> None:
        """Delete a previously uploaded file from Ragustave.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response.
        """
        url = f"{self._base_url}/v1/files/{file_id}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        logger.info("Ragustave: deleting file id=%s (name=%s)", file_id, original_name)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()

        log_file_deleted(original_name, file_id)
        logger.info("Ragustave: file deleted, id=%s", file_id)

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        file_paths: Optional[List[Path]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Any:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        data: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_schema:
            data["response_format"] = json_schema

        resolved_ids: List[str] = list(file_ids or [])

        if file_paths:
            for fp in file_paths:
                fid = await self.upload_file(fp, fp.name)
                resolved_ids.append(fid)

        if resolved_ids:
            data["files"] = [{"type": "file", "id": fid} for fid in resolved_ids]
            logger.info(
                "Ragustave: attaching %d file(s): %s", len(resolved_ids), resolved_ids
            )

        logger.info(
            "Ragustave request -- model=%s, temperature=%s, json_schema=%s, "
            "file_paths=%s, file_ids=%s",
            model, temperature, json_schema is not None, file_paths, resolved_ids,
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"[ragustave] Unexpected response structure: {result}"
            ) from exc

        logger.info("[ragustave] Raw output: %s", content)

        usage = _extract_openai_usage(result)

        raw_text = content

        if not json_schema:
            return LLMChatResult(content=content, usage=usage, raw_text=raw_text)

        return LLMChatResult(content=_resolve_json_content(content, "ragustave"), usage=usage, raw_text=raw_text)


# ---------------------------------------------------------------------------
# Gemini provider (Google Generative AI REST endpoint)
# ---------------------------------------------------------------------------

class GeminiProvider:
    """Adapter for the Google Gemini ``generateContent`` REST API."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds)

    # -- LLMProvider interface -------------------------------------------

    @property
    def name(self) -> str:
        return "gemini"

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        """Gemini expects the raw schema directly (used as
        ``responseSchema`` in ``generationConfig``)."""
        return schema

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        file_paths: Optional[List[Path]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Any:
        if file_paths or file_ids:
            logger.warning(
                "[gemini] File upload is not supported by this provider -- ignoring %d file(s) / %d id(s)",
                len(file_paths or []), len(file_ids or []),
            )
        # Strip provider prefix if present (e.g. "gemini/gemini-2.5-flash")
        if "/" in model:
            model = model.split("/", 1)[1]

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent"
        )

        data: Dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"temperature": temperature},
        }

        if json_schema:
            data["generationConfig"]["responseMimeType"] = "application/json"
            data["generationConfig"]["responseSchema"] = json_schema

        logger.info(
            "Gemini request -- model=%s, temperature=%s, json_schema=%s",
            model, temperature, json_schema is not None,
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                params={"key": self._api_key},
                json=data,
            )
            response.raise_for_status()
            result = response.json()

        try:
            content = result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"Gemini returned unexpected response structure: {result}"
            ) from exc

        logger.info("Gemini raw output: %s", content)

        gemini_usage = result.get("usageMetadata") or {}
        usage = LLMUsageMetrics(
            input_tokens=gemini_usage.get("promptTokenCount"),
            output_tokens=gemini_usage.get("candidatesTokenCount"),
            request_count=1,
        )

        raw_text = content

        if not json_schema:
            return LLMChatResult(content=content, usage=usage, raw_text=raw_text)

        return LLMChatResult(content=_resolve_json_content(content, "gemini"), usage=usage, raw_text=raw_text)


# ---------------------------------------------------------------------------
# Ollama provider (local model server)
# ---------------------------------------------------------------------------

class OllamaProvider:
    """Adapter for the Ollama ``/api/chat`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)

    # -- LLMProvider interface -------------------------------------------

    @property
    def name(self) -> str:
        return "ollama"

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        """Ollama uses the ``format`` field which expects the inner
        ``schema`` dict directly."""
        return {"name": schema_name, "schema": schema}

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        file_paths: Optional[List[Path]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Any:
        if file_paths or file_ids:
            logger.warning(
                "[ollama] File upload is not supported by this provider -- ignoring %d file(s) / %d id(s)",
                len(file_paths or []), len(file_ids or []),
            )
        # Strip provider prefix if present (e.g. "ollama/llama3.1")
        if "/" in model:
            model = model.split("/", 1)[1]

        url = f"{self._base_url}/api/chat"

        data: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": json_schema["schema"] if json_schema else None,
            "temperature": temperature,
        }

        logger.info(
            "Ollama request -- model=%s, temperature=%s, json_schema=%s",
            model, temperature, json_schema is not None,
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            result = response.json()

        content = result["message"]["content"]
        logger.info("Ollama raw output: %s", content)

        ollama_usage = LLMUsageMetrics(
            input_tokens=result.get("prompt_eval_count"),
            output_tokens=result.get("eval_count"),
            request_count=1,
        )

        raw_text = content

        if not json_schema:
            return LLMChatResult(content=content, usage=ollama_usage, raw_text=raw_text)

        return LLMChatResult(content=_resolve_json_content(content, "ollama"), usage=ollama_usage, raw_text=raw_text)


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------

class OpenRouterProvider:
    """Adapter for the OpenRouter API (https://openrouter.ai/api/v1).

    OpenRouter is OpenAI-compatible but requires specific JSON schema formatting.
    """

    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._name = provider_name
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds)

    @property
    def name(self) -> str:
        return self._name

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        file_paths: Optional[List[Path]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Any:
        if file_paths or file_ids:
            logger.warning(
                "[%s] File upload is not supported by OpenRouter -- ignoring %d file(s) / %d id(s)",
                self._name, len(file_paths or []), len(file_ids or []),
            )

        url = f"{self._BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        data: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 12000,
            "reasoning": {"enabled": True},
        }

        if json_schema:
            data["response_format"] = json_schema

        logger.info(
            "OpenRouter [%s] request -- model=%s, temperature=%s, json_schema=%s",
            self._name, model, temperature, json_schema is not None,
        )

        max_attempts = 4
        attempt = 0

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while True:
                attempt += 1
                try:
                    response = await client.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    result = response.json()
                    break
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    should_retry = status_code == 429 or 500 <= status_code < 600
                    if not should_retry or attempt >= max_attempts:
                        raise
                    retry_after_raw = exc.response.headers.get("retry-after")
                    try:
                        retry_delay = float(retry_after_raw) if retry_after_raw else 0.0
                    except ValueError:
                        retry_delay = 0.0
                    if retry_delay <= 0.0:
                        retry_delay = float(2 ** (attempt - 1))
                    retry_delay = min(retry_delay, 20.0)
                    logger.warning(
                        "[%s] HTTP %s from OpenRouter (attempt %s/%s). Retrying in %.2fs.",
                        self._name, status_code, attempt, max_attempts, retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                    if attempt >= max_attempts:
                        raise
                    retry_delay = min(float(2 ** (attempt - 1)), 10.0)
                    logger.warning(
                        "[%s] transient network error (%s) attempt %s/%s. Retrying in %.2fs.",
                        self._name, exc.__class__.__name__, attempt, max_attempts, retry_delay,
                    )
                    await asyncio.sleep(retry_delay)

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"[{self._name}] Unexpected OpenRouter response structure: {result}"
            ) from exc
        logger.info("[%s] Raw output: %s", self._name, content)

        usage = _extract_openai_usage(result)

        raw_text = content

        if not json_schema:
            return LLMChatResult(content=content, usage=usage, raw_text=raw_text)

        return LLMChatResult(content=_resolve_json_content(content, self._name), usage=usage, raw_text=raw_text)


# ---------------------------------------------------------------------------
# Cerebras provider
# ---------------------------------------------------------------------------

class CerebrasProvider:
    """Adapter for the Cerebras Cloud SDK (https://cloud.cerebras.ai).

    Uses the official ``cerebras-cloud-sdk`` package which mirrors the
    OpenAI client interface.  The SDK is synchronous so we run calls in
    an executor to stay non-blocking in the async context.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
    ) -> None:
        from cerebras.cloud.sdk import Cerebras
        self._name = provider_name
        self._client = Cerebras(api_key=api_key)

    @property
    def name(self) -> str:
        return self._name

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": False,
                "schema": schema,
            },
        }

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        file_paths: Optional[List[Path]] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Any:
        if file_paths or file_ids:
            logger.warning(
                "[%s] File upload is not supported by Cerebras -- ignoring %d file(s) / %d id(s)",
                self._name, len(file_paths or []), len(file_ids or []),
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_schema:
            kwargs["response_format"] = json_schema

        logger.info(
            "Cerebras [%s] request -- model=%s, temperature=%s, json_schema=%s",
            self._name, model, temperature, json_schema is not None,
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.chat.completions.create(**kwargs),
        )

        try:
            content = response.choices[0].message.content
        except (IndexError, AttributeError) as exc:
            raise ValueError(
                f"[{self._name}] Unexpected Cerebras response structure: {response}"
            ) from exc

        logger.info(
            "[%s] Raw output: %s",
            self._name,
            content
        )

        cerebras_usage = getattr(response, "usage", None)
        usage = LLMUsageMetrics(
            input_tokens=getattr(cerebras_usage, "prompt_tokens", None) if cerebras_usage else None,
            output_tokens=getattr(cerebras_usage, "completion_tokens", None) if cerebras_usage else None,
            request_count=1,
        )

        raw_text = content

        if not json_schema:
            return LLMChatResult(content=content, usage=usage, raw_text=raw_text)

        return LLMChatResult(content=_resolve_json_content(content, self._name), usage=usage, raw_text=raw_text)
