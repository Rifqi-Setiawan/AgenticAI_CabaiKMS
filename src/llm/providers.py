"""Text provider dispatch: 9Router by default, explicit legacy rollback."""

from __future__ import annotations

import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from src.reliability.provider_failures import (
    ProviderCallError,
    ProviderFailureKind,
    classify_provider_exception,
    classify_ninerouter_exception,
    combine_failure_kinds,
    provider_error_summary,
)
from src.llm.openai_compatible import (
    NINEROUTER_REQUIRED_TEXT_MODEL,
    NinerouterConfig,
    ninerouter_instructor_client,
    provider_mode,
)
from src.llm.telemetry import record_provider_call

load_dotenv()

T = TypeVar("T", bound=BaseModel)

GROQ_MODEL = "openai/gpt-oss-120b"
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class LLMCallError(ProviderCallError):
    """Raised when the selected text provider fails."""


def _groq_instructor_client():
    import instructor
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise LLMCallError(
            "GROQ_API_KEY is not set",
            failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
        )
    return instructor.from_groq(Groq(api_key=api_key), mode=instructor.Mode.TOOLS)


def _ollama_instructor_client():
    import instructor
    from openai import OpenAI

    base_url = os.environ.get("OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL)
    client = OpenAI(base_url=base_url, api_key="ollama")  # Ollama ignores the key
    return instructor.from_openai(client, mode=instructor.Mode.JSON)


def _call_legacy(
    *,
    response_model: type[T],
    messages: list[dict[str, str]],
    max_retries: int = 2,
) -> T:
    """Groq first; if that raises for any reason (missing key, network,
    rate limit, ...), retry once against local Ollama. Raises LLMCallError
    with both underlying errors if neither works."""
    errors: list[str] = []
    failure_kinds: list[ProviderFailureKind] = []

    try:
        client = _groq_instructor_client()
        return client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except Exception as exc:  # noqa: BLE001 — this except IS the fallback boundary
        errors.append(provider_error_summary("groq", exc))
        failure_kinds.append(classify_provider_exception(exc))

    try:
        client = _ollama_instructor_client()
        return client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        errors.append(provider_error_summary("ollama", exc))
        failure_kinds.append(classify_provider_exception(exc))

    raise LLMCallError(
        "both providers failed — " + "; ".join(errors),
        failure_kind=combine_failure_kinds(failure_kinds),
    )


def call_ninerouter_text(
    *,
    response_model: type[T],
    messages: list[dict],
    max_retries: int = 2,
) -> T:
    """Call the one fixed 9Router text model; never fall back to legacy."""
    started = time.perf_counter()
    attempt = 1
    base_record = {
        "gateway": "9router",
        "provider_route": "antigravity",
        "requested_model": NINEROUTER_REQUIRED_TEXT_MODEL,
        "model_id": NINEROUTER_REQUIRED_TEXT_MODEL,
        "role": "text",
        "attempt": attempt,
        "selected_account": "unknown",
    }
    try:
        config = NinerouterConfig.from_env(require_role="text")
        client = ninerouter_instructor_client(config)
        result = client.chat.completions.create(
            model=config.text_model,
            messages=messages,
            response_model=response_model,
            # Instructor retries are limited to contract repair. The underlying
            # OpenAI client always has max_retries=0.
            max_retries=max_retries,
        )
    except ValidationError:
        record_provider_call({
            **base_record,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "success": False,
            "failure_kind": ProviderFailureKind.INVALID_STRUCTURED_OUTPUT.value,
            "structured_output_valid": False,
        })
        raise
    except Exception as exc:  # noqa: BLE001 - provider normalization boundary
        kind = classify_ninerouter_exception(exc)
        record_provider_call({
            **base_record,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "success": False,
            "failure_kind": kind.value,
            "structured_output_valid": False,
        })
        raise LLMCallError(
            provider_error_summary("9router", exc), failure_kind=kind
        ) from exc

    record_provider_call({
        **base_record,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "success": True,
        "failure_kind": None,
        "structured_output_valid": True,
    })
    return result


def call_with_fallback(
    *,
    response_model: type[T],
    messages: list[dict],
    max_retries: int = 2,
) -> T:
    """Compatibility entry point with configuration-controlled dispatch.

    In 9Router mode the historical name does not imply a fallback: exactly
    one configured model is called. Groq -> Ollama remains available only in
    explicit ``CABAI_KMS_TEXT_PROVIDER=legacy`` mode.
    """
    try:
        mode = provider_mode("CABAI_KMS_TEXT_PROVIDER")
    except ProviderCallError as exc:
        raise LLMCallError(str(exc), failure_kind=exc.failure_kind) from exc
    if mode == "9router":
        return call_ninerouter_text(
            response_model=response_model, messages=messages, max_retries=max_retries
        )
    return _call_legacy(
        response_model=response_model, messages=messages, max_retries=max_retries
    )
