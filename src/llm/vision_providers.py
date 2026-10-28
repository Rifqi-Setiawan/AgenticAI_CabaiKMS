"""Vision-LVM provider abstraction for the Vision & Classification agent
(src/agents/vision_classification.py).

Gemini is the primary path, always used, with no fallback of its own (per
the brief — "Utama: LVM Gemini"). A second voter (Qwen2.5-VL-72B via
OpenRouter, falling back to a local Ollama Qwen2.5-VL-7B) exists only for
optional consensus mode. Both paths go through `instructor`'s OpenAI-
compatible bridge — Gemini and OpenRouter both expose OpenAI-compatible
chat endpoints — matching src/llm/providers.py's pattern for the text-only
schema-matching reranker.

Model name note: the brief names "Gemini 2.5 Flash", but that exact model
id (`gemini-2.5-flash`) returns 404 "no longer available to new users" for
newly-provisioned API keys as of this project's Google AI Studio account
(verified directly against the real API, not assumed) — `gemini-flash-latest`
is used instead, and is configurable via GEMINI_MODEL_NAME for whenever
availability shifts again.
"""

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
    NINEROUTER_REQUIRED_VISION_MODEL,
    NinerouterConfig,
    ninerouter_instructor_client,
    provider_mode,
)
from src.llm.telemetry import record_provider_call

load_dotenv()  # once at import — see src/llm/providers.py's docstring for why

T = TypeVar("T", bound=BaseModel)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_NAME", "gemini-flash-latest")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_VL_MODEL = "qwen/qwen2.5-vl-72b-instruct"

OLLAMA_VL_BASE_URL_DEFAULT = "http://localhost:11434/v1"
OLLAMA_VL_MODEL = "qwen2.5-vl:7b"


class VisionCallError(ProviderCallError):
    """Raised when an LVM call fails outright — no result to return."""


def _openai_compatible_client(base_url: str, api_key: str):
    import instructor
    from openai import OpenAI

    return instructor.from_openai(OpenAI(base_url=base_url, api_key=api_key), mode=instructor.Mode.JSON)


def _gemini_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise VisionCallError(
            "GOOGLE_API_KEY is not set",
            failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
        )
    return _openai_compatible_client(GEMINI_BASE_URL, api_key)


def _openrouter_client():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise VisionCallError(
            "OPENROUTER_API_KEY is not set",
            failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
        )
    return _openai_compatible_client(OPENROUTER_BASE_URL, api_key)


def _ollama_vl_client():
    base_url = os.environ.get("OLLAMA_BASE_URL", OLLAMA_VL_BASE_URL_DEFAULT)
    return _openai_compatible_client(base_url, "ollama")  # Ollama ignores the key


def call_gemini(
    *,
    response_model: type[T],
    messages: list[dict],
    max_retries: int = 2,
) -> T:
    """The primary, always-used LVM call. No fallback of its own — a
    missing GOOGLE_API_KEY or any Gemini-side failure raises VisionCallError
    directly; only the optional second voter (call_second_voter) has its
    own internal fallback."""
    try:
        client = _gemini_client()
        return client.chat.completions.create(
            model=GEMINI_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except VisionCallError:
        raise
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize every failure mode to one error type
        raise VisionCallError(
            provider_error_summary("gemini", exc),
            failure_kind=classify_provider_exception(exc),
        ) from exc


def call_ninerouter_vision(
    *,
    response_model: type[T],
    messages: list[dict],
    max_retries: int = 2,
) -> T:
    """Call the fixed 9Router multimodal model with no legacy fallback."""
    started = time.perf_counter()
    base_record = {
        "gateway": "9router",
        "provider_route": "antigravity",
        "requested_model": NINEROUTER_REQUIRED_VISION_MODEL,
        "model_id": NINEROUTER_REQUIRED_VISION_MODEL,
        "role": "vision",
        "attempt": 1,
        "selected_account": "unknown",
    }
    try:
        config = NinerouterConfig.from_env(require_role="vision")
        client = ninerouter_instructor_client(config)
        result = client.chat.completions.create(
            model=config.vision_model,
            messages=messages,
            response_model=response_model,
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
    except Exception as exc:  # noqa: BLE001
        kind = classify_ninerouter_exception(exc)
        record_provider_call({
            **base_record,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "success": False,
            "failure_kind": kind.value,
            "structured_output_valid": False,
        })
        raise VisionCallError(
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


def call_vision(
    *,
    response_model: type[T],
    messages: list[dict],
    max_retries: int = 2,
) -> T:
    """Configuration-controlled primary vision call."""
    try:
        mode = provider_mode("CABAI_KMS_VISION_PROVIDER")
    except ProviderCallError as exc:
        raise VisionCallError(str(exc), failure_kind=exc.failure_kind) from exc
    if mode == "9router":
        return call_ninerouter_vision(
            response_model=response_model, messages=messages, max_retries=max_retries
        )
    return call_gemini(
        response_model=response_model, messages=messages, max_retries=max_retries
    )


def call_second_voter(
    *,
    response_model: type[T],
    messages: list[dict],
    max_retries: int = 2,
) -> T:
    """Qwen2.5-VL-72B via OpenRouter; falls back to local Ollama
    Qwen2.5-VL-7B if OpenRouter is unavailable. Only invoked when consensus
    mode is enabled — see VisionSession(consensus=True)."""
    errors: list[str] = []
    failure_kinds: list[ProviderFailureKind] = []

    try:
        client = _openrouter_client()
        return client.chat.completions.create(
            model=OPENROUTER_VL_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(provider_error_summary("openrouter", exc))
        failure_kinds.append(classify_provider_exception(exc))

    try:
        client = _ollama_vl_client()
        return client.chat.completions.create(
            model=OLLAMA_VL_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        errors.append(provider_error_summary("ollama", exc))
        failure_kinds.append(classify_provider_exception(exc))

    raise VisionCallError(
        "second voter failed — " + "; ".join(errors),
        failure_kind=combine_failure_kinds(failure_kinds),
    )
