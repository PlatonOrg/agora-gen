"""
Generic LLM provider abstraction.

Defines the contract that every LLM provider adapter must satisfy so the
rest of the application never depends on a concrete vendor SDK or HTTP
client.  New providers (OpenAI-compatible, Gemini, Ollama, or anything
else) are added by implementing ``LLMProvider`` and registering an
instance in the ``LLMProviderRegistry``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMUsageMetrics:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    request_count: int = 1


@dataclass(frozen=True)
class LLMChatResult:
    content: Any
    usage: LLMUsageMetrics = field(default_factory=LLMUsageMetrics)
    raw_text: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """Abstraction over a single LLM provider (Groq, Gemini, Ollama, ...)."""

    @property
    def name(self) -> str:
        """Human-readable provider identifier (e.g. 'groq', 'gemini')."""
        ...

    def wrap_json_schema(
        self,
        schema: Dict[str, Any],
        schema_name: str = "exercise_output",
    ) -> Dict[str, Any]:
        """Wrap a raw JSON Schema dict into the format expected by this provider's API.

        Each provider expects structured-output schemas in a slightly
        different envelope.  This method isolates that difference.
        """
        ...

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
        """Send a chat-completion request and return the parsed result.

        Args:
            model: Model identifier understood by this provider.
            system_prompt: System-level instruction.
            user_prompt: The user's message.
            json_schema: *Already wrapped* schema (output of ``wrap_json_schema``).
                         ``None`` means plain-text generation.
            temperature: Sampling temperature.
            file_path: Optional path to a local file to attach to the request.
                       Only supported by providers that implement file upload
                       (currently only ``RagustaveProvider``).

        Returns:
            ``LLMChatResult`` containing the parsed content and usage metrics.
        """
        ...


class LLMProviderRegistry:
    """Thread-safe, name-keyed store of ``LLMProvider`` instances.

    The registry is the single lookup point used by the LLM wrapper layer
    to route a request to the correct provider without any ``if/elif``
    chain.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {}
        self._default_provider_name: Optional[str] = None
        self._default_models: Dict[str, str] = {}
        self._available_models: Dict[str, List[str]] = {}

    # -- Registration ----------------------------------------------------

    def register(
        self,
        provider: LLMProvider,
        *,
        default_model: str,
        models: Optional[List[str]] = None,
        is_default: bool = False,
    ) -> None:
        """Register a provider instance under its ``name``.

        Args:
            provider: Concrete adapter implementing ``LLMProvider``.
            default_model: Fallback model used when no explicit model is
                           supplied by the caller.
            models: All models available for this provider.  If ``None``
                    or empty, defaults to ``[default_model]``.
            is_default: Mark this provider as the system-wide default.
        """
        self._providers[provider.name] = provider
        self._default_models[provider.name] = default_model

        resolved_models = list(models) if models else []
        if default_model and default_model not in resolved_models:
            resolved_models.insert(0, default_model)
        self._available_models[provider.name] = resolved_models

        if is_default:
            self._default_provider_name = provider.name

    # -- Lookup ----------------------------------------------------------

    def get(self, provider_name: str) -> LLMProvider:
        """Return the provider registered under *provider_name*.

        Raises:
            ValueError: If no provider with that name exists.
        """
        try:
            return self._providers[provider_name]
        except KeyError:
            available = ", ".join(sorted(self._providers)) or "(none)"
            raise ValueError(
                f"Unknown LLM provider '{provider_name}'. "
                f"Registered providers: {available}"
            )

    @property
    def default_provider(self) -> LLMProvider:
        """Return the system-wide default provider.

        Raises:
            RuntimeError: If no default has been set.
        """
        if self._default_provider_name is None:
            raise RuntimeError("No default LLM provider has been configured.")
        return self.get(self._default_provider_name)

    @property
    def default_provider_name(self) -> str:
        if self._default_provider_name is None:
            raise RuntimeError("No default LLM provider has been configured.")
        return self._default_provider_name

    def default_model_for(self, provider_name: str) -> str:
        """Return the configured default model for *provider_name*."""
        try:
            return self._default_models[provider_name]
        except KeyError:
            raise ValueError(
                f"No default model registered for provider '{provider_name}'."
            )

    @property
    def registered_names(self) -> List[str]:
        return list(self._providers.keys())

    # -- Mutation ---------------------------------------------------------

    def set_default(self, provider_name: str, model: Optional[str] = None) -> None:
        """Switch the system-wide default provider and optionally its model.

        This allows runtime reconfiguration without restarting the server.
        The provider must already be registered in the registry, and the
        model (if supplied) must be in that provider's available models.

        Args:
            provider_name: Name of an already-registered provider.
            model: If supplied, overrides the default model for that provider.

        Raises:
            ValueError: If *provider_name* is not registered or *model*
                        is not in the provider's available models.
        """
        self.get(provider_name)  # validates existence
        if model is not None:
            available = self._available_models.get(provider_name, [])
            if available and model not in available:
                raise ValueError(
                    f"Model '{model}' is not available for provider "
                    f"'{provider_name}'. Available: {available}"
                )
            self._default_models[provider_name] = model
        self._default_provider_name = provider_name

    def update_models(self, provider_name: str, models: List[str]) -> None:
        self.get(provider_name)
        self._available_models[provider_name] = list(models)
        current_default = self._default_models.get(provider_name, "")
        if current_default and current_default not in models and models:
            self._default_models[provider_name] = models[0]

    def available_options(self) -> List[Dict[str, str]]:
        """Return a flat list of all registered provider/model pairs.

        Each entry contains ``provider`` and ``model`` keys.  Providers
        with multiple models produce one entry per model, suitable for
        building a frontend selection dropdown.
        """
        options: List[Dict[str, str]] = []
        for name in self._providers:
            models = self._available_models.get(name, [])
            if not models:
                # Fallback: at least show the default model
                options.append({"provider": name, "model": self._default_models.get(name, "")})
            else:
                for model in models:
                    options.append({"provider": name, "model": model})
        return options

