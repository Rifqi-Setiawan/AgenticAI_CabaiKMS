from __future__ import annotations

from types import SimpleNamespace

import openpyxl
from pandas.testing import assert_frame_equal
import pytest

from src.agents.schema_matching.anchor import AnchorResult
from src.agents.schema_matching.retrieval import RetrievalHit
from src.reliability.rate_limit import RuntimeRateLimitConfig
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import ImageMetadata, SchemaMapping, VisionResult
from src.ui import pipeline_runner as runner
from tests.test_source_parsing import flat_observations


class _FakeLimiter:
    instances: list["_FakeLimiter"] = []

    def __init__(self, max_rate=10, time_period=60.0):
        self.max_rate = max_rate
        self.time_period = time_period
        self.acquisitions = 0
        self.closed = False
        self.instances.append(self)

    def acquire_sync(self):
        self.acquisitions += 1

    def close(self):
        self.closed = True


def _exact_source(tmp_path):
    path = tmp_path / "exact.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Observations"
    worksheet.append(["Variety", "habitus"])
    worksheet.append(["Domba", "terna"])
    workbook.save(path)
    workbook.close()
    return path


def _isolate_runner(monkeypatch, schema):
    monkeypatch.setattr(
        runner, "detect_anchor",
        lambda *args, **kwargs: AnchorResult("found", "Variety", 1.0, "test"),
    )
    monkeypatch.setattr(runner, "ensure_indexed", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "retrieve", lambda *args, **kwargs: [
        RetrievalHit(
            row.id, row.label, row.domain, index / 100.0,
            canonical_key=row.canonical_key,
        )
        for index, row in enumerate(schema.rows)
    ])
    monkeypatch.setattr(runner, "run_pipeline", lambda *args, **kwargs: {})


def test_runner_created_limiters_are_distinct_and_closed_on_success(monkeypatch):
    _FakeLimiter.instances = []
    monkeypatch.setattr(runner, "RateLimiter", _FakeLimiter)
    monkeypatch.setattr(
        runner, "_run_pipeline_ui_impl",
        lambda file_path, **kwargs: (kwargs["text_rate_limiter"], kwargs["vision_rate_limiter"]),
    )
    text, vision = runner.run_pipeline_ui(
        object(), rate_limit_config=RuntimeRateLimitConfig(text_rpm=12, vision_rpm=3),
    )
    assert text is not vision
    assert (text.max_rate, vision.max_rate) == (12, 3)
    assert text.closed is True
    assert vision.closed is True


def test_fractional_rpm_observability_reports_equivalent_limit(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_run_pipeline_ui_impl",
        lambda file_path, **kwargs: runner.describe_rate_limiter(kwargs["text_rate_limiter"]),
    )

    status = runner.run_pipeline_ui(
        object(), rate_limit_config=RuntimeRateLimitConfig(text_rpm=0.5),
    )

    assert status == "enabled, 1 requests / 120s"


def test_runner_created_limiters_are_closed_on_exception(monkeypatch):
    _FakeLimiter.instances = []
    monkeypatch.setattr(runner, "RateLimiter", _FakeLimiter)

    def fail(*args, **kwargs):
        raise RuntimeError("pipeline failed")

    monkeypatch.setattr(runner, "_run_pipeline_ui_impl", fail)
    with pytest.raises(RuntimeError, match="pipeline failed"):
        runner.run_pipeline_ui(
            object(), rate_limit_config=RuntimeRateLimitConfig(text_rpm=12, vision_rpm=3),
        )
    assert len(_FakeLimiter.instances) == 2
    assert all(limiter.closed for limiter in _FakeLimiter.instances)


def test_injected_limiters_remain_caller_owned(monkeypatch):
    text = _FakeLimiter()
    vision = _FakeLimiter()
    monkeypatch.setattr(
        runner, "_run_pipeline_ui_impl",
        lambda file_path, **kwargs: (kwargs["text_rate_limiter"], kwargs["vision_rate_limiter"]),
    )
    assert runner.run_pipeline_ui(
        object(), text_rate_limiter=text, vision_rate_limiter=vision,
        rate_limit_config=RuntimeRateLimitConfig(),
    ) == (text, vision)
    assert text.closed is False
    assert vision.closed is False


