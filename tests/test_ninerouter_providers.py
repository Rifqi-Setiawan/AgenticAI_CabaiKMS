from __future__ import annotations

import base64
import struct
from types import SimpleNamespace
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from src.llm.openai_compatible import (
    NINEROUTER_DEFAULT_BASE_URL,
    NINEROUTER_REQUIRED_TEXT_MODEL,
    NINEROUTER_REQUIRED_VISION_MODEL,
    NinerouterConfig,
    openai_instructor_client,
)
from src.llm.providers import LLMCallError, call_ninerouter_text, call_with_fallback
from src.llm.telemetry import drain_provider_calls
from src.llm.vision_providers import VisionCallError, call_ninerouter_vision, call_vision
from src.reliability.provider_failures import (
    ProviderFailureKind,
    classify_ninerouter_exception,
)


class _TextResult(BaseModel):
    answer: str


class _VisionResult(BaseModel):
    status: str


@pytest.fixture
def ninerouter_env(monkeypatch):
    monkeypatch.setenv("CABAI_KMS_TEXT_PROVIDER", "9router")
    monkeypatch.setenv("CABAI_KMS_VISION_PROVIDER", "9router")
    monkeypatch.setenv("NINEROUTER_BASE_URL", NINEROUTER_DEFAULT_BASE_URL)
    monkeypatch.setenv("NINEROUTER_API_KEY", "unit-test-secret")
    monkeypatch.setenv("NINEROUTER_TEXT_MODEL", NINEROUTER_REQUIRED_TEXT_MODEL)
    monkeypatch.setenv("NINEROUTER_VISION_MODEL", NINEROUTER_REQUIRED_VISION_MODEL)
    monkeypatch.setenv("NINEROUTER_TIMEOUT_SECONDS", "60")
    drain_provider_calls()


def _client(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_live_image_fixture_is_a_safe_64px_png():
    fixture = Path("tests/fixtures/ninerouter_preflight_image.b64")
    raw = base64.b64decode(fixture.read_text(encoding="ascii").strip(), validate=True)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", raw[16:24]) == (64, 64)


def test_configuration_uses_windows_loopback_and_role_specific_models(ninerouter_env):
    config = NinerouterConfig.from_env()
    assert config.base_url == "http://127.0.0.1:20128/v1"
    assert config.text_model == NINEROUTER_REQUIRED_TEXT_MODEL
    assert config.vision_model == NINEROUTER_REQUIRED_VISION_MODEL


def test_text_and_vision_configuration_are_independent(monkeypatch, ninerouter_env):
    monkeypatch.delenv("NINEROUTER_VISION_MODEL")
    assert NinerouterConfig.from_env(require_role="text").text_model == NINEROUTER_REQUIRED_TEXT_MODEL
    monkeypatch.setenv("NINEROUTER_VISION_MODEL", NINEROUTER_REQUIRED_VISION_MODEL)
    monkeypatch.delenv("NINEROUTER_TEXT_MODEL")
    assert NinerouterConfig.from_env(require_role="vision").vision_model == NINEROUTER_REQUIRED_VISION_MODEL


@pytest.mark.parametrize("variable", ["NINEROUTER_API_KEY", "NINEROUTER_TEXT_MODEL", "NINEROUTER_VISION_MODEL"])
def test_required_configuration_is_not_silently_substituted(monkeypatch, ninerouter_env, variable):
    monkeypatch.delenv(variable)
    with pytest.raises(Exception) as exc_info:
        NinerouterConfig.from_env()
    assert variable in str(exc_info.value)


@pytest.mark.parametrize("url", ["localhost", "ftp://127.0.0.1:20128/v1", "http://user:secret@127.0.0.1:20128/v1", "http://127.0.0.1:20128"])
def test_invalid_base_url_fails_configuration(monkeypatch, ninerouter_env, url):
    monkeypatch.setenv("NINEROUTER_BASE_URL", url)
    with pytest.raises(Exception):
        NinerouterConfig.from_env()


def test_alternative_text_model_is_rejected(monkeypatch, ninerouter_env):
    monkeypatch.setenv("NINEROUTER_TEXT_MODEL", "some/other-model")
    with pytest.raises(Exception) as exc_info:
        NinerouterConfig.from_env()
    assert NINEROUTER_REQUIRED_TEXT_MODEL in str(exc_info.value)


def test_non_high_vision_model_is_rejected(monkeypatch, ninerouter_env):
    monkeypatch.setenv("NINEROUTER_VISION_MODEL", NINEROUTER_REQUIRED_TEXT_MODEL)
    with pytest.raises(Exception) as exc_info:
        NinerouterConfig.from_env(require_role="vision")
    assert NINEROUTER_REQUIRED_VISION_MODEL in str(exc_info.value)


def test_openai_client_disables_sdk_retries(monkeypatch):
    captured = {}
    raw = object()
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: captured.update(kwargs) or raw)
    monkeypatch.setattr("instructor.from_openai", lambda client, mode: (client, mode))
    wrapped = openai_instructor_client(
        base_url=NINEROUTER_DEFAULT_BASE_URL, api_key="secret", timeout_seconds=60
    )
    assert wrapped[0] is raw
    import instructor

    assert wrapped[1] is instructor.Mode.MD_JSON
    assert captured == {
        "base_url": NINEROUTER_DEFAULT_BASE_URL,
        "api_key": "secret",
        "timeout": 60,
        "max_retries": 0,
    }


