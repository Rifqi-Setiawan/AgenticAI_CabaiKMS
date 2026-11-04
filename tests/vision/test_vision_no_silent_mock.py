"""D18: the vision dispatcher must never silently substitute the deterministic mock for a failed real call.

Before D18, default_lvm_call() returned the mock when the provider raised or no key was set. The mock answers KNOWN from
the filename alone (confidence 0.90) and always reports part DAUN, so those rows looked like real model output
(19 of 160 photos in the 1 Nov 2026 evaluation run). These tests pin the new behaviour.
"""
from datetime import datetime, timezone

import pytest

from src.agents import vision_classification as vc
from src.schema.contracts import ImageMetadata, VisionResult

MESSAGES = [
    {"role": "system", "content": "Daftar varietas:\n- Jalapeno: (tidak ada deskripsi tercatat)"},
    {"role": "user", "content": [{"type": "text", "text": "Nama berkas: 'jalapeno_buah_001.jpg'"}]},
]


@pytest.fixture
def real_mode(monkeypatch: pytest.MonkeyPatch):
    """Production provider mode. PYTEST_CURRENT_TEST is re-set by pytest at the start of the call phase,
    so each test removes it again with leave_pytest() right before exercising the dispatcher."""
    monkeypatch.setenv("CABAI_KMS_VISION_PROVIDER", "9router")
    return monkeypatch


def leave_pytest(mp: pytest.MonkeyPatch) -> None:
    mp.delenv("PYTEST_CURRENT_TEST", raising=False)


def test_missing_key_raises_instead_of_mock(real_mode):
    for key in ("NINEROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        real_mode.delenv(key, raising=False)
    leave_pytest(real_mode)
    with pytest.raises(vc.VisionProviderUnavailable):
        vc.default_lvm_call(response_model=VisionResult, messages=MESSAGES)


def test_provider_error_propagates_instead_of_mock(real_mode):
    real_mode.setenv("NINEROUTER_API_KEY", "unit-test-secret")

    def boom(**kwargs):
        raise RuntimeError("provider down")

    real_mode.setattr(vc, "call_vision", boom)
    mock_called = []
    real_mode.setattr(vc, "deterministic_mock_lvm", lambda **kw: mock_called.append(1))
    leave_pytest(real_mode)
    with pytest.raises(RuntimeError, match="provider down"):
        vc.default_lvm_call(response_model=VisionResult, messages=MESSAGES)
    assert mock_called == []


def test_explicit_mock_mode_still_available(real_mode):
    real_mode.setenv("CABAI_KMS_VISION_PROVIDER", "mock")
    leave_pytest(real_mode)
    res = vc.default_lvm_call(response_model=VisionResult, messages=MESSAGES)
    assert isinstance(res, VisionResult)


def test_session_classify_surfaces_failure_to_caller(real_mode):
    """vision_hook catches this exception and records the photo as FAILED (no fabricated KNOWN)."""
    real_mode.setenv("NINEROUTER_API_KEY", "unit-test-secret")

    def boom(**kwargs):
        raise RuntimeError("contract retries exhausted")

    real_mode.setattr(vc, "call_vision", boom)
    session = vc.VisionSession(run_scope_varieties=["Jalapeno"])
    image = ImageMetadata(file_id="f1", filename="jalapeno_buah_001.jpg", mime_type="image/jpeg", size=3,
                          created_time=datetime(2026, 11, 4, tzinfo=timezone.utc))
    leave_pytest(real_mode)
    with pytest.raises(RuntimeError, match="contract retries exhausted"):
        session.classify(image, image_bytes=b"abc")
