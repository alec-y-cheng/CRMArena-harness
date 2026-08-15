"""Model completion wrapper for LiteLLM and local CLI providers."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from litellm import completion as litellm_completion


CLI_PROVIDERS = {"claude_cli", "codex_cli"}
OPENROUTER_PROVIDER = "openrouter"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-2024-11-20"
OPENROUTER_TRANSIENT_ERRORS = (
    "ResourceExhausted",
    "rate limit",
    "rate_limit",
    "overloaded",
    "capacity",
    "temporarily unavailable",
    "upstream error",
    "timeout",
    "timed out",
    " 429",
    " 502",
    " 503",
    " 504",
)


def is_cli_provider(provider: Optional[str]) -> bool:
    return provider in CLI_PROVIDERS


def should_pass_litellm_custom_provider(provider: Optional[str]) -> bool:
    return provider is not None and provider not in CLI_PROVIDERS


def default_model_for_provider(provider: Optional[str], fallback: Optional[str] = None) -> str:
    if provider == OPENROUTER_PROVIDER:
        return os.environ.get("OPENROUTER_DEFAULT_MODEL", DEFAULT_OPENROUTER_MODEL)
    return fallback or ""


def normalize_model_for_provider(model: str, provider: Optional[str]) -> str:
    if provider != OPENROUTER_PROVIDER:
        return model
    model = model or default_model_for_provider(provider)
    if model.startswith("openrouter/"):
        return model
    return f"openrouter/{model}"


def completion_with_provider(*, provider: Optional[str] = None, **kwargs: Any):
    if provider == OPENROUTER_PROVIDER:
        kwargs["model"] = normalize_model_for_provider(str(kwargs.get("model") or ""), provider)
        kwargs.setdefault("custom_llm_provider", OPENROUTER_PROVIDER)
        return _completion_with_retry(
            kwargs,
            attempts=int(os.environ.get("OPENROUTER_RETRY_ATTEMPTS", "4")),
            base_sleep=float(os.environ.get("OPENROUTER_RETRY_BASE_SLEEP_SECONDS", "8")),
        )
    if provider not in CLI_PROVIDERS:
        return litellm_completion(**kwargs)
    adapter_root = Path(__file__).resolve().parents[2]
    if str(adapter_root) not in sys.path:
        sys.path.insert(0, str(adapter_root))
    from cli_model_adapter import cli_completion

    return cli_completion(provider=provider, **kwargs)


def _completion_with_retry(kwargs: dict[str, Any], *, attempts: int, base_sleep: float):
    attempts = max(1, attempts)
    last_error = None
    for attempt in range(attempts):
        try:
            return litellm_completion(**kwargs)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts - 1 or not _is_transient_openrouter_error(exc):
                raise
            sleep_seconds = base_sleep * (2 ** attempt)
            print(
                "OpenRouter transient completion error; retrying "
                f"{attempt + 2}/{attempts} after {sleep_seconds:.1f}s: {exc}"
            )
            time.sleep(sleep_seconds)
    raise last_error


def _is_transient_openrouter_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token.lower() in message for token in OPENROUTER_TRANSIENT_ERRORS)
