"""Deterministic Phase 7C1 verifier-signal export for later calibration."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from src.schema.mapping_verification import MappingVerificationResult

DATASET_COLUMNS = [
    "source_attribute",
    "source_context",
    "mapping_method",
    "proposed_target_canonical_key",
    "model_confidence",
    "exact_name_status",
    "retrieval_target_rank",
    "retrieval_target_distance",
    "retrieval_top1_top2_margin",
    "retrieval_target_vs_top1_gap",
    "verifier_status",
    "verifier_hard_issues",
    "verifier_warnings",
    "gold_target_canonical_key",
]


def build_mapping_verifier_dataset(
    verifications: Sequence[MappingVerificationResult],
    *,
    gold_target_canonical_keys: Sequence[str | None] | None = None,
) -> pd.DataFrame:
    """Build one row per verification; gold is included only when supplied."""
    if gold_target_canonical_keys is not None and len(gold_target_canonical_keys) != len(
        verifications
    ):
        raise ValueError("gold labels must align one-for-one with verifications")
    gold = gold_target_canonical_keys or [None] * len(verifications)
    rows = []
    for verification, gold_key in zip(verifications, gold):
        evidence = verification.retrieval_evidence
        rows.append(
            {
                "source_attribute": verification.source_attribute,
                "source_context": verification.source_context,
                "mapping_method": verification.mapping_method,
                "proposed_target_canonical_key": verification.proposed_target_canonical_key,
                "model_confidence": verification.model_confidence,
                "exact_name_status": verification.exact_name_status,
                "retrieval_target_rank": evidence.target_rank if evidence else None,
                "retrieval_target_distance": evidence.target_distance if evidence else None,
                "retrieval_top1_top2_margin": evidence.top1_top2_margin if evidence else None,
                "retrieval_target_vs_top1_gap": (
                    evidence.target_vs_top1_distance_gap if evidence else None
                ),
                "verifier_status": verification.status.value,
                "verifier_hard_issues": "|".join(verification.hard_issue_codes),
                "verifier_warnings": "|".join(verification.warning_codes),
                "gold_target_canonical_key": gold_key,
            }
        )
    return pd.DataFrame(rows, columns=DATASET_COLUMNS)


def export_mapping_verifier_dataset(
    verifications: Sequence[MappingVerificationResult],
    output_path: Path | str,
    *,
    gold_target_canonical_keys: Sequence[str | None] | None = None,
) -> pd.DataFrame:
    """Export CSV/XLSX without manufacturing labels from model predictions."""
    frame = build_mapping_verifier_dataset(
        verifications, gold_target_canonical_keys=gold_target_canonical_keys
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.casefold() == ".xlsx":
        frame.to_excel(path, index=False)
    elif path.suffix.casefold() == ".csv":
        frame.to_csv(path, index=False, lineterminator="\n")
    else:
        raise ValueError("mapping verifier dataset output must be .csv or .xlsx")
    return frame
