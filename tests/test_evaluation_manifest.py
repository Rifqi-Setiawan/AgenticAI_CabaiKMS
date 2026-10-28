import pytest
from pydantic import ValidationError

from src.schema.evaluation_manifest import (
    EvaluationManifest,
    EvaluationSplit,
    EvaluationWorkbookEntry,
    assert_calibration_split,
)


def _entry(digest, split, sheet="Sheet1"):
    return EvaluationWorkbookEntry(
        source_file_name="source.xlsx", source_file_sha256=digest, sheet=sheet,
        source_format="row-oriented", split=split,
    )


def test_manifest_groups_every_workbook_hash_into_one_split():
    manifest = EvaluationManifest(workbooks=[
        _entry("a" * 64, "validation", "Sheet1"),
        _entry("a" * 64, "validation", "Sheet2"),
        _entry("b" * 64, "test"),
    ])
    assert manifest.split_for("a" * 64, "Sheet2", "row-oriented") is EvaluationSplit.VALIDATION


def test_duplicate_hash_across_splits_fails():
    with pytest.raises(ValidationError, match="across validation and test"):
        EvaluationManifest(workbooks=[_entry("a" * 64, "validation"), _entry("a" * 64, "test", "Sheet2")])


def test_calibration_refuses_test_split():
    with pytest.raises(ValueError, match="evaluation-only"):
        assert_calibration_split("test")
