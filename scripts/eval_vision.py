"""Vision Evaluation Harness & Threshold Sweep for Plant Variety Classification.

Evaluates multimodal model predictions against a ground-truth CSV manifest.
Calculates Top-1 accuracy, Macro-F1, OTHER recall, candidate precision,
and review routing rate across an operating threshold sweep (0.50..0.95).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


MANDATORY_COLUMNS = {"filename", "true_label", "kind", "split"}


def load_vision_manifest(path: Path | str) -> list[dict[str, str]]:
    """Load and validate manifest CSV."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Manifest file not found: {p}")

    with p.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Empty manifest CSV.")
        missing = MANDATORY_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing required columns in manifest: {sorted(missing)}")
        return [dict(row) for row in reader]


def calculate_vision_metrics(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> dict[str, float]:
    """Calculate evaluation metrics for vision classification."""
    pred_map = {p["filename"]: p for p in predictions}

    correct_top1 = 0
    total_known = 0

    true_other_count = 0
    true_other_caught_candidate = 0

    total_candidates_predicted = 0
    candidate_true_positives = 0

    total_reviewed = 0
    total_samples = len(ground_truth)

    classes = set()
    tp_per_class: dict[str, int] = {}
    fp_per_class: dict[str, int] = {}
    fn_per_class: dict[str, int] = {}

    for gt in ground_truth:
        fname = gt["filename"]
        t_label = gt.get("true_label", "")
        kind = gt.get("kind", "KNOWN").upper()
        if kind == "KNOWN":
            classes.add(t_label)

        pred = pred_map.get(fname, {})
        pred_label = pred.get("predicted_variety")
        action = pred.get("action", "")

        # Review rate accounting
        if action in ("REVIEW_MISMATCH", "REVIEW_UNCERTAIN", "CANDIDATE"):
            total_reviewed += 1

        # Known evaluation
        if kind == "KNOWN":
            total_known += 1
            if pred_label == t_label:
                correct_top1 += 1
                tp_per_class[t_label] = tp_per_class.get(t_label, 0) + 1
            else:
                fn_per_class[t_label] = fn_per_class.get(t_label, 0) + 1
                if pred_label:
                    fp_per_class[pred_label] = fp_per_class.get(pred_label, 0) + 1

        # OTHER / Candidate evaluation
        if kind == "OTHER":
            true_other_count += 1
            if action == "CANDIDATE":
                true_other_caught_candidate += 1

        if action == "CANDIDATE":
            total_candidates_predicted += 1
            if kind == "OTHER":
                candidate_true_positives += 1

    top1 = (correct_top1 / total_known) if total_known > 0 else 0.0
    recall_other = (true_other_caught_candidate / true_other_count) if true_other_count > 0 else 1.0
    cand_prec = (candidate_true_positives / total_candidates_predicted) if total_candidates_predicted > 0 else 1.0
    review_rate = (total_reviewed / total_samples) if total_samples > 0 else 0.0

    # Macro F1
    f1_list = []
    for cls_name in classes:
        tp = tp_per_class.get(cls_name, 0)
        fp = fp_per_class.get(cls_name, 0)
        fn = fn_per_class.get(cls_name, 0)
        prec = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        f1_list.append(f1)

    macro_f1 = (sum(f1_list) / len(f1_list)) if f1_list else 1.0

    return {
        "top1_accuracy": round(top1, 4),
        "macro_f1": round(macro_f1, 4),
        "recall_other": round(recall_other, 4),
        "candidate_precision": round(cand_prec, 4),
        "review_rate": round(review_rate, 4),
        "total_samples": total_samples,
    }


def run_threshold_sweep(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    min_t: float = 0.50,
    max_t: float = 0.95,
    step: float = 0.05,
) -> list[dict[str, Any]]:
    """Evaluate metric trajectory across a sweep of confidence thresholds."""
    results: list[dict[str, Any]] = []
    steps = int(round((max_t - min_t) / step)) + 1

    for s in range(steps):
        t = round(min_t + s * step, 2)
        # Classify each prediction under threshold t
        simulated_preds = []
        for p in predictions:
            conf = float(p.get("confidence", 0.0))
            p_copy = dict(p)
            if conf < t:
                p_copy["action"] = "REVIEW_UNCERTAIN"
            else:
                p_copy["action"] = p.get("action", "AUTO_LINK")
            simulated_preds.append(p_copy)

        m = calculate_vision_metrics(ground_truth, simulated_preds)
        results.append({
            "threshold": t,
            "top1_accuracy": m["top1_accuracy"],
            "macro_f1": m["macro_f1"],
            "review_rate": m["review_rate"],
        })
    return results


def evaluate_offline_mock(manifest_path: Path | str, output_dir: Path | str) -> dict[str, Any]:
    """Run offline evaluation on a manifest using deterministic mock predictions."""
    manifest = load_vision_manifest(manifest_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Generate deterministic mock predictions
    preds = []
    for row in manifest:
        kind = row.get("kind", "KNOWN").upper()
        if kind == "KNOWN":
            preds.append({
                "filename": row["filename"],
                "predicted_variety": row["true_label"],
                "confidence": 0.90,
                "action": "AUTO_LINK",
            })
        elif kind == "OTHER":
            preds.append({
                "filename": row["filename"],
                "predicted_variety": None,
                "confidence": 0.85,
                "action": "CANDIDATE",
            })
        else:
            preds.append({
                "filename": row["filename"],
                "predicted_variety": None,
                "confidence": 0.50,
                "action": "REVIEW_UNCERTAIN",
            })

    metrics = calculate_vision_metrics(manifest, preds)
    sweep = run_threshold_sweep(manifest, preds)

    # Write sweep CSV
    sweep_csv = out_path / "sweep_results.csv"
    with sweep_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["threshold", "top1_accuracy", "macro_f1", "review_rate"])
        writer.writeheader()
        writer.writerows(sweep)

    # Write markdown summary
    summary_md = out_path / "eval_summary.md"
    md_content = [
        "# Laporan Evaluasi Model Visi (Offline Mock)",
        "",
        f"- **Total Sampel:** {metrics['total_samples']}",
        f"- **Top-1 Akurasi:** {metrics['top1_accuracy'] * 100:.2f}%",
        f"- **Macro-F1:** {metrics['macro_f1']:.4f}",
        f"- **Recall OTHER:** {metrics['recall_other'] * 100:.2f}%",
        f"- **Presisi Kandidat:** {metrics['candidate_precision'] * 100:.2f}%",
        f"- **Tingkat Review:** {metrics['review_rate'] * 100:.2f}%",
        "",
        "## Hasil Threshold Sweep",
        "",
        "| Threshold | Top-1 Accuracy | Macro-F1 | Review Rate |",
        "|---|---|---|---|",
    ]
    for row in sweep:
        md_content.append(f"| {row['threshold']:.2f} | {row['top1_accuracy']:.4f} | {row['macro_f1']:.4f} | {row['review_rate']:.4f} |")

    summary_md.write_text("\n".join(md_content) + "\n", encoding="utf-8")

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate vision classification manifest")
    parser.add_argument("--manifest", type=str, required=True, help="Path to manifest CSV")
    parser.add_argument("--output-dir", type=str, default="data/eval_output", help="Output directory")
    parser.add_argument("--offline-mock", action="store_true", help="Run in offline mock mode")
    args = parser.parse_args()

    if args.offline_mock:
        metrics = evaluate_offline_mock(args.manifest, args.output_dir)
        print("Offline evaluation completed:", metrics)
    else:
        print("Real image evaluation requires model API connection. Use --offline-mock for testing.")


if __name__ == "__main__":
    main()
