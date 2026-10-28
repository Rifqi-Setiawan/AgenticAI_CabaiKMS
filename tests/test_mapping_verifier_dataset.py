import pandas as pd
import pytest

from eval.mapping_verifier_dataset import (
    DATASET_COLUMNS,
    build_mapping_verifier_dataset,
    export_mapping_verifier_dataset,
)
from src.schema.mapping_verification import (
    MappingVerificationResult,
    MappingVerificationStatus,
    RetrievalEvidence,
)


def _verification():
    return MappingVerificationResult(
        status=MappingVerificationStatus.PASS,
        mapping_method="retrieve_rerank",
        source_attribute="Height",
        source_context="Morphology",
        proposed_target_row_id="r_2",
        proposed_target_canonical_key="tinggi_tanaman",
        exact_name_status="NO_MATCH",
        warning_codes=["TARGET_NOT_RETRIEVAL_TOP1"],
        retrieval_evidence=RetrievalEvidence(
            candidate_count=3,
            target_in_candidates=True,
            target_rank=2,
            target_distance=0.15,
            top1_row_id="r_1",
            top1_canonical_key="habitus",
            top1_distance=0.10,
            top2_row_id="r_2",
            top2_canonical_key="tinggi_tanaman",
            top2_distance=0.15,
            top1_top2_margin=0.05,
            target_vs_top1_distance_gap=0.05,
        ),
        model_confidence=0.9,
        recommendation_summary="no deterministic verifier violation observed",
    )


def test_dataset_exports_raw_signals_without_manufacturing_gold(tmp_path):
    verification = _verification()
    frame = build_mapping_verifier_dataset([verification])
    assert frame.columns.tolist() == DATASET_COLUMNS
    assert pd.isna(frame.loc[0, "gold_target_canonical_key"])
    assert frame.loc[0, "retrieval_target_distance"] == 0.15
    assert frame.loc[0, "retrieval_top1_top2_margin"] == 0.05
    assert frame.loc[0, "verifier_warnings"] == "TARGET_NOT_RETRIEVAL_TOP1"

    output = tmp_path / "verification.csv"
    exported = export_mapping_verifier_dataset(
        [verification], output, gold_target_canonical_keys=["tinggi_tanaman"]
    )
    loaded = pd.read_csv(output)
    assert exported.loc[0, "gold_target_canonical_key"] == "tinggi_tanaman"
    assert loaded.loc[0, "gold_target_canonical_key"] == "tinggi_tanaman"


def test_gold_labels_must_align_explicitly():
    with pytest.raises(ValueError, match="one-for-one"):
        build_mapping_verifier_dataset([_verification()], gold_target_canonical_keys=[])
