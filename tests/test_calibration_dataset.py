import pandas as pd
import pytest

from src.schema.calibration import build_calibration_dataset
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import EvaluationRunConfig
from src.schema.evaluation_manifest import EvaluationManifest, EvaluationWorkbookEntry
from src.schema.gold_mapping import GoldMappingAnnotation, GoldMappingStatus

DIGEST = "a" * 64


def _gold(item, key):
    status = GoldMappingStatus.NO_MATCH if key is None else GoldMappingStatus.ONE_TO_ONE
    return GoldMappingAnnotation(
        mapping_item_id=item, source_file_name="source.xlsx", source_file_sha256=DIGEST,
        source_sheet="Sheet1", source_format="row-oriented", source_attribute_display=item,
        source_attribute=item, gold_status=status, gold_canonical_keys=[] if key is None else [key],
        annotator_id="annotator_A", annotation_round=1,
    )


def _mapping(item, prediction, schema, *, retrieval_backend="exact"):
    config = EvaluationRunConfig(
        source_backend="legacy", retrieval_backend=retrieval_backend, retrieval_k=8,
        canonical_schema_version=schema.schema_version,
        canonical_template_hash=schema.template_hash,
        mapping_verification_version="mapping-verification-v1",
        embedding_model_name="embedding-model",
    )
    return {
        "mapping_item_id": item, "source_file_sha256": DIGEST, "source_sheet": "Sheet1",
        "source_format": "row-oriented", "mapping_method": "retrieve_rerank",
        "proposed_target_canonical_key": prediction, "acceptance_status": "AUTO_ACCEPT",
        "confidence": 0.9, "exact_name_status": "NO_MATCH", "verifier_status": "PASS",
        "verifier_warnings": [], "verifier_hard_issues": [],
        "source_backend": "legacy", "retrieval_backend": retrieval_backend,
        "retrieval_k": 8, "schema_version": schema.schema_version,
        "template_hash": schema.template_hash,
        "mapping_verification_version": "mapping-verification-v1",
        "embedding_model_name": "embedding-model",
        "evaluation_config_fingerprint": config.fingerprint,
    }


def _manifest():
    return EvaluationManifest(workbooks=[EvaluationWorkbookEntry(
        source_file_name="source.xlsx", source_file_sha256=DIGEST, sheet="Sheet1",
        source_format="row-oriented", split="validation",
    )])


def test_calibration_join_is_order_independent_and_correctness_is_prediction_only():
    schema = CanonicalSchema.from_template()
    key_a, key_c = schema.rows[0].canonical_key, schema.rows[1].canonical_key
    mappings = pd.DataFrame([_mapping("A", key_a, schema), _mapping("B", None, schema), _mapping("C", key_a, schema)])
    frame = build_calibration_dataset(mappings, [_gold("C", key_c), _gold("A", key_a), _gold("B", None)], _manifest(), schema=schema)
    by_id = frame.set_index("mapping_item_id")
    assert bool(by_id.loc["A", "prediction_correct"]) is True
    assert bool(by_id.loc["B", "prediction_correct"]) is True
    assert bool(by_id.loc["C", "prediction_correct"]) is False


def test_non_calibratable_and_legacy_gold_remain_reported():
    schema = CanonicalSchema.from_template()
    annotation = _gold("A", None).model_copy(update={
        "gold_status": GoldMappingStatus.AMBIGUOUS, "annotation_source": "legacy_unverified",
        "calibration_eligible": False,
    })
    frame = build_calibration_dataset(pd.DataFrame([_mapping("A", None, schema)]), [annotation], _manifest(), schema=schema)
    assert not bool(frame.loc[0, "calibration_eligible"])
    assert pd.isna(frame.loc[0, "prediction_correct"])
    assert frame.attrs["excluded_counts"] == {"AMBIGUOUS": 1, "legacy_unverified": 1}


def test_calibration_join_rejects_item_set_mismatch():
    schema = CanonicalSchema.from_template()
    with pytest.raises(ValueError, match="item sets differ"):
        build_calibration_dataset(pd.DataFrame([_mapping("A", None, schema)]), [_gold("B", None)], _manifest(), schema=schema)


def test_calibration_rejects_unknown_gold_and_mixed_configurations():
    schema = CanonicalSchema.from_template()
    with pytest.raises(ValueError, match="unknown canonical key"):
        build_calibration_dataset(
            pd.DataFrame([_mapping("A", schema.rows[0].canonical_key, schema)]),
            [_gold("A", "totally_fake_canonical_key")], _manifest(), schema=schema,
        )
    first = _mapping("A", schema.rows[0].canonical_key, schema, retrieval_backend="exact")
    second = _mapping("B", schema.rows[1].canonical_key, schema, retrieval_backend="chroma")
    with pytest.raises(ValueError, match="cannot mix"):
        build_calibration_dataset(
            pd.DataFrame([first, second]),
            [_gold("A", schema.rows[0].canonical_key), _gold("B", schema.rows[1].canonical_key)],
            _manifest(), schema=schema,
        )
