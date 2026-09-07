import json
from types import SimpleNamespace

import pandas as pd
import pytest

from eval.prepare_annotation_campaign import (
    BLINDED_COLUMNS,
    HUMAN_COLUMNS,
    prepare_campaign,
)
from eval.finalize_mapping_annotations import FINAL_COLUMNS, _annotation_row, finalize_campaign
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import EvaluationRunConfig
from src.schema.gold_mapping import (
    GoldMappingAnnotation,
    build_mapping_item_id,
    create_adjudication_template,
    load_gold_annotations,
)


def _pipeline_result(path, *, source_format, sheet_name, **kwargs):
    schema = CanonicalSchema.from_template()
    digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    identity = {
        "source_file_sha256": digest,
        "source_sheet": sheet_name,
        "source_format": source_format,
        "identity_kind": "source_attribute_display",
        "identity_value": "Height",
    }
    config = EvaluationRunConfig(
        source_backend="legacy", retrieval_backend="exact", retrieval_k=8,
        canonical_schema_version=schema.schema_version,
        canonical_template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2",
    )
    return SimpleNamespace(
        mapping_verifications=[], source_backend="legacy", retrieval_backend="exact",
        retrieval_k=8, schema_version=schema.schema_version,
        template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2",
        evaluation_config_fingerprint=config.fingerprint,
        mapping_df=pd.DataFrame([{
            "mapping_item_id": build_mapping_item_id(**identity),
            "mapping_identity_kind": identity["identity_kind"],
            "mapping_identity_value": identity["identity_value"],
            "mapping_identity_issue": None,
            "source_file_name": path.name,
            "source_file_sha256": digest,
            "source_sheet": sheet_name,
            "source_format": source_format,
            "source_attribute_id": None,
            "source_attribute_display": "Height",
            "source_attribute": "Height",
            "source_context": None,
            "proposed_target_canonical_key": schema.rows[0].canonical_key,
            "predicted_row": schema.rows[0].id,
            "mapping_method": "retrieve_rerank",
            "confidence": 0.9,
            "exact_name_status": "NO_MATCH",
            "verifier_status": "PASS",
            "verifier_warnings": [],
            "verifier_hard_issues": [],
            "retrieval_target_rank": 1,
            "retrieval_target_distance": 0.1,
            "retrieval_top1_top2_margin": 0.2,
            "retrieval_target_vs_top1_gap": 0.0,
            "acceptance_status": "AUTO_ACCEPT",
        }]),
    )


def test_campaign_templates_are_identical_blank_and_prediction_blinded(tmp_path):
    source_dir = tmp_path / "inputs"
    source_dir.mkdir()
    source = source_dir / "source.xlsx"
    source.write_bytes(b"frozen-workbook")
    digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "manifest_version": "schema-mapping-eval-v1",
        "workbooks": [{
            "source_file_name": source.name,
            "source_file_sha256": digest,
            "sheet": "Sheet1",
            "source_format": "row-oriented",
            "split": "validation",
        }],
    }), encoding="utf-8")

    output_a, output_b, metadata = prepare_campaign(
        manifest, source_dir, tmp_path / "campaign", pipeline_call=_pipeline_result,
    )
    frame_a = pd.read_excel(output_a, sheet_name="Annotations", dtype=object).fillna("")
    frame_b = pd.read_excel(output_b, sheet_name="Annotations", dtype=object).fillna("")
    assert frame_a.equals(frame_b)
    assert frame_a.columns.tolist() == BLINDED_COLUMNS
    assert all(frame_a.loc[0, column] == "" for column in HUMAN_COLUMNS)
    assert "proposed_target_canonical_key" not in frame_a
    assert pd.ExcelFile(output_a).sheet_names == ["Annotations", "Canonical Reference"]
    campaign_metadata = json.loads(metadata.read_text(encoding="utf-8"))
    assert campaign_metadata["prediction_blinded"] is True
    assert campaign_metadata["annotatable_item_count"] == 1


def test_campaign_refuses_hash_drift_and_overwrite(tmp_path):
    source_dir = tmp_path / "inputs"
    source_dir.mkdir()
    source = source_dir / "source.xlsx"
    source.write_bytes(b"current")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "manifest_version": "schema-mapping-eval-v1",
        "workbooks": [{
            "source_file_name": source.name,
            "source_file_sha256": "0" * 64,
            "sheet": "Sheet1",
            "source_format": "row-oriented",
            "split": "validation",
        }],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare_campaign(manifest, source_dir, tmp_path / "campaign", pipeline_call=_pipeline_result)


def test_finalize_campaign_exports_strict_gold_and_full_history(tmp_path):
    schema = CanonicalSchema.from_template()
    identity = {
        "source_file_sha256": "a" * 64,
        "source_sheet": "Sheet1",
        "source_format": "row-oriented",
        "identity_kind": "source_attribute_display",
        "identity_value": "Height",
    }
    common = {
        "mapping_item_id": build_mapping_item_id(**identity),
        "mapping_identity_kind": identity["identity_kind"],
        "mapping_identity_value": identity["identity_value"],
        "source_file_name": "source.xlsx",
        "source_file_sha256": identity["source_file_sha256"],
        "source_sheet": identity["source_sheet"],
        "source_format": identity["source_format"],
        "source_attribute_display": "Height",
        "source_attribute": "Height",
        "annotation_round": 1,
    }
    annotation_a = GoldMappingAnnotation(
        **common, gold_status="NO_MATCH", gold_canonical_keys=[], annotator_id="annotator_A",
    )
    annotation_b = GoldMappingAnnotation(
        **common, gold_status="ONE_TO_ONE",
        gold_canonical_keys=[schema.rows[0].canonical_key], annotator_id="annotator_B",
    )
    path_a, path_b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    pd.DataFrame([_annotation_row(annotation_a)], columns=FINAL_COLUMNS).to_excel(path_a, index=False)
    pd.DataFrame([_annotation_row(annotation_b)], columns=FINAL_COLUMNS).to_excel(path_b, index=False)
    adjudication = tmp_path / "adjudication.xlsx"
    frame = create_adjudication_template([annotation_a], [annotation_b])
    frame.loc[0, "adjudicated_status"] = "NO_MATCH"
    frame.loc[0, "adjudicator_id"] = "adjudicator_1"
    frame.loc[0, "adjudication_notes"] = "Resolved from source evidence."
    frame.to_excel(adjudication, index=False)

    final_path = tmp_path / "final.xlsx"
    history_path = tmp_path / "history.json"
    finalize_campaign(path_a, path_b, adjudication, final_path, history_path)
    final = load_gold_annotations(final_path, schema=schema).annotations[0]
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert final.annotation_source == "adjudicated"
    assert final.gold_status.value == "NO_MATCH"
    assert history[0]["annotation_a"]["annotator_id"] == "annotator_A"
    assert history[0]["annotation_b"]["annotator_id"] == "annotator_B"
    assert history[0]["final_annotation"]["annotator_id"] == "adjudicator_1"
