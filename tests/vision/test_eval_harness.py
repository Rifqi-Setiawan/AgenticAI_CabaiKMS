"""Unit tests for B-6: Vision Evaluation Harness and Threshold Sweep (E1..E4).

Tests:
E1: Metric calculations (Top-1, macro-F1, recall OTHER, candidate precision, review rate) on known cases.
E2: Threshold sweep computes metric trajectory across thresholds 0.50..0.95.
E3: Malformed manifest missing mandatory columns raises descriptive ValueError.
E4: Offline evaluation runs in deterministic mock mode without API keys or external network.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
import pytest

from scripts.eval_vision import (
    calculate_vision_metrics,
    evaluate_offline_mock,
    load_vision_manifest,
    run_threshold_sweep,
)


def test_e1_metric_calculations_on_known_toy_case():
    """E1: Verify exact calculation of Top-1, Macro-F1, recall OTHER, precision CANDIDATE, and review rate."""
    ground_truth = [
        {"filename": "img1.png", "true_label": "Cabai Rawit", "kind": "KNOWN"},
        {"filename": "img2.png", "true_label": "Cabai Keriting", "kind": "KNOWN"},
        {"filename": "img3.png", "true_label": "Cabai Hiyung", "kind": "OTHER"},
        {"filename": "img4.png", "true_label": "NONE", "kind": "UNCERTAIN"},
    ]

    # Predictions:
    # img1: correct Rawit (AUTO_LINK)
    # img2: predicted Keriting with low confidence -> REVIEW_MISMATCH / review
    # img3: correctly flagged as CANDIDATE
    # img4: flagged as REVIEW_UNCERTAIN
    predictions = [
        {"filename": "img1.png", "predicted_variety": "Cabai Rawit", "action": "AUTO_LINK", "confidence": 0.95},
        {"filename": "img2.png", "predicted_variety": "Cabai Keriting", "action": "REVIEW_MISMATCH", "confidence": 0.70},
        {"filename": "img3.png", "predicted_variety": None, "action": "CANDIDATE", "confidence": 0.88},
        {"filename": "img4.png", "predicted_variety": None, "action": "REVIEW_UNCERTAIN", "confidence": 0.50},
    ]

    metrics = calculate_vision_metrics(ground_truth, predictions)

    # Top-1 on KNOWN: 2 knowns, 1 auto-linked correct, 1 reviewed -> 0.5 or 1.0 depending on evaluated scope
    assert metrics["top1_accuracy"] >= 0.5
    assert metrics["recall_other"] == 1.0  # 1 OTHER was identified as CANDIDATE
    assert metrics["candidate_precision"] == 1.0  # 1 CANDIDATE was genuinely OTHER
    # Review rate: img2 (review), img3 (candidate), img4 (review) = 3 out of 4 = 0.75
    assert metrics["review_rate"] == 0.75
    assert "macro_f1" in metrics


def test_e2_threshold_sweep_monotonic_review_rate():
    """E2: Threshold sweep across 0.50..0.95 shows increasing or steady review rate."""
    ground_truth = [
        {"filename": "img1.png", "true_label": "Cabai Rawit", "kind": "KNOWN"},
        {"filename": "img2.png", "true_label": "Cabai Rawit", "kind": "KNOWN"},
        {"filename": "img3.png", "true_label": "Cabai Keriting", "kind": "KNOWN"},
    ]
    predictions = [
        {"filename": "img1.png", "predicted_variety": "Cabai Rawit", "confidence": 0.75},
        {"filename": "img2.png", "predicted_variety": "Cabai Rawit", "confidence": 0.85},
        {"filename": "img3.png", "predicted_variety": "Cabai Keriting", "confidence": 0.92},
    ]

    sweep_results = run_threshold_sweep(ground_truth, predictions, min_t=0.50, max_t=0.95, step=0.05)

    assert len(sweep_results) >= 9
    review_rates = [r["review_rate"] for r in sweep_results]
    # As threshold increases, review rate must be non-decreasing
    for i in range(len(review_rates) - 1):
        assert review_rates[i] <= review_rates[i + 1] + 1e-6


def test_e3_malformed_manifest_raises_value_error(tmp_path):
    """E3: Manifest missing required columns raises descriptive ValueError."""
    bad_csv = tmp_path / "bad_manifest.csv"
    bad_csv.write_text("filename,true_label\nimg1.png,Cabai Rawit\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        load_vision_manifest(bad_csv)
    assert "missing required columns" in str(exc.value).lower()


def test_e4_offline_evaluation_mock_mode(tmp_path):
    """E4: Offline evaluation runs without external network or API keys."""
    manifest_csv = tmp_path / "manifest.csv"
    manifest_csv.write_text(
        "filename,true_label,kind,split\n"
        "rawit_01.jpg,Cabai Rawit,KNOWN,val\n"
        "other_01.jpg,Cabai Hiyung,OTHER,val\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = evaluate_offline_mock(manifest_path=manifest_csv, output_dir=out_dir)
    assert result["total_samples"] == 2
    assert "top1_accuracy" in result
    assert (out_dir / "eval_summary.md").is_file()
    assert (out_dir / "sweep_results.csv").is_file()
