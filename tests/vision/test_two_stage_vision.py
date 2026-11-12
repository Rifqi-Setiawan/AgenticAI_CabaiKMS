"""D24: two-stage vision. Stage 1 = filename-blind visual call; stage 2 = deterministic filename match;
signal_fusion combines both. single_call mode keeps the <= D23 behaviour as a baseline."""
from __future__ import annotations

import pytest

from src.agents import vision_classification as vc
from src.agents.signal_fusion import FusionAction, fuse_photo_signals
from src.schema.contracts import ImageMetadata
from src.storage.document_contracts import PhotoContextSignal, VisionClassificationResult

IMG = b"\xff\xd8fake"
REGISTRY = ["Rikub 1", "Rikub 2", "Carabrina 01", "Katokkon"]


def _image(name: str) -> ImageMetadata:
    return ImageMetadata(file_id="f", filename=name, mime_type="image/webp", size=10, created_time="2026-11-12T00:00:00Z")


def _vcr(status="KNOWN", variety="Rikub 1", conf=0.9, consistent=True, text_conf=0.9):
    return VisionClassificationResult(
        classification_status=status, matched_variety=variety, identified_part="BUAH",
        visual_confidence=conf, text_confidence=text_conf, confidence=conf, visual_evidence="ciri buah",
        options_evaluated=REGISTRY, signals_consistent=consistent,
    )


def _recorder(result):
    calls = []

    def call(*, response_model, messages):
        calls.append(messages)
        return result

    call.calls = calls
    return call


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("CABAI_KMS_VISION_MODE", raising=False)


# ---------------------------------------------------------------- mode resolution
def test_default_mode_is_two_stage():
    assert vc.resolve_vision_mode() == "two_stage"


def test_env_selects_single_call_baseline(monkeypatch):
    monkeypatch.setenv("CABAI_KMS_VISION_MODE", "single_call")
    assert vc.resolve_vision_mode() == "single_call"
    assert vc.VisionSession(run_scope_varieties=REGISTRY, lvm_call=_recorder(_vcr())).independent_signals is False


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("CABAI_KMS_VISION_MODE", "both")
    with pytest.raises(ValueError):
        vc.resolve_vision_mode()


# ---------------------------------------------------------------- stage 1: what the model sees
def test_two_stage_prompt_has_no_filename_caption_or_hint():
    rec = _recorder(_vcr())
    session = vc.VisionSession(run_scope_varieties=REGISTRY, lvm_call=rec)
    sig = vc.extract_photo_context_signal("rikub_1_buah_07.webp", caption="Rikub 1 panen", known_varieties=REGISTRY)
    session.classify(_image("rikub_1_buah_07.webp"), image_bytes=IMG, photo_signal=sig)
    text = " ".join(
        part["text"] if isinstance(part, dict) and part.get("type") == "text" else (m["content"] if isinstance(m["content"], str) else "")
        for m in rec.calls[0] for part in (m["content"] if isinstance(m["content"], list) else [m])
    )
    assert "rikub_1_buah_07" not in text
    assert "Rikub 1 panen" not in text
    assert "Nama berkas:" not in text
    assert "Rikub 1" in rec.calls[0][0]["content"]  # the registry itself is still offered
    assert session.independent_signals is True


def test_single_call_prompt_keeps_filename():
    rec = _recorder(_vcr())
    session = vc.VisionSession(run_scope_varieties=REGISTRY, lvm_call=rec, mode="single_call")
    session.classify(_image("rikub_1_buah_07.webp"), image_bytes=IMG)
    assert "rikub_1_buah_07" in str(rec.calls[0])


def test_two_stage_recomputes_consistency_from_code_not_the_model():
    # The model claims consistency; it never saw the filename, so code must decide: hint Rikub 2 != visual Rikub 1.
    session = vc.VisionSession(run_scope_varieties=REGISTRY, lvm_call=_recorder(_vcr(consistent=True, text_conf=0.99)))
    sig = vc.extract_photo_context_signal("rikub_2_buah.webp", known_varieties=REGISTRY)
    assert sig.suggested_variety_hint == "Rikub 2"
    out = session.classify(_image("rikub_2_buah.webp"), image_bytes=IMG, photo_signal=sig)
    assert out.signals_consistent is False
    assert out.text_confidence == 0.85


