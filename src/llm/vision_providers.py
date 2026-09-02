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
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()  # once at import — see src/llm/providers.py's docstring for why

T = TypeVar("T", bound=BaseModel)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_NAME", "gemini-flash-latest")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_VL_MODEL = "qwen/qwen2.5-vl-72b-instruct"

OLLAMA_VL_BASE_URL_DEFAULT = "http://localhost:11434/v1"
OLLAMA_VL_MODEL = "qwen2.5-vl:7b"


class VisionCallError(Exception):
    """Raised when an LVM call fails outright — no result to return."""


def _openai_compatible_client(base_url: str, api_key: str):
    import instructor
    from openai import OpenAI

    return instructor.from_openai(OpenAI(base_url=base_url, api_key=api_key), mode=instructor.Mode.JSON)


def _gemini_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise VisionCallError("GOOGLE_API_KEY is not set")
    return _openai_compatible_client(GEMINI_BASE_URL, api_key)


def _openrouter_client():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise VisionCallError("OPENROUTER_API_KEY is not set")
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
    except Exception as exc:  # noqa: BLE001 — normalize every failure mode to one error type
        raise VisionCallError(f"gemini: {exc}") from exc


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

    try:
        client = _openrouter_client()
        return client.chat.completions.create(
            model=OPENROUTER_VL_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"openrouter: {exc}")

    try:
        client = _ollama_vl_client()
        return client.chat.completions.create(
            model=OLLAMA_VL_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ollama: {exc}")

    raise VisionCallError("second voter failed — " + "; ".join(errors))
