import pytest
import pandas as pd

from src.schema.calibration import (
    analyze_confidence_thresholds,
    baseline_policy_decisions,
    calculate_selective_metrics,
    wilson_interval,
)


def _observations(correctness, *, split="validation"):
    return pd.DataFrame({
        "mapping_item_id": [str(i) for i in range(len(correctness))],
        "calibration_eligible": [True] * len(correctness),
        "prediction_correct": correctness,
        "split": [split] * len(correctness),
        "mapping_method": ["retrieve_rerank"] * len(correctness),
        "proposed_target_canonical_key": ["key"] * len(correctness),
        "model_confidence": [0.9] * len(correctness),
        "verifier_status": ["PASS"] * len(correctness),
        "verifier_hard_issues": [[] for _ in correctness],
        "verifier_warnings": [[] for _ in correctness],
    })


def test_selective_metrics_controlled_example():
    observations = _observations([True, True, True, True, True, False, True, False, True, False])
    metrics = calculate_selective_metrics(observations, ["AUTO_ACCEPT"] * 6 + ["REVIEW"] * 3 + ["NO_WRITE"])
    assert metrics.auto_accept_precision == pytest.approx(5 / 6)
    assert metrics.automation_coverage == 0.6
    assert metrics.manual_review_rate == 0.3
    assert metrics.no_write_rate == 0.1
    assert metrics.silent_error_rate == pytest.approx(1 / 6)
    assert metrics.selective_risk == pytest.approx(1 / 6)


def test_zero_accept_has_no_precision_risk_or_interval():
    metrics = calculate_selective_metrics(_observations([True, False]), ["REVIEW", "NO_WRITE"])
    assert metrics.auto_accept_precision is None
    assert metrics.selective_risk is None
    assert metrics.auto_accept_precision_wilson_95 is None


@pytest.mark.parametrize("successes,total", [(5, 5), (95, 100), (0, 5)])
def test_wilson_known_inputs_stay_bounded(successes, total):
    lower, upper = wilson_interval(successes, total)
    assert 0 <= lower <= upper <= 1
    assert lower <= successes / total <= upper


def test_baseline_policy_semantics():
    rows = _observations([True] * 5)
    rows.loc[0, "mapping_method"] = "exact_name"
    rows.loc[1, "model_confidence"] = 0.59
    rows.loc[2, "verifier_status"] = "REJECT"
    rows.at[2, "verifier_hard_issues"] = ["BROKEN"]
    rows.loc[3, "proposed_target_canonical_key"] = None
    assert [item.value for item in baseline_policy_decisions(rows)] == [
        "AUTO_ACCEPT", "REVIEW", "NO_WRITE", "REVIEW", "AUTO_ACCEPT",
    ]


def test_threshold_sweep_refuses_test():
    with pytest.raises(ValueError, match="refuses the test"):
        analyze_confidence_thresholds(_observations([True], split="test"))


def test_threshold_sweep_does_not_apply_rerank_threshold_to_exact_name():
    rows = _observations([True, True])
    rows.loc[0, "mapping_method"] = "exact_name"
    rows.loc[0, "model_confidence"] = 0.7
    rows.loc[1, "model_confidence"] = 0.9
    sweep = analyze_confidence_thresholds(rows)
    assert sweep.confidence_threshold.tolist() == [0.9]
    assert sweep.loc[0, "coverage"] == 1.0
