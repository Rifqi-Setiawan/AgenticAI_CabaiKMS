from types import SimpleNamespace

import pandas as pd
import pytest

from eval.create_mapping_annotations import create_annotation_table
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import EvaluationRunConfig
from src.schema.gold_mapping import (
    build_mapping_item_id,
    compare_annotators,
    load_gold_annotations,
)


def _annotation_frame(schema):
    identity = dict(
        source_file_sha256="a" * 64, source_sheet="Sheet1",
        source_format="row-oriented", identity_kind="source_attribute_display",
        identity_value="Height",
    )
    config = EvaluationRunConfig(
        source_backend="legacy", retrieval_backend="exact", retrieval_k=8,
        canonical_schema_version=schema.schema_version,
        canonical_template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="embedding-model",
    )
    result = SimpleNamespace(
        mapping_verifications=[], source_backend="legacy", retrieval_backend="exact",
        retrieval_k=8, schema_version=schema.schema_version, template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="embedding-model", evaluation_config_fingerprint=config.fingerprint,
        mapping_df=pd.DataFrame([{
            "mapping_item_id": build_mapping_item_id(**identity),
            "mapping_identity_kind": identity["identity_kind"],
            "mapping_identity_value": identity["identity_value"],
            "mapping_identity_issue": None, "source_file_name": "source.xlsx",
            "source_file_sha256": identity["source_file_sha256"],
            "source_sheet": identity["source_sheet"], "source_format": identity["source_format"],
            "source_attribute_display": "Height", "source_attribute": "Height",
            "source_context": None, "proposed_target_canonical_key": schema.rows[0].canonical_key,
            "predicted_row": schema.rows[0].id, "mapping_method": "retrieve_rerank",
            "confidence": 0.9, "exact_name_status": "NO_MATCH", "verifier_status": "PASS",
            "verifier_warnings": [], "verifier_hard_issues": [], "retrieval_target_rank": 1,
            "retrieval_target_distance": 0.1, "retrieval_top1_top2_margin": 0.2,
            "retrieval_target_vs_top1_gap": 0.0, "acceptance_status": "AUTO_ACCEPT",
        }]),
    )
    frame = create_annotation_table(result)
    frame.loc[0, "gold_status"] = "ONE_TO_ONE"
    frame.loc[0, "gold_canonical_keys"] = f" {schema.rows[0].canonical_key} "
    frame.loc[0, "annotator_id"] = "annotator_A"
    frame.loc[0, "annotation_round"] = "1"
    return frame


@pytest.mark.parametrize("suffix", [".xlsx", ".csv"])
def test_annotation_round_trip_xlsx_and_csv(tmp_path, suffix):
    schema = CanonicalSchema.from_template()
    frame = _annotation_frame(schema)
    path = tmp_path / f"annotations{suffix}"
    frame.to_excel(path, index=False) if suffix == ".xlsx" else frame.to_csv(path, index=False)
    loaded = load_gold_annotations(path, schema=schema)
    item = loaded.annotations[0]
    assert item.gold_canonical_keys == [schema.rows[0].canonical_key]
    assert item.mapping_identity_kind.value == "source_attribute_display"
    assert item.mapping_identity_value == "Height"
    assert item.annotator_id == "annotator_A"


@pytest.mark.parametrize("column,value", [("source_sheet", "Tampered"), ("mapping_identity_value", "Width")])
def test_annotation_loader_rejects_identity_tampering(tmp_path, column, value):
    schema = CanonicalSchema.from_template()
    frame = _annotation_frame(schema)
    frame.loc[0, column] = value
    path = tmp_path / "tampered.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="identity verification failed"):
        load_gold_annotations(path, schema=schema)


def test_loader_rejects_unknown_key_and_blank_completion(tmp_path):
    schema = CanonicalSchema.from_template()
    frame = _annotation_frame(schema)
    path = tmp_path / "bad.csv"
    frame.loc[0, "gold_canonical_keys"] = "totally_fake_canonical_key"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="unknown canonical key"):
        load_gold_annotations(path, schema=schema)
    frame.loc[0, "gold_canonical_keys"] = ""
    frame.loc[0, "gold_status"] = ""
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="incomplete"):
        load_gold_annotations(path, schema=schema)


def test_independence_and_degenerate_kappa(tmp_path):
    schema = CanonicalSchema.from_template()
    frame = _annotation_frame(schema)
    frame.loc[0, "gold_status"] = "NO_MATCH"
    frame.loc[0, "gold_canonical_keys"] = ""
    path = tmp_path / "a.csv"
    frame.to_csv(path, index=False)
    annotations_a = load_gold_annotations(path, schema=schema)
    with pytest.raises(ValueError, match="different IDs"):
        compare_annotators(annotations_a, annotations_a)
    annotations_b = annotations_a.model_copy(deep=True)
    annotations_b.annotations[0].annotator_id = "annotator_B"
    _, metrics = compare_annotators(annotations_a, annotations_b)
    assert metrics.raw_agreement == 1.0
    assert metrics.cohens_kappa is None
    assert metrics.kappa_defined is False
    assert metrics.kappa_undefined_reason == "SINGLE_CLASS_DEGENERATE"
