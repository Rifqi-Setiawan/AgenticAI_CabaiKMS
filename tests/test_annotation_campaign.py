import hashlib
import json
from types import SimpleNamespace

import pandas as pd

from eval.create_mapping_annotations import ANNOTATION_COLUMNS
from eval.finalize_mapping_annotations import FINAL_COLUMNS, _annotation_row, finalize_campaign
from eval.prepare_annotation_campaign import (
    BLINDED_COLUMNS, HUMAN_COLUMNS, PREDICTION_COLUMNS,
    assess_campaign_readiness, prepare_campaign,
)
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import EvaluationRunConfig
from src.schema.gold_mapping import (
    GoldMappingAnnotation, build_mapping_item_id, create_adjudication_template,
    load_gold_annotations,
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_source(path):
    pd.DataFrame({"Jenis Cabai": ["A", "B"], "Height": [10, 12]}).to_excel(path, sheet_name="Sheet1", index=False)


def _manifest(tmp_path, *, entries=None):
    schema = CanonicalSchema.from_template()
    config = EvaluationRunConfig(
        source_backend="legacy", retrieval_backend="exact", retrieval_k=8,
        canonical_schema_version=schema.schema_version,
        canonical_template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2",
    )
    source = tmp_path / "source.xlsx"
    if not source.exists():
        _write_source(source)
    default_entry = {
        "entry_id": "source-sheet1", "path": "source.xlsx", "sha256": _sha(source),
        "source_format": "row-oriented", "sheets": ["Sheet1"],
        "source_backend": "legacy", "retrieval_backend": "exact", "retrieval_k": 8,
        "part_of_validation": True,
        "counts": {"annotatable_attributes": 1, "stable_mapping_identities": 1, "unavailable_identities": 0},
    }
    payload = {
        "campaign_version": "schema-mapping-validation-campaign-v1",
        "annotation_version": "schema-mapping-gold-v1", "annotation_round": 1,
        "canonical_schema_version": schema.schema_version,
        "canonical_template_hash": schema.template_hash,
        "mapping_verification_version": "mapping-verification-v1",
        "embedding_model_name": "paraphrase-multilingual-MiniLM-L12-v2",
        "source_backend": "legacy", "retrieval_backend": "exact", "retrieval_k": 8,
        "frozen_evaluation_config_fingerprint": config.fingerprint,
        "annotation_guideline_version": "annotation-guidelines-v1",
        "annotation_guideline_path": "guideline.md",
        "validation_workbooks": entries or [default_entry],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "guideline.md").write_text("test guideline", encoding="utf-8")
    return path, payload, default_entry


def _pipeline_result(path, *, source_format, sheet_name, **kwargs):
    schema = CanonicalSchema.from_template()
    digest = _sha(path)
    config = EvaluationRunConfig(
        source_backend="legacy", retrieval_backend="exact", retrieval_k=8,
        canonical_schema_version=schema.schema_version,
        canonical_template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2",
    )
    identity = {
        "source_file_sha256": digest, "source_sheet": sheet_name,
        "source_format": source_format, "identity_kind": "source_attribute_display",
        "identity_value": "Height",
    }
    return SimpleNamespace(
        mapping_verifications=[], source_backend="legacy", retrieval_backend="exact", retrieval_k=8,
        schema_version=schema.schema_version, template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="paraphrase-multilingual-MiniLM-L12-v2",
        evaluation_config_fingerprint=config.fingerprint,
        mapping_df=pd.DataFrame([{
            "mapping_item_id": build_mapping_item_id(**identity),
            "mapping_identity_kind": identity["identity_kind"], "mapping_identity_value": "Height",
            "mapping_identity_issue": None, "source_file_name": path.name,
            "source_file_sha256": digest, "source_sheet": sheet_name, "source_format": source_format,
            "source_attribute_id": None, "source_attribute_display": "Height", "source_attribute": "Height",
            "source_context": None, "proposed_target_canonical_key": schema.rows[0].canonical_key,
            "predicted_row": schema.rows[0].id, "mapping_method": "retrieve_rerank", "confidence": 0.9,
            "exact_name_status": "NO_MATCH", "verifier_status": "PASS", "verifier_warnings": [],
            "verifier_hard_issues": [], "retrieval_target_rank": 1, "retrieval_target_distance": 0.1,
            "retrieval_top1_top2_margin": 0.2, "retrieval_target_vs_top1_gap": 0.0,
            "acceptance_status": "AUTO_ACCEPT",
        }]),
    )


def _generated(tmp_path):
    manifest, payload, _ = _manifest(tmp_path)
    paths = prepare_campaign(manifest, tmp_path / "campaign", project_root=tmp_path, pipeline_call=_pipeline_result)
    return paths, payload


def test_a_b_ids_blank_fields_and_identical_order(tmp_path):
    (_, _, path_a, path_b, _), _ = _generated(tmp_path)
    a = pd.read_excel(path_a, sheet_name="Annotations", dtype=object).fillna("")
    b = pd.read_excel(path_b, sheet_name="Annotations", dtype=object).fillna("")
    assert a.equals(b)
    assert a["mapping_item_id"].tolist() == b["mapping_item_id"].tolist()
    assert all(a[column].eq("").all() for column in HUMAN_COLUMNS)


def test_master_has_predictions_but_blinded_views_do_not(tmp_path):
    (_, master_path, path_a, _, _), _ = _generated(tmp_path)
    master = pd.read_excel(master_path, sheet_name="Annotations")
    blinded = pd.read_excel(path_a, sheet_name="Annotations")
    assert master.columns.tolist() == ANNOTATION_COLUMNS
    assert PREDICTION_COLUMNS <= set(master.columns)
    assert not (PREDICTION_COLUMNS & set(blinded.columns))
    assert blinded.columns.tolist() == BLINDED_COLUMNS


def test_immutable_provenance_matches_master_and_a_b(tmp_path):
    (_, master_path, path_a, path_b, _), _ = _generated(tmp_path)
    master = pd.read_excel(master_path, sheet_name="Annotations", dtype=object).fillna("")
    a = pd.read_excel(path_a, sheet_name="Annotations", dtype=object).fillna("")
    b = pd.read_excel(path_b, sheet_name="Annotations", dtype=object).fillna("")
    immutable = [column for column in BLINDED_COLUMNS if column not in HUMAN_COLUMNS]
    assert master[immutable].equals(a[immutable])
    assert a[immutable].equals(b[immutable])


def test_mixed_configuration_causes_readiness_failure(tmp_path):
    manifest, payload, entry = _manifest(tmp_path)
    mixed = dict(entry, entry_id="mixed", retrieval_k=9)
    payload["validation_workbooks"].append(mixed)
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    report = assess_campaign_readiness(manifest, project_root=tmp_path)
    assert report["campaign_ready"] is False
    assert any(item.startswith("MIXED_EVALUATION_CONFIGURATION:mixed") for item in report["blockers"])


def test_hash_mismatch_causes_readiness_failure(tmp_path):
    manifest, payload, _ = _manifest(tmp_path)
    payload["validation_workbooks"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    report = assess_campaign_readiness(manifest, project_root=tmp_path)
    assert report["campaign_ready"] is False
    assert "WORKBOOK_HASH_MISMATCH:source-sheet1" in report["blockers"]


def test_identity_unavailable_causes_readiness_failure(tmp_path):
    manifest, payload, _ = _manifest(tmp_path)
    payload["validation_workbooks"][0]["counts"] = {
        "annotatable_attributes": 2, "stable_mapping_identities": 0, "unavailable_identities": 2,
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    attribute = lambda: SimpleNamespace(source_attribute_id=None, display_name="Duplicate")
    loader = lambda *args, **kwargs: SimpleNamespace(all_attributes=[attribute(), attribute()], schema_attributes=[attribute(), attribute()])
    report = assess_campaign_readiness(manifest, project_root=tmp_path, source_loader=loader)
    assert report["campaign_ready"] is False
    assert report["unavailable_identity_count"] == 2
    assert any(item.startswith("IDENTITY_UNAVAILABLE") for item in report["blockers"])


def test_duplicate_mapping_item_id_causes_readiness_failure(tmp_path):
    manifest, payload, entry = _manifest(tmp_path)
    payload["validation_workbooks"] = [entry, dict(entry, entry_id="same-input-again")]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    report = assess_campaign_readiness(manifest, project_root=tmp_path)
    assert report["campaign_ready"] is False
    assert report["duplicate_mapping_item_id_count"] == 1


def test_metadata_fingerprint_matches_master_observations(tmp_path):
    (_, master_path, _, _, metadata_path), payload = _generated(tmp_path)
    master = pd.read_excel(master_path, sheet_name="Annotations")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert master["evaluation_config_fingerprint"].unique().tolist() == [payload["frozen_evaluation_config_fingerprint"]]
    assert metadata["frozen_evaluation_config_fingerprint"] == payload["frozen_evaluation_config_fingerprint"]


def test_strict_loader_accepts_completed_fixture_from_blinded_template(tmp_path):
    (_, _, path_a, _, _), _ = _generated(tmp_path)
    frame = pd.read_excel(path_a, sheet_name="Annotations", dtype=object)
    frame.loc[0, "gold_status"] = "NO_MATCH"
    frame.loc[0, "annotator_id"] = "annotator_fixture"
    frame.loc[0, "annotation_round"] = 1
    completed = tmp_path / "completed.xlsx"
    frame.to_excel(completed, index=False)
    loaded = load_gold_annotations(completed, schema=CanonicalSchema.from_template())
    assert len(loaded.annotations) == 1


def test_finalize_campaign_exports_strict_gold_and_traceable_history(tmp_path):
    schema = CanonicalSchema.from_template()
    identity = {"source_file_sha256": "a" * 64, "source_sheet": "Sheet1", "source_format": "row-oriented", "identity_kind": "source_attribute_display", "identity_value": "Height"}
    common = {
        "mapping_item_id": build_mapping_item_id(**identity), "mapping_identity_kind": identity["identity_kind"],
        "mapping_identity_value": identity["identity_value"], "source_file_name": "source.xlsx",
        "source_file_sha256": identity["source_file_sha256"], "source_sheet": "Sheet1",
        "source_format": "row-oriented", "source_attribute_display": "Height",
        "source_attribute": "Height", "annotation_round": 1,
    }
    a = GoldMappingAnnotation(**common, gold_status="NO_MATCH", gold_canonical_keys=[], annotator_id="annotator_A")
    b = GoldMappingAnnotation(**common, gold_status="ONE_TO_ONE", gold_canonical_keys=[schema.rows[0].canonical_key], annotator_id="annotator_B")
    path_a, path_b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    pd.DataFrame([_annotation_row(a)], columns=FINAL_COLUMNS).to_excel(path_a, index=False)
    pd.DataFrame([_annotation_row(b)], columns=FINAL_COLUMNS).to_excel(path_b, index=False)
    adjudication = tmp_path / "adjudication.xlsx"
    frame = create_adjudication_template([a], [b])
    frame.loc[0, "adjudicated_status"] = "NO_MATCH"
    frame.loc[0, "adjudicator_id"] = "adjudicator_1"
    frame.loc[0, "adjudication_notes"] = "Resolved from source evidence."
    frame.to_excel(adjudication, index=False)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"campaign_version": "campaign-v1", "frozen_evaluation_config_fingerprint": "f" * 64}), encoding="utf-8")
    final_path, history_path = tmp_path / "final.xlsx", tmp_path / "history.json"
    finalize_campaign(path_a, path_b, adjudication, final_path, history_path, metadata)
    final = load_gold_annotations(final_path, schema=schema).annotations[0]
    final_frame = pd.read_excel(final_path)
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert final.annotation_source == "adjudicated"
    assert final_frame.loc[0, "campaign_version"] == "campaign-v1"
    assert history["records"][0]["annotation_a"]["annotator_id"] == "annotator_A"
    assert history["frozen_evaluation_config_fingerprint"] == "f" * 64
