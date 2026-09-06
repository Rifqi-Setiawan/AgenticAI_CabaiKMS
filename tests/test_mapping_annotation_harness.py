from types import SimpleNamespace

import pandas as pd
import pytest

from eval.create_mapping_annotations import HUMAN_COLUMNS, create_annotation_table, run_annotation_harness


def _result():
    return SimpleNamespace(
        mapping_verifications=[], source_backend="legacy", retrieval_backend="exact",
        retrieval_k=8, schema_version="schema-v1", template_hash="template-hash",
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="embedding-model", evaluation_config_fingerprint="config-id",
        mapping_df=pd.DataFrame([{
        "mapping_item_id": "stable-id", "source_file_name": "source.xlsx",
        "mapping_identity_kind": "source_attribute_display",
        "mapping_identity_value": "Height", "mapping_identity_issue": None,
        "source_file_sha256": "a" * 64, "source_sheet": "Sheet1",
        "source_format": "row-oriented", "source_attribute_id": "Sheet1!COL:B",
        "source_attribute_display": "Height", "source_attribute": "Height",
        "source_context": None, "proposed_target_canonical_key": "tinggi_tanaman",
        "predicted_row": "r_2", "mapping_method": "retrieve_rerank", "confidence": 0.95,
        "exact_name_status": "NO_MATCH", "verifier_status": "PASS",
        "verifier_warnings": [], "verifier_hard_issues": [], "retrieval_target_rank": 1,
        "retrieval_target_distance": 0.1, "retrieval_top1_top2_margin": 0.2,
        "retrieval_target_vs_top1_gap": 0.0, "acceptance_status": "AUTO_ACCEPT",
    }]))


def test_annotation_table_never_prefills_gold_from_prediction():
    frame = create_annotation_table(_result())
    assert frame.loc[0, "proposed_target_canonical_key"] == "tinggi_tanaman"
    assert all(frame.loc[0, column] == "" for column in HUMAN_COLUMNS)


def test_harness_requires_force_to_overwrite(tmp_path):
    output = tmp_path / "annotations.csv"
    output.write_text("historical", encoding="utf-8")
    with pytest.raises(FileExistsError, match="--force"):
        run_annotation_harness(tmp_path / "source.xlsx", output, pipeline_call=lambda *a, **k: _result())


def test_harness_exports_with_explicit_output(tmp_path):
    output = tmp_path / "annotations.csv"
    frame = run_annotation_harness(
        tmp_path / "source.xlsx", output, pipeline_call=lambda *a, **k: _result()
    )
    assert output.exists()
    assert all(frame.loc[0, column] == "" for column in HUMAN_COLUMNS)
