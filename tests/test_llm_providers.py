from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from src.llm.providers import LLMCallError, _groq_instructor_client, call_with_fallback
from src.reliability.provider_failures import ProviderFailureKind


class _Dummy(BaseModel):
    x: int


def test_missing_groq_key_is_classified_as_configuration_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMCallError) as exc_info:
        _groq_instructor_client()
    assert exc_info.value.failure_kind is ProviderFailureKind.NON_RETRYABLE_CONFIGURATION


def test_groq_failure_still_falls_back_to_ollama(monkeypatch):
    calls = []

    def create_primary(**kwargs):
        calls.append("groq")
        raise ConnectionError("temporary")

    def create_fallback(**kwargs):
        calls.append("ollama")
        return _Dummy(x=1)

    monkeypatch.setattr(
        "src.llm.providers._groq_instructor_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_primary)),
        ),
    )
    monkeypatch.setattr(
        "src.llm.providers._ollama_instructor_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_fallback)),
        ),
    )

    result = call_with_fallback(
        response_model=_Dummy, messages=[{"role": "user", "content": "hi"}],
    )
    assert result == _Dummy(x=1)
    assert calls == ["groq", "ollama"]


def test_final_fallback_contract_error_remains_revisable(monkeypatch):
    def primary_unavailable():
        raise ConnectionError("temporary")

    def invalid_contract(**kwargs):
        raise ValidationError.from_exception_data("SchemaMapping", [])

    monkeypatch.setattr(
        "src.llm.providers._groq_instructor_client",
        primary_unavailable,
    )
    monkeypatch.setattr(
        "src.llm.providers._ollama_instructor_client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=invalid_contract)),
        ),
    )
    with pytest.raises(ValidationError):
        call_with_fallback(
            response_model=_Dummy, messages=[{"role": "user", "content": "hi"}],
        )


@pytest.mark.llm_fallback_live  # real localhost connection attempt, ~15-20s
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