def test_text_dispatch_uses_fixed_model_and_response_model(monkeypatch, ninerouter_env):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _TextResult(answer="ok")

    monkeypatch.setattr("src.llm.providers.ninerouter_instructor_client", lambda config: _client(create))
    monkeypatch.setattr("src.llm.providers._call_legacy", lambda **_: pytest.fail("legacy called"))
    result = call_with_fallback(response_model=_TextResult, messages=[{"role": "user", "content": "hi"}])
    assert result.answer == "ok"
    assert captured["model"] == NINEROUTER_REQUIRED_TEXT_MODEL
    assert captured["response_model"] is _TextResult


def test_sanitized_trace_counts_application_attempts(monkeypatch, ninerouter_env):
    monkeypatch.setattr(
        "src.llm.providers.ninerouter_instructor_client",
        lambda config: _client(lambda **_: _TextResult(answer="ok")),
    )
    for _ in range(2):
        call_ninerouter_text(response_model=_TextResult, messages=[])
    records = drain_provider_calls()
    assert [record["attempt"] for record in records] == [1, 2]
    assert all(record["selected_account"] == "unknown" for record in records)


def test_vision_dispatch_preserves_multimodal_payload(monkeypatch, ninerouter_env):
    payload = [{"role": "user", "content": [
        {"type": "text", "text": "classify"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,c2FmZQ=="}},
    ]}]
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return _VisionResult(status="KNOWN")

    monkeypatch.setattr("src.llm.vision_providers.ninerouter_instructor_client", lambda config: _client(create))
    monkeypatch.setattr("src.llm.vision_providers.call_gemini", lambda **_: pytest.fail("legacy called"))
    result = call_vision(response_model=_VisionResult, messages=payload)
    assert result.status == "KNOWN"
    assert captured["model"] == NINEROUTER_REQUIRED_VISION_MODEL
    assert captured["messages"] is payload


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, ProviderFailureKind.AUTHENTICATION), (404, ProviderFailureKind.MODEL_NOT_FOUND),
     (400, ProviderFailureKind.INVALID_REQUEST), (429, ProviderFailureKind.RATE_LIMIT),
     (503, ProviderFailureKind.TRANSIENT_UPSTREAM), (415, ProviderFailureKind.UNSUPPORTED_MULTIMODAL)],
)
def test_ninerouter_error_classification(status, expected):
    error = type("StatusError", (Exception,), {"status_code": status})()
    assert classify_ninerouter_exception(error) is expected


def test_invalid_structured_outputs_remain_revisable(monkeypatch, ninerouter_env):
    invalid = ValidationError.from_exception_data("Result", [])
    monkeypatch.setattr(
        "src.llm.providers.ninerouter_instructor_client",
        lambda config: _client(lambda **_: (_ for _ in ()).throw(invalid)),
    )
    with pytest.raises(ValidationError):
        call_ninerouter_text(response_model=_TextResult, messages=[])

    monkeypatch.setattr(
        "src.llm.vision_providers.ninerouter_instructor_client",
        lambda config: _client(lambda **_: (_ for _ in ()).throw(invalid)),
    )
    with pytest.raises(ValidationError):
        call_ninerouter_vision(response_model=_VisionResult, messages=[])


def test_errors_and_telemetry_do_not_leak_key_or_image(monkeypatch, ninerouter_env):
    image = "data:image/png;base64,VERY-SENSITIVE-IMAGE"
    error = type("StatusError", (Exception,), {"status_code": 401})("unit-test-secret " + image)
    monkeypatch.setattr(
        "src.llm.vision_providers.ninerouter_instructor_client",
        lambda config: _client(lambda **_: (_ for _ in ()).throw(error)),
    )
    with pytest.raises(VisionCallError) as exc_info:
        call_ninerouter_vision(
            response_model=_VisionResult,
            messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}]}],
        )
    combined = str(exc_info.value) + repr(drain_provider_calls())
    assert "unit-test-secret" not in combined
    assert "VERY-SENSITIVE-IMAGE" not in combined


def test_explicit_legacy_modes_still_dispatch(monkeypatch, ninerouter_env):
    monkeypatch.setenv("CABAI_KMS_TEXT_PROVIDER", "legacy")
    monkeypatch.setenv("CABAI_KMS_VISION_PROVIDER", "legacy")
    monkeypatch.setattr("src.llm.providers._call_legacy", lambda **_: _TextResult(answer="legacy"))
    monkeypatch.setattr("src.llm.vision_providers.call_gemini", lambda **_: _VisionResult(status="legacy"))
    assert call_with_fallback(response_model=_TextResult, messages=[]).answer == "legacy"
    assert call_vision(response_model=_VisionResult, messages=[]).status == "legacy"


def test_ninerouter_consensus_does_not_call_second_voter(monkeypatch, ninerouter_env):
    from src.agents.vision_classification import VarietyDescription, classify_image
    from src.schema.contracts import ImageMetadata, VisionResult

    primary = VisionResult(classification_status="OTHER", matched_variety=None,
                           identified_part="DAUN", confidence=0.4, visual_evidence="unclear")
    image_meta = ImageMetadata(file_id="x", filename="x.png", mime_type="image/png", size=1,
                               created_time="2026-01-01T00:00:00Z")
    result = classify_image(
        image_meta, "-", [VarietyDescription("Gendot", {})], image_bytes=b"x",
        lvm_call=lambda **_: primary, consensus=True,
        second_voter_call=lambda **_: pytest.fail("second voter called"),
    )
    assert result is primary