def test_same_text_limiter_is_reused_and_output_semantics_are_unchanged(
    flat_observations, monkeypatch,
):
    schema = CanonicalSchema.from_template()
    _isolate_runner(monkeypatch, schema)
    seen_limiters = []

    def mapping(profile, candidates, state, *, source_format, rate_limiter=None, **kwargs):
        seen_limiters.append(rate_limiter)
        target = schema.row_by_label("habitus")
        return SchemaMapping(
            source_attribute=profile.attribute_name, source_format=source_format,
            target_canonical_row=target.id, confidence=0.99,
            reasoning="fixed response", normalization_required=False,
        ), {}

    monkeypatch.setattr(runner, "safe_rerank", mapping)
    limiter = _FakeLimiter()
    enabled = runner.run_pipeline_ui(
        flat_observations, text_rate_limiter=limiter,
        rate_limit_config=RuntimeRateLimitConfig(),
    )
    enabled_calls = list(seen_limiters)
    seen_limiters.clear()
    disabled = runner.run_pipeline_ui(
        flat_observations, rate_limit_config=RuntimeRateLimitConfig(),
    )

    assert len(enabled_calls) > 1
    assert all(item is limiter for item in enabled_calls)
    assert all(item is None for item in seen_limiters)
    assert_frame_equal(enabled.canonical_df, disabled.canonical_df)
    assert enabled.workbook_bytes == disabled.workbook_bytes
    assert enabled.agent_status["text_rate_limit"] == "enabled, 10 requests / 60s"


def test_exact_name_and_no_drive_acquire_no_model_capacity(tmp_path, monkeypatch):
    schema = CanonicalSchema.from_template()
    _isolate_runner(monkeypatch, schema)
    monkeypatch.setattr(
        runner, "safe_rerank",
        lambda *args, **kwargs: pytest.fail("exact-name mapping must bypass reranker"),
    )
    text = _FakeLimiter()
    vision = _FakeLimiter()
    result = runner.run_pipeline_ui(
        _exact_source(tmp_path), text_rate_limiter=text, vision_rate_limiter=vision,
        rate_limit_config=RuntimeRateLimitConfig(),
    )
    assert text.acquisitions == 0
    assert vision.acquisitions == 0
    assert result.agent_status["vision_rate_limit"] == "enabled, 10 requests / 60s"
    assert result.agent_status["vision_classification"].startswith("dilewati")


def test_runner_passes_vision_limiter_only_to_classification(tmp_path, monkeypatch):
    schema = CanonicalSchema.from_template()
    _isolate_runner(monkeypatch, schema)
    image = ImageMetadata(
        file_id="image-1", filename="leaf.jpg", mime_type="image/jpeg",
        size=10, created_time="2026-01-01T00:00:00Z",
    )
    monkeypatch.setattr(runner, "normalize_folder_id", lambda value: value)
    monkeypatch.setattr(runner, "list_images", lambda folder: [image])
    monkeypatch.setattr(
        runner, "VisionSession",
        lambda: SimpleNamespace(knowledge_source_text="knowledge", varieties=[]),
    )
    seen = []

    def classify(*args, vision_rate_limiter=None, **kwargs):
        seen.append(vision_rate_limiter)
        return VisionResult(
            classification_status="KNOWN", matched_variety="Domba",
            identified_part="DAUN", confidence=0.9, visual_evidence="test",
        ), {}

    monkeypatch.setattr(runner, "safe_classify_image", classify)
    limiter = _FakeLimiter()
    runner.run_pipeline_ui(
        _exact_source(tmp_path), drive_folder_id="folder", vision_rate_limiter=limiter,
        rate_limit_config=RuntimeRateLimitConfig(),
    )
    assert seen == [limiter]
    assert limiter.closed is False
