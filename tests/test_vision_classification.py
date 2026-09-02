from __future__ import annotations

import pytest

from src.agents import vision_classification
from src.agents.vision_classification import (
    FilenameSignal,
    VarietyDescription,
    VisionSession,
    build_knowledge_source_text,
    build_messages,
    classify_image,
    extract_filename_signal,
    load_variety_descriptions,
)
from src.schema.contracts import ImageMetadata

FAKE_IMAGE_BYTES = b"\xff\xd8\xfake-jpeg-bytes"


def _image(filename: str, file_id: str = "f1") -> ImageMetadata:
    return ImageMetadata(
        file_id=file_id,
        filename=filename,
        mime_type="image/jpeg",
        size=1024,
        created_time="2026-06-01T10:00:00Z",
    )


def _vision_result(status="KNOWN", variety="Gendot", part="DAUN", confidence=0.9, evidence="ok"):
    return vision_classification.VisionResult(
        classification_status=status,
        matched_variety=variety,
        identified_part=part,
        confidence=confidence,
        visual_evidence=evidence,
    )


def _fixed_lvm(result):
    def _call(*, response_model, messages):
        return result

    return _call


def _recording_lvm(result):
    calls = []

    def _call(*, response_model, messages):
        calls.append(messages)
        return result

    _call.calls = calls
    return _call


VARIETIES = [
    VarietyDescription("Gendot", {"habitus": "perdu", "tekstur daun": "kasap"}),
    VarietyDescription("Kopay", {"habitus": "terna", "tekstur daun": "halus"}),
]


class TestLoadVarietyDescriptions:
    def test_reads_real_template_dynamically(self):
        varieties = load_variety_descriptions()
        names = [v.name for v in varieties]
        assert "Gendot" in names
        assert "Kopay" in names
        gendot = next(v for v in varieties if v.name == "Gendot")
        assert gendot.characteristics.get("habitus") == "perdu"

    def test_ten_varieties_match_template(self):
        assert len(load_variety_descriptions()) == 10


class TestBuildKnowledgeSourceText:
    def test_includes_every_variety_name_and_characteristic(self):
        text = build_knowledge_source_text(VARIETIES)
        assert "Gendot" in text
        assert "habitus=perdu" in text
        assert "Kopay" in text
        assert "tekstur daun=halus" in text


class TestExtractFilenameSignal:
    def test_detects_part_keyword(self):
        signal = extract_filename_signal("cabai katokon - bentuk daun.jpg", ["Gendot", "Katokkon"])
        assert signal.suggested_part == "DAUN"

    def test_detects_variety_substring(self):
        signal = extract_filename_signal("Gendot - tinggi tanaman.jpg", ["Gendot", "Kopay"])
        assert signal.suggested_variety == "Gendot"

    def test_no_signal_when_nothing_matches(self):
        signal = extract_filename_signal("IMG_0001.jpg", ["Gendot", "Kopay"])
        assert signal.suggested_part is None
        assert signal.suggested_variety is None

    def test_typo_variety_name_is_not_fuzzy_matched(self):
        # real filename spells "katokon", template says "Katokkon" — a
        # deliberate limitation (simple substring match), not a bug
        signal = extract_filename_signal("cabai katokon - bentuk daun.jpg", ["Katokkon"])
        assert signal.suggested_variety is None


class TestBuildMessages:
    def test_message_structure_and_content(self):
        signal = FilenameSignal(suggested_part="DAUN", suggested_variety="Gendot")
        messages = build_messages(FAKE_IMAGE_BYTES, "image/jpeg", "gendot_daun.jpg", "- Gendot: habitus=perdu", signal)

        assert messages[0]["role"] == "system"
        assert "habitus=perdu" in messages[0]["content"]

        assert messages[1]["role"] == "user"
        content = messages[1]["content"]
        text_block = next(b for b in content if b["type"] == "text")
        image_block = next(b for b in content if b["type"] == "image_url")

        assert "gendot_daun.jpg" in text_block["text"]
        assert "DAUN" in text_block["text"]
        assert "Gendot" in text_block["text"]
        assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_no_signal_produces_neutral_hint_text(self):
        signal = FilenameSignal(suggested_part=None, suggested_variety=None)
        messages = build_messages(FAKE_IMAGE_BYTES, "image/jpeg", "IMG_0001.jpg", "-", signal)
        text_block = next(b for b in messages[1]["content"] if b["type"] == "text")
        assert "Tidak ada sinyal jelas" in text_block["text"]


