from __future__ import annotations

import pytest
from pydantic import BaseModel

from src.llm.providers import LLMCallError, call_with_fallback

pytestmark = pytest.mark.llm_fallback_live  # real localhost connection attempt, ~15-20s


class _Dummy(BaseModel):
    x: int


def test_call_with_fallback_raises_when_neither_provider_is_configured(monkeypatch):
    """This dev environment has no GROQ_API_KEY and no local Ollama server —
    exercising the real failure path (not mocked) proves the fallback
    boundary fails loudly with both underlying errors, rather than hanging
    or raising something unhandled."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(LLMCallError) as exc_info:
        call_with_fallback(
            response_model=_Dummy,
            messages=[{"role": "user", "content": "hi"}],
            max_retries=1,
        )

    message = str(exc_info.value)
    assert "groq" in message
    assert "ollama" in message
