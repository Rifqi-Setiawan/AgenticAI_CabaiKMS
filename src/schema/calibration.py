"""Offline calibration observations and selective-automation metrics.

This module evaluates candidate policies. It never mutates production policy.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from src.agents.schema_matching.review_queue import AcceptanceStatus, DEFAULT_CONFIDENCE_THRESHOLD
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import validate_evaluation_config_fingerprint
from src.schema.evaluation_manifest import EvaluationManifest, EvaluationSplit, assert_calibration_split
from src.schema.gold_mapping import (
    AdjudicatedGoldRecord,
    GoldAnnotationSet,
    GoldMappingAnnotation,
    GoldMappingStatus,
    validate_gold_annotations,
)


class CalibrationObservation(BaseModel):
    mapping_item_id: str
    source_file_sha256: str
    split: EvaluationSplit
    source_backend: str
    retrieval_backend: str
    retrieval_k: int
    canonical_schema_version: str
    canonical_template_hash: str
    mapping_verification_version: str
    embedding_model_name: str | None = None
    evaluation_config_fingerprint: str
    mapping_method: Literal["exact_name", "retrieve_rerank"]
    proposed_target_canonical_key: str | None = None
    current_acceptance_status: AcceptanceStatus
    model_confidence: float | None = None
    exact_name_status: str
    retrieval_target_rank: int | None = None
    retrieval_target_distance: float | None = None
    retrieval_top1_top2_margin: float | None = None
    retrieval_target_vs_top1_gap: float | None = None
    verifier_status: str
    verifier_warnings: list[str] = Field(default_factory=list)
    verifier_hard_issues: list[str] = Field(default_factory=list)
    gold_status: GoldMappingStatus
    gold_canonical_key: str | None = None
    calibration_eligible: bool
    prediction_correct: bool | None = None


class SelectiveAutomationMetrics(BaseModel):
    n_total_eligible: int
    n_auto_accept: int
    n_review: int
    n_no_write: int
    n_correct_auto_accept: int
    n_wrong_auto_accept: int
    auto_accept_precision: float | None
    automation_coverage: float
    manual_review_rate: float
    no_write_rate: float
    silent_error_rate: float | None
    selective_risk: float | None
    auto_accept_precision_wilson_95: tuple[float, float] | None


def _as_records(mapping_outputs: pd.DataFrame | Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(mapping_outputs, pd.DataFrame):
        return mapping_outputs.to_dict(orient="records")
    return [dict(item) for item in mapping_outputs]


def _codes(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, str):
        return [part for part in value.split("|") if part]
    return list(value)


def _nullable(value: Any) -> Any:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def _final_annotations(
    gold_annotations: GoldAnnotationSet | Sequence[GoldMappingAnnotation | AdjudicatedGoldRecord],
) -> list[GoldMappingAnnotation]:
    raw = gold_annotations.annotations if isinstance(gold_annotations, GoldAnnotationSet) else list(gold_annotations)
    return [item.final_annotation if isinstance(item, AdjudicatedGoldRecord) else item for item in raw]


def build_calibration_dataset(
    mapping_outputs: pd.DataFrame | Sequence[dict[str, Any]],
    gold_annotations: GoldAnnotationSet | Sequence[GoldMappingAnnotation | AdjudicatedGoldRecord],
    manifest: EvaluationManifest,
    *,
    schema: CanonicalSchema,
) -> pd.DataFrame:
    """Join predictions and gold by mapping_item_id, independent of input order."""
    mappings = _as_records(mapping_outputs)
    gold = _final_annotations(gold_annotations)
    validate_gold_annotations(gold, schema)
    fingerprints = {str(row.get("evaluation_config_fingerprint") or "") for row in mappings}
    if "" in fingerprints:
        raise ValueError("mapping observations require evaluation_config_fingerprint")
    if len(fingerprints) != 1:
        raise ValueError("calibration dataset cannot mix evaluation configuration fingerprints")
    for row in mappings:
        validate_evaluation_config_fingerprint(
            str(row["evaluation_config_fingerprint"]),
            source_backend=row["source_backend"],
            retrieval_backend=row["retrieval_backend"],
            retrieval_k=int(row["retrieval_k"]),
            canonical_schema_version=row.get("schema_version", row.get("canonical_schema_version")),
            canonical_template_hash=row.get("template_hash", row.get("canonical_template_hash")),
            mapping_verification_version=row["mapping_verification_version"],
            embedding_model_name=_nullable(row.get("embedding_model_name")),
        )
    mapping_ids = [str(row.get("mapping_item_id") or "") for row in mappings]
    if not all(mapping_ids) or len(mapping_ids) != len(set(mapping_ids)):
        raise ValueError("mapping outputs require unique, non-blank mapping_item_id values")
    gold_by_id = {item.mapping_item_id: item for item in gold}
    if len(gold_by_id) != len(gold):
        raise ValueError("gold annotations require unique mapping_item_id values")
    if set(mapping_ids) != set(gold_by_id):
        missing_gold = sorted(set(mapping_ids) - set(gold_by_id))
        missing_mapping = sorted(set(gold_by_id) - set(mapping_ids))
        raise ValueError(f"mapping/gold item sets differ; missing_gold={missing_gold}, missing_mapping={missing_mapping}")

    rows: list[dict[str, Any]] = []
    excluded = Counter()
    for mapping in mappings:
        item_id = str(mapping["mapping_item_id"])
        annotation = gold_by_id[item_id]
        digest = str(mapping.get("source_file_sha256") or annotation.source_file_sha256)
        sheet = str(mapping.get("source_sheet") or annotation.source_sheet)
        source_format = str(mapping.get("source_format") or annotation.source_format)
        if digest.lower() != annotation.source_file_sha256.lower() or sheet != annotation.source_sheet or source_format != annotation.source_format:
            raise ValueError(f"mapping/gold source identity mismatch for {item_id}")
        split = manifest.split_for(digest, sheet, source_format)
        eligible = annotation.calibration_eligible
        gold_key = annotation.gold_canonical_keys[0] if annotation.gold_status is GoldMappingStatus.ONE_TO_ONE else None
        predicted = _nullable(mapping.get("proposed_target_canonical_key", mapping.get("predicted_canonical_key")))
        correct: bool | None = None
        if eligible:
            correct = predicted == gold_key if annotation.gold_status is GoldMappingStatus.ONE_TO_ONE else predicted is None
        else:
            excluded[annotation.gold_status.value] += 1
            if annotation.annotation_source == "legacy_unverified":
                excluded["legacy_unverified"] += 1
        observation = CalibrationObservation(
            mapping_item_id=item_id,
            source_file_sha256=digest,
            split=split,
            source_backend=mapping["source_backend"],
            retrieval_backend=mapping["retrieval_backend"],
            retrieval_k=int(mapping["retrieval_k"]),
            canonical_schema_version=mapping.get("schema_version", mapping.get("canonical_schema_version")),
            canonical_template_hash=mapping.get("template_hash", mapping.get("canonical_template_hash")),
            mapping_verification_version=mapping["mapping_verification_version"],
            embedding_model_name=_nullable(mapping.get("embedding_model_name")),
            evaluation_config_fingerprint=mapping["evaluation_config_fingerprint"],
            mapping_method=mapping["mapping_method"],
            proposed_target_canonical_key=predicted,
            current_acceptance_status=mapping.get("acceptance_status", mapping.get("current_acceptance_status")),
            model_confidence=_nullable(mapping.get("confidence", mapping.get("model_confidence"))),
            exact_name_status=mapping["exact_name_status"],
            retrieval_target_rank=_nullable(mapping.get("retrieval_target_rank")),
            retrieval_target_distance=_nullable(mapping.get("retrieval_target_distance")),
            retrieval_top1_top2_margin=_nullable(mapping.get("retrieval_top1_top2_margin")),
            retrieval_target_vs_top1_gap=_nullable(mapping.get("retrieval_target_vs_top1_gap")),
            verifier_status=mapping["verifier_status"],
            verifier_warnings=_codes(mapping.get("verifier_warnings")),
            verifier_hard_issues=_codes(mapping.get("verifier_hard_issues")),
            gold_status=annotation.gold_status,
            gold_canonical_key=gold_key,
            calibration_eligible=eligible,
            prediction_correct=correct,
        )
        rows.append(observation.model_dump(mode="json"))
    frame = pd.DataFrame(rows)
    frame.attrs["excluded_counts"] = dict(sorted(excluded.items()))
    return frame


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if total == 0:
        return None
    if not (0 <= successes <= total):
        raise ValueError("successes must be between zero and total")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def calculate_selective_metrics(
    observations: pd.DataFrame | Sequence[CalibrationObservation | dict[str, Any]],
    decisions: Sequence[AcceptanceStatus | str],
) -> SelectiveAutomationMetrics:
    if isinstance(observations, pd.DataFrame):
        records = observations.to_dict(orient="records")
    else:
        records = [item.model_dump(mode="json") if isinstance(item, CalibrationObservation) else dict(item) for item in observations]
    if len(records) != len(decisions):
        raise ValueError("decisions must align one-for-one with observations")
    eligible = [(row, AcceptanceStatus(decision)) for row, decision in zip(records, decisions) if row.get("calibration_eligible", True)]
    counts = Counter(decision for _, decision in eligible)
    accepted = [row for row, decision in eligible if decision is AcceptanceStatus.AUTO_ACCEPT]
    correct = sum(row.get("prediction_correct") is True for row in accepted)
    wrong = sum(row.get("prediction_correct") is False for row in accepted)
    n_total, n_accepted = len(eligible), len(accepted)
    precision = correct / n_accepted if n_accepted else None
    return SelectiveAutomationMetrics(
        n_total_eligible=n_total,
        n_auto_accept=n_accepted,
        n_review=counts[AcceptanceStatus.REVIEW],
        n_no_write=counts[AcceptanceStatus.NO_WRITE],
        n_correct_auto_accept=correct,
        n_wrong_auto_accept=wrong,
        auto_accept_precision=precision,
        automation_coverage=n_accepted / n_total if n_total else 0.0,
        manual_review_rate=counts[AcceptanceStatus.REVIEW] / n_total if n_total else 0.0,
        no_write_rate=counts[AcceptanceStatus.NO_WRITE] / n_total if n_total else 0.0,
        silent_error_rate=wrong / n_accepted if n_accepted else None,
        selective_risk=(1.0 - precision) if precision is not None else None,
        auto_accept_precision_wilson_95=wilson_interval(correct, n_accepted),
    )


def baseline_policy_decisions(
    observations: pd.DataFrame | Sequence[CalibrationObservation | dict[str, Any]],
) -> list[AcceptanceStatus]:
    """Reproduce Phase 7C1 policy without changing its implementation."""
    if isinstance(observations, pd.DataFrame):
        records = observations.to_dict(orient="records")
    else:
        records = [item.model_dump(mode="json") if isinstance(item, CalibrationObservation) else dict(item) for item in observations]
    decisions = []
    for row in records:
        if _codes(row.get("verifier_hard_issues")) or row.get("verifier_status") == "REJECT":
            decisions.append(AcceptanceStatus.NO_WRITE)
        elif (
            _nullable(row.get("proposed_target_canonical_key")) is None
            or _nullable(row.get("model_confidence")) is None
            or float(row["model_confidence"]) < DEFAULT_CONFIDENCE_THRESHOLD
            or "RERANK_RELIABILITY_PATCH" in _codes(row.get("verifier_warnings"))
        ):
            decisions.append(AcceptanceStatus.REVIEW)
        else:
            decisions.append(AcceptanceStatus.AUTO_ACCEPT)
    return decisions


def evaluate_current_policy(
    observations: pd.DataFrame | Sequence[CalibrationObservation | dict[str, Any]],
) -> SelectiveAutomationMetrics:
    """Evaluation-only: allowed on either split and never selects a policy."""
    return calculate_selective_metrics(observations, baseline_policy_decisions(observations))


def stratified_policy_metrics(
    observations: pd.DataFrame,
    decisions: Sequence[AcceptanceStatus | str] | None = None,
) -> pd.DataFrame:
    decisions = list(decisions) if decisions is not None else baseline_policy_decisions(observations)
    if len(decisions) != len(observations):
        raise ValueError("decisions must align one-for-one with observations")
    working = observations.copy()
    working["_decision"] = [AcceptanceStatus(value).value for value in decisions]
    rows = []
    for label, group in [("overall", working), *list(working.groupby("mapping_method", sort=True))]:
        metrics = calculate_selective_metrics(group, group["_decision"].tolist())
        rows.append({"stratum": label, **metrics.model_dump()})
    return pd.DataFrame(rows)


def summarize_retrieval_signals(observations: pd.DataFrame) -> pd.DataFrame:
    """Validation-only descriptive statistics; no threshold is selected."""
    if set(observations["split"].dropna().unique()) - {EvaluationSplit.VALIDATION.value}:
        raise ValueError("raw signal analysis is validation-only")
    subset = observations.loc[
        observations["calibration_eligible"].astype(bool)
        & (observations["mapping_method"] == "retrieve_rerank")
    ]
    signals = [
        "model_confidence", "retrieval_target_rank", "retrieval_target_distance",
        "retrieval_top1_top2_margin", "retrieval_target_vs_top1_gap",
    ]
    rows = []
    for correctness, group in subset.groupby("prediction_correct", dropna=False, sort=True):
        for signal in signals:
            values = pd.to_numeric(group[signal], errors="coerce").dropna()
            rows.append({
                "prediction_correct": correctness, "signal": signal, "count": int(values.count()),
                "mean": values.mean() if len(values) else None,
                "median": values.median() if len(values) else None,
                "min": values.min() if len(values) else None,
                "max": values.max() if len(values) else None,
                "q25": values.quantile(0.25) if len(values) else None,
                "q75": values.quantile(0.75) if len(values) else None,
            })
    return pd.DataFrame(rows)


def analyze_confidence_thresholds(observations: pd.DataFrame) -> pd.DataFrame:
    """Validation-only, data-derived sweep artifact; does not pick a winner."""
    if set(observations["split"].dropna().unique()) - {EvaluationSplit.VALIDATION.value}:
        raise ValueError("threshold calibration refuses the test split")
    assert_calibration_split(EvaluationSplit.VALIDATION)
    eligible_confidence = pd.to_numeric(
        observations.loc[
            observations["calibration_eligible"].astype(bool)
            & (observations["mapping_method"] == "retrieve_rerank"),
            "model_confidence",
        ],
        errors="coerce",
    ).dropna()
    rows = []
    for threshold in sorted(set(float(value) for value in eligible_confidence)):
        records = observations.to_dict(orient="records")
        decisions = baseline_policy_decisions(records)
        for index, row in enumerate(records):
            if row.get("mapping_method") != "retrieve_rerank":
                continue
            if _codes(row.get("verifier_hard_issues")) or row.get("verifier_status") == "REJECT":
                decisions[index] = AcceptanceStatus.NO_WRITE
            elif _nullable(row.get("proposed_target_canonical_key")) is None or _nullable(row.get("model_confidence")) is None or float(row["model_confidence"]) < threshold:
                decisions[index] = AcceptanceStatus.REVIEW
            else:
                decisions[index] = AcceptanceStatus.AUTO_ACCEPT
        metrics = calculate_selective_metrics(observations, decisions)
        rows.append({
            "policy_descriptor": f"retrieve_rerank confidence>={threshold!r}; exact_name baseline",
            "confidence_threshold": threshold,
            "coverage": metrics.automation_coverage, "selective_risk": metrics.selective_risk,
            "precision": metrics.auto_accept_precision,
            "wilson_lower_bound": metrics.auto_accept_precision_wilson_95[0] if metrics.auto_accept_precision_wilson_95 else None,
            "review_rate": metrics.manual_review_rate, "no_write_rate": metrics.no_write_rate,
            "silent_errors": metrics.n_wrong_auto_accept,
        })
    return pd.DataFrame(rows)
