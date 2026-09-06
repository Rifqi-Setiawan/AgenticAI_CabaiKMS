import pandas as pd
import pytest

from src.schema.calibration import build_calibration_dataset
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


def _mapping(item, prediction):
    return {
        "mapping_item_id": item, "source_file_sha256": DIGEST, "source_sheet": "Sheet1",
        "source_format": "row-oriented", "mapping_method": "retrieve_rerank",
        "proposed_target_canonical_key": prediction, "acceptance_status": "AUTO_ACCEPT",
        "confidence": 0.9, "exact_name_status": "NO_MATCH", "verifier_status": "PASS",
        "verifier_warnings": [], "verifier_hard_issues": [],
    }


def _manifest():
    return EvaluationManifest(workbooks=[EvaluationWorkbookEntry(
        source_file_name="source.xlsx", source_file_sha256=DIGEST, sheet="Sheet1",
        source_format="row-oriented", split="validation",
    )])


def test_calibration_join_is_order_independent_and_correctness_is_prediction_only():
    mappings = pd.DataFrame([_mapping("A", "key_a"), _mapping("B", None), _mapping("C", "wrong")])
    frame = build_calibration_dataset(mappings, [_gold("C", "key_c"), _gold("A", "key_a"), _gold("B", None)], _manifest())
    by_id = frame.set_index("mapping_item_id")
    assert bool(by_id.loc["A", "prediction_correct"]) is True
    assert bool(by_id.loc["B", "prediction_correct"]) is True
    assert bool(by_id.loc["C", "prediction_correct"]) is False


def test_non_calibratable_and_legacy_gold_remain_reported():
    annotation = _gold("A", None).model_copy(update={
        "gold_status": GoldMappingStatus.AMBIGUOUS, "annotation_source": "legacy_unverified",
        "calibration_eligible": False,
    })
    frame = build_calibration_dataset(pd.DataFrame([_mapping("A", None)]), [annotation], _manifest())
    assert not bool(frame.loc[0, "calibration_eligible"])
    assert pd.isna(frame.loc[0, "prediction_correct"])
    assert frame.attrs["excluded_counts"] == {"AMBIGUOUS": 1, "legacy_unverified": 1}


def test_calibration_join_rejects_item_set_mismatch():
    with pytest.raises(ValueError, match="item sets differ"):
        build_calibration_dataset(pd.DataFrame([_mapping("A", None)]), [_gold("B", None)], _manifest())