def test_two_stage_without_hint_has_zero_text_confidence():
    session = vc.VisionSession(run_scope_varieties=REGISTRY, lvm_call=_recorder(_vcr(text_conf=0.7)))
    out = session.classify(_image("IMG_5101.webp"), image_bytes=IMG,
                           photo_signal=vc.extract_photo_context_signal("IMG_5101.webp", known_varieties=REGISTRY))
    assert out.text_confidence == 0.0
    assert out.signals_consistent is True


def test_stage_consistency_keeps_numbered_varieties_apart():
    assert vc.stage_signals_consistent("Rikub 1", "KNOWN", "Rikub 1") is True
    assert vc.stage_signals_consistent("Rikub 1", "KNOWN", "Rikub 2") is False
    assert vc.stage_signals_consistent("Cabe Rawit", "KNOWN", "cabai rawit") is True
    assert vc.stage_signals_consistent("Rikub 1", "OTHER", None) is False
    assert vc.stage_signals_consistent("Cabai rawit", "KNOWN", "Cabai rawit (Capsicum frutescens L)") is True
    assert vc.stage_signals_consistent("Carabrina 01", "KNOWN", "Carabrina 1") is True
    assert vc.stage_signals_consistent("Tabia Sala 1 IPB", "KNOWN", "Tabia Sala Kuning IPB") is False


def test_mock_still_receives_filename_out_of_band(monkeypatch):
    """CI mock derives its answer from the filename; in two-stage mode that must not require the prompt."""
    monkeypatch.setenv("CABAI_KMS_VISION_PROVIDER", "mock")
    session = vc.VisionSession(run_scope_varieties=["Katokkon", "Kopay"])
    out = session.classify(_image("katokkon_buah_01.jpg"), image_bytes=IMG)
    assert out.classification_status == "KNOWN"
    assert out.matched_variety == "Katokkon"
    assert out.identified_part == "BUAH"


# ---------------------------------------------------------------- fusion
def _fuse(hint, status, variety, conf, independent):
    return fuse_photo_signals(filename_match=hint, registry_known=REGISTRY,
                              visual_result=_vcr(status=status, variety=variety, conf=conf),
                              is_exact_hint=True, raw_filename="x.webp", independent_signals=independent)


def test_independent_contradiction_is_caught_even_at_low_confidence():
    assert _fuse("Carabrina 01", "KNOWN", "Katokkon", 0.70, True).action == FusionAction.REVIEW_MISMATCH
    # baseline: low confidence hides the contradiction behind REVIEW_UNCERTAIN
    assert _fuse("Carabrina 01", "KNOWN", "Katokkon", 0.70, False).action == FusionAction.REVIEW_UNCERTAIN


def test_numbered_varieties_conflict_only_with_exact_comparison():
    assert _fuse("Rikub 2", "KNOWN", "Rikub 1", 0.95, True).action == FusionAction.REVIEW_MISMATCH
    # baseline token-overlap rule treated "Rikub 1" and "Rikub 2" as consistent
    assert _fuse("Rikub 2", "KNOWN", "Rikub 1", 0.95, False).action == FusionAction.AUTO_LINK


def test_agreement_of_independent_signals_lifts_mid_confidence_to_auto_link():
    out = _fuse("Rikub 1", "KNOWN", "Rikub 1", 0.70, True)
    assert out.action == FusionAction.AUTO_LINK
    assert "agree" in out.reason
    assert _fuse("Rikub 1", "KNOWN", "Rikub 1", 0.70, False).action == FusionAction.REVIEW_UNCERTAIN
    assert _fuse("Rikub 1", "KNOWN", "Rikub 1", 0.55, True).action == FusionAction.REVIEW_UNCERTAIN


def test_no_hint_behaves_like_baseline():
    for conf, action in ((0.95, FusionAction.AUTO_LINK), (0.70, FusionAction.REVIEW_UNCERTAIN)):
        assert _fuse(None, "KNOWN", "Rikub 1", conf, True).action == action
        assert _fuse(None, "KNOWN", "Rikub 1", conf, False).action == action


def test_other_with_registered_filename_is_mismatch_in_both_modes():
    for independent in (True, False):
        assert _fuse("Katokkon", "OTHER", None, 0.9, independent).action == FusionAction.REVIEW_MISMATCH
