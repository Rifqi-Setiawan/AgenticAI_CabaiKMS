"""LLM provider abstraction: Groq (primary) with local Ollama (fallback),
both going through `instructor` for constrained decoding into a Pydantic
model. First consumer is the schema-matching reranker
(src/agents/schema_matching/reranking.py); nothing here is schema-matching
specific.

Loads .env on import (python-dotenv) so GROQ_API_KEY set there is picked up
without every entrypoint having to call load_dotenv() itself. In test
suites, `call_with_fallback` is exercised only via an injected mock
`llm_call`, never against the real network.
"""

from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)

GROQ_MODEL = "openai/gpt-oss-120b"
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class LLMCallError(Exception):
    """Raised when both the primary and fallback provider calls fail."""


def _groq_instructor_client():
    import instructor
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise LLMCallError("GROQ_API_KEY is not set")
    return instructor.from_groq(Groq(api_key=api_key), mode=instructor.Mode.TOOLS)


def _ollama_instructor_client():
    import instructor
    from openai import OpenAI

    base_url = os.environ.get("OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL)
    client = OpenAI(base_url=base_url, api_key="ollama")  # Ollama ignores the key
    return instructor.from_openai(client, mode=instructor.Mode.JSON)


def call_with_fallback(
    *,
    response_model: type[T],
    messages: list[dict[str, str]],
    max_retries: int = 2,
) -> T:
    """Groq first; if that raises for any reason (missing key, network,
    rate limit, ...), retry once against local Ollama. Raises LLMCallError
    with both underlying errors if neither works."""
    errors: list[str] = []

    try:
        client = _groq_instructor_client()
        return client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except Exception as exc:  # noqa: BLE001 — this except IS the fallback boundary
        errors.append(f"groq: {exc}")

    try:
        client = _ollama_instructor_client()
        return client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ollama: {exc}")

    raise LLMCallError("both providers failed — " + "; ".join(errors))
