from __future__ import annotations

import pytest
from pydantic import BaseModel

from src.llm.vision_providers import VisionCallError, call_gemini, call_second_voter


class _Dummy(BaseModel):
    x: int


def test_call_gemini_raises_cleanly_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(VisionCallError):
        call_gemini(response_model=_Dummy, messages=[{"role": "user", "content": "hi"}])


@pytest.mark.llm_fallback_live  # real localhost connection attempt, ~15-20s
def test_call_second_voter_raises_when_neither_provider_is_configured(monkeypatch):
    """Neither OPENROUTER_API_KEY nor a local Ollama server exists in this
    dev environment — exercising the real failure path proves it fails
    loudly with both underlying errors, matching call_with_fallback's
    behavior in src/llm/providers.py."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(VisionCallError) as exc_info:
        call_second_voter(response_model=_Dummy, messages=[{"role": "user", "content": "hi"}], max_retries=1)

    message = str(exc_info.value)
    assert "openrouter" in message
    assert "ollama" in message