class TestClassifyImage:
    def test_returns_valid_vision_result_with_injected_bytes(self):
        expected = _vision_result()
        result = classify_image(
            _image("x.jpg"), "- Gendot: habitus=perdu", VARIETIES,
            image_bytes=FAKE_IMAGE_BYTES, lvm_call=_fixed_lvm(expected),
        )
        assert result is expected

    def test_raises_type_error_on_bad_lvm_return(self):
        with pytest.raises(TypeError):
            classify_image(
                _image("x.jpg"), "-", VARIETIES,
                image_bytes=FAKE_IMAGE_BYTES, lvm_call=_fixed_lvm({"not": "a VisionResult"}),
            )

    @pytest.mark.parametrize("status", ["KNOWN", "OTHER", "UNCERTAIN"])
    def test_all_three_statuses_pass_through_unmodified(self, status):
        expected = _vision_result(status=status, variety=None if status != "KNOWN" else "Gendot")
        result = classify_image(
            _image("x.jpg"), "-", VARIETIES,
            image_bytes=FAKE_IMAGE_BYTES, lvm_call=_fixed_lvm(expected),
        )
        assert result.classification_status == status

    def test_filename_signal_is_included_in_prompt_but_does_not_touch_output(self):
        """The core guarantee from the brief: a filename hint never
        overrides a conflicting visual result. Filename here screams
        "daun" (leaf); the mocked LVM insists on "BUAH" (fruit) — the
        final result must still be BUAH, and the filename hint must have
        reached the prompt (so it *was* offered as context)."""
        visual_result = _vision_result(part="BUAH", variety=None, status="KNOWN")
        recorder = _recording_lvm(visual_result)

        result = classify_image(
            _image("daun_daun_daun.jpg"), "- Gendot: habitus=perdu", VARIETIES,
            image_bytes=FAKE_IMAGE_BYTES, lvm_call=recorder,
        )

        assert result.identified_part == "BUAH"  # visual result wins, unmodified
        text_block = next(b for b in recorder.calls[0][1]["content"] if b["type"] == "text")
        assert "DAUN" in text_block["text"]  # the hint really was offered as context

    def test_no_consensus_by_default_second_voter_never_called(self):
        called = []

        def exploding_second_voter(*, response_model, messages):
            called.append(1)
            raise AssertionError("should not be called when consensus=False")

        result = classify_image(
            _image("x.jpg"), "-", VARIETIES,
            image_bytes=FAKE_IMAGE_BYTES,
            lvm_call=_fixed_lvm(_vision_result()),
            second_voter_call=exploding_second_voter,
        )
        assert called == []
        assert result.classification_status == "KNOWN"


class TestConsensus:
    def test_agreement_boosts_confidence_and_keeps_decision(self):
        primary = _vision_result(part="DAUN", variety="Gendot", confidence=0.7)
        secondary = _vision_result(part="DAUN", variety="Gendot", confidence=0.8)

        result = classify_image(
            _image("x.jpg"), "-", VARIETIES,
            image_bytes=FAKE_IMAGE_BYTES,
            lvm_call=_fixed_lvm(primary),
            consensus=True,
            second_voter_call=_fixed_lvm(secondary),
        )

        assert result.identified_part == "DAUN"
        assert result.matched_variety == "Gendot"
        assert result.confidence > 0.75  # boosted above the simple average's midpoint

    def test_disagreement_downgrades_to_uncertain_and_lowers_confidence(self):
        primary = _vision_result(part="DAUN", variety="Gendot", confidence=0.9, status="KNOWN")
        secondary = _vision_result(part="BUAH", variety="Kopay", confidence=0.6, status="KNOWN")

        result = classify_image(
            _image("x.jpg"), "-", VARIETIES,
            image_bytes=FAKE_IMAGE_BYTES,
            lvm_call=_fixed_lvm(primary),
            consensus=True,
            second_voter_call=_fixed_lvm(secondary),
        )

        assert result.classification_status == "UNCERTAIN"
        assert result.confidence == pytest.approx(0.6)  # min of the two
        assert "consensus mismatch" in result.visual_evidence
        # the returned decision still has to be *some* valid part/variety —
        # kept as the primary's, not silently invented
        assert result.identified_part == "DAUN"

    def test_second_voter_bad_return_type_raises(self):
        with pytest.raises(TypeError):
            classify_image(
                _image("x.jpg"), "-", VARIETIES,
                image_bytes=FAKE_IMAGE_BYTES,
                lvm_call=_fixed_lvm(_vision_result()),
                consensus=True,
                second_voter_call=_fixed_lvm({"not": "a VisionResult"}),
            )


class TestVisionSession:
    def test_reads_knowledge_source_exactly_once_for_a_whole_batch(self, monkeypatch):
        calls = []
        original = vision_classification.load_variety_descriptions

        def spy(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(vision_classification, "load_variety_descriptions", spy)

        session = VisionSession(lvm_call=_fixed_lvm(_vision_result()))
        assert len(calls) == 1

        session.classify(_image("a.jpg"), image_bytes=FAKE_IMAGE_BYTES)
        session.classify(_image("b.jpg"), image_bytes=FAKE_IMAGE_BYTES)
        session.classify_batch(
            [_image("c.jpg", "fc"), _image("d.jpg", "fd")],
            image_bytes_map={"fc": FAKE_IMAGE_BYTES, "fd": FAKE_IMAGE_BYTES},
        )

        assert len(calls) == 1  # still just the one read from __init__

    def test_classify_batch_returns_one_result_per_image(self):
        session = VisionSession(lvm_call=_fixed_lvm(_vision_result()))
        images = [_image("a.jpg", "fa"), _image("b.jpg", "fb"), _image("c.jpg", "fc")]
        results = session.classify_batch(
            images, image_bytes_map={img.file_id: FAKE_IMAGE_BYTES for img in images}
        )
        assert len(results) == 3
        assert all(r.classification_status == "KNOWN" for r in results)

    def test_session_carries_consensus_setting_to_every_classification(self):
        primary = _vision_result(part="DAUN", variety="Gendot", confidence=0.7)
        secondary = _vision_result(part="BATANG", variety="Kopay", confidence=0.6)

        session = VisionSession(
            lvm_call=_fixed_lvm(primary),
            consensus=True,
            second_voter_call=_fixed_lvm(secondary),
        )
        result = session.classify(_image("x.jpg"), image_bytes=FAKE_IMAGE_BYTES)
        assert result.classification_status == "UNCERTAIN"  # consensus mismatch applied
