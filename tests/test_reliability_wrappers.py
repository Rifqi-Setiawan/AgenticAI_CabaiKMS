from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.vision_classification import VarietyDescription
from src.llm.providers import LLMCallError
from src.llm.vision_providers import VisionCallError
from src.reliability.rate_limit import RateLimiter
from src.reliability.wrappers import safe_classify_image, safe_rerank
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, ImageMetadata, SchemaMapping, VisionResult
from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile

FAST = {"max_retry_attempts": 3, "retry_base_delay": 0.001, "retry_max_delay": 0.01}


def _image(file_id="f1") -> ImageMetadata:
    return ImageMetadata(
        file_id=file_id, filename="daun.jpg", mime_type="image/jpeg", size=100,
        created_time="2026-01-01T00:00:00Z",
    )


def _vision(status="KNOWN", variety="Gendot", part="DAUN", confidence=0.9, evidence="ok"):
    return VisionResult(
        classification_status=status, matched_variety=variety, identified_part=part,
        confidence=confidence, visual_evidence=evidence,
    )


def _mapping(target_row="r_1", confidence=0.9, attribute="x"):
    return SchemaMapping(
        source_attribute=attribute, source_format="row-oriented", target_canonical_row=target_row,
        confidence=confidence, reasoning="test fixture", normalization_required=False,
    )


VARIETIES = [VarietyDescription("Gendot", {"habitus": "perdu"})]


@pytest.fixture(scope="module")
def schema() -> CanonicalSchema:
    return CanonicalSchema.from_template()


class TestSafeClassifyImageDownload:
    def test_image_link_inaccessible_records_error_trace(self):
        def always_fails_download(file_id, service=None):
            raise ConnectionError("simulated network failure")

        import src.reliability.wrappers as w

        original = w.download_image_bytes
        w.download_image_bytes = always_fails_download
        try:
            state = {"error_trace": []}
            result, patch = safe_classify_image(_image(), "-", VARIETIES, state, **FAST)
        finally:
            w.download_image_bytes = original

        assert result is None
        assert "link citra tak terakses" in patch["error_trace"][0]
        assert "f1" in patch["error_trace"][0]

    def test_transient_download_failure_is_retried_and_recovers(self):
        attempts = []

        def flaky_download(file_id, service=None):
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("transient")
            return b"real-bytes"

        import src.reliability.wrappers as w

        original = w.download_image_bytes
        w.download_image_bytes = flaky_download
        try:
            state = {"error_trace": []}
            result, patch = safe_classify_image(
                _image(), "-", VARIETIES, state, lvm_call=lambda **_: _vision(), **FAST
            )
        finally:
            w.download_image_bytes = original

        assert len(attempts) == 2
        assert result.classification_status == "KNOWN"
        assert patch == {}


class TestSafeClassifyImageClassification:
    def test_transient_vision_call_error_is_retried_and_recovers(self):
        attempts = []

        def flaky_lvm(*, response_model, messages):
            attempts.append(1)
            if len(attempts) < 2:
                raise VisionCallError("transient provider hiccup")
            return _vision()

        state = {"error_trace": []}
        result, patch = safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x", lvm_call=flaky_lvm, **FAST
        )
        assert len(attempts) == 2
        assert result.classification_status == "KNOWN"
        assert patch == {}

    def test_contract_violation_is_revised_and_recovers(self):
        attempts = []

        def flaky_contract_lvm(*, response_model, messages):
            attempts.append(1)
            if len(attempts) < 2:
                raise ValidationError.from_exception_data("VisionResult", [])
            return _vision()

        state = {"error_trace": []}
        result, patch = safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x", lvm_call=flaky_contract_lvm,
            max_revisions=2, **FAST,
        )
        assert len(attempts) == 2
        assert result.classification_status == "KNOWN"
        assert patch == {}

    def test_format_invalid_exhausts_revisions_and_falls_to_manual_review(self):
        def always_invalid_lvm(*, response_model, messages):
            raise ValidationError.from_exception_data("VisionResult", [])

        state = {"error_trace": []}
        result, patch = safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x", lvm_call=always_invalid_lvm,
            max_revisions=1, **FAST,
        )
        assert result is None
        assert "manual_review" in patch["error_trace"][-1]

    def test_persistent_vision_call_error_does_not_crash_the_caller(self):
        """Regression test for a real bug: once run_with_retry exhausts its
        own retries and re-raises VisionCallError, that exception must
        still be caught by the OUTER verify-then-revise loop (it's in
        VISION_REVISABLE_EXCEPTIONS) rather than propagating uncaught and
        crashing the whole pipeline over one image's provider failure —
        this actually happened against a real exhausted Groq quota."""

        def always_fails(*, response_model, messages):
            raise VisionCallError("simulated persistent provider failure")

        state = {"error_trace": []}
        result, patch = safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x", lvm_call=always_fails,
            max_revisions=1, **FAST,
        )
        assert result is None
        assert "manual_review" in patch["error_trace"][-1]

    def test_uncertain_status_is_returned_but_flagged_for_review(self):
        state = {"error_trace": []}
        result, patch = safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x",
            lvm_call=lambda **_: _vision(status="UNCERTAIN", variety=None, confidence=0.3, evidence="blurry"),
            **FAST,
        )
        assert result.classification_status == "UNCERTAIN"
        assert "status UNCERTAIN" in patch["error_trace"][0]
        assert "blurry" in patch["error_trace"][0]

    def test_known_confident_result_produces_empty_patch(self):
        state = {"error_trace": []}
        result, patch = safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x", lvm_call=lambda **_: _vision(), **FAST
        )
        assert result.classification_status == "KNOWN"
        assert patch == {}

    def test_rate_limiter_is_used_when_provided(self):
        limiter = RateLimiter(max_rate=100, time_period=60)
        acquired = []
        original = limiter.acquire_sync

        def spy_acquire(*a, **k):
            acquired.append(1)
            return original(*a, **k)

        limiter.acquire_sync = spy_acquire

        state = {"error_trace": []}
        safe_classify_image(
            _image(), "-", VARIETIES, state, image_bytes=b"x", lvm_call=lambda **_: _vision(),
            rate_limiter=limiter, **FAST,
        )
        assert len(acquired) >= 1
        limiter.close()


class TestSafeRerank:
    def test_exact_seed_alias_maps_without_manual_review_or_llm(self, schema):
        profile = SourceAttributeProfile(
            attribute_name="Seeds per mature fruit",
            structural_context="Mature Fruit",
            sample_values=["35", "42"],
        )
        state = {"error_trace": []}

        def must_not_call_llm(**kwargs):
            pytest.fail("Exact curated aliases must bypass the LLM")

        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema,
            llm_call=must_not_call_llm, **FAST,
        )

        assert schema.row_by_id(mapping.target_canonical_row).label == "jumlah biji/buah masak"
        assert patch == {}

    def test_persistent_llm_call_error_does_not_crash_the_caller(self, schema):
        """Regression test for a real bug: a rate limit that persists
        across every retry attempt used to propagate LLMCallError straight
        out of safe_rerank uncaught, crashing the whole pipeline run over
        one attribute's provider failure — confirmed against a real
        exhausted Groq daily quota, not a hypothetical."""

        def always_rate_limited(*, response_model, messages):
            raise LLMCallError("simulated persistent rate limit")

        profile = SourceAttributeProfile(attribute_name="x")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema,
            llm_call=always_rate_limited, max_revisions=1, **FAST,
        )
        assert mapping is None
        assert "manual_review" in patch["error_trace"][-1]

    def test_transient_llm_call_error_is_retried_and_recovers(self, schema):
        attempts = []

        def flaky_llm_call(*, response_model, messages):
            attempts.append(1)
            if len(attempts) < 2:
                raise LLMCallError("transient")
            return _mapping()

        profile = SourceAttributeProfile(attribute_name="x")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema, llm_call=flaky_llm_call, **FAST
        )
        assert len(attempts) == 2
        assert mapping.target_canonical_row == "r_1"
        assert patch == {}

    def test_contract_violation_is_revised_and_recovers(self, schema):
        attempts = []

        def flaky_contract_llm(*, response_model, messages):
            attempts.append(1)
            if len(attempts) < 2:
                raise ValidationError.from_exception_data("SchemaMapping", [])
            return _mapping()

        profile = SourceAttributeProfile(attribute_name="x")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema, llm_call=flaky_contract_llm,
            max_revisions=2, **FAST,
        )
        assert len(attempts) == 2
        assert mapping.target_canonical_row == "r_1"
        assert patch == {}

    def test_format_invalid_exhausts_revisions_and_falls_to_manual_review(self, schema):
        def always_invalid_llm(*, response_model, messages):
            raise ValidationError.from_exception_data("SchemaMapping", [])

        profile = SourceAttributeProfile(attribute_name="x")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema, llm_call=always_invalid_llm,
            max_revisions=1, **FAST,
        )
        assert mapping is None
        assert "manual_review" in patch["error_trace"][-1]

    def test_unmapped_attribute_null_target_is_flagged_via_review_queue(self, schema):
        profile = SourceAttributeProfile(attribute_name="Nama Kolektor")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema,
            llm_call=lambda **_: _mapping(target_row=NULL_ROW, attribute="Nama Kolektor"), **FAST,
        )
        assert mapping.target_canonical_row == NULL_ROW
        assert "tidak punya padanan baris kanonik" in patch["error_trace"][0]

    def test_low_confidence_mapping_is_flagged_via_review_queue(self, schema):
        profile = SourceAttributeProfile(attribute_name="x")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema,
            llm_call=lambda **_: _mapping(confidence=0.1), confidence_threshold=0.6, **FAST,
        )
        assert mapping.confidence == 0.1
        assert "confidence" in patch["error_trace"][0].lower()

    def test_confident_mapping_produces_empty_patch(self, schema):
        profile = SourceAttributeProfile(attribute_name="x")
        state = {"error_trace": []}
        mapping, patch = safe_rerank(
            profile, [], state, source_format="row-oriented", schema=schema,
            llm_call=lambda **_: _mapping(confidence=0.95), **FAST,
        )
        assert mapping.confidence == 0.95
        assert patch == {}
