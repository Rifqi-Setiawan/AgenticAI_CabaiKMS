"""Workbook-grouped validation/test manifest for schema-mapping evaluation."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EVALUATION_MANIFEST_VERSION = "schema-mapping-eval-v1"


class EvaluationSplit(str, Enum):
    VALIDATION = "validation"
    TEST = "test"


class EvaluationWorkbookEntry(BaseModel):
    source_file_name: str = Field(min_length=1)
    source_file_sha256: str = Field(min_length=1)
    sheet: str = Field(min_length=1)
    source_format: str = Field(min_length=1)
    split: EvaluationSplit
    notes: str | None = None
    variation_tags: list[str] = Field(default_factory=list)


class EvaluationManifest(BaseModel):
    manifest_version: Literal["schema-mapping-eval-v1"] = EVALUATION_MANIFEST_VERSION
    workbooks: list[EvaluationWorkbookEntry]

    @model_validator(mode="after")
    def _workbook_grouped_split(self) -> "EvaluationManifest":
        splits_by_hash: dict[str, set[EvaluationSplit]] = {}
        identities: set[tuple[str, str, str]] = set()
        for item in self.workbooks:
            digest = item.source_file_sha256.strip().lower()
            splits_by_hash.setdefault(digest, set()).add(item.split)
            identity = (digest, item.sheet.strip(), item.source_format.strip())
            if identity in identities:
                raise ValueError(f"duplicate manifest workbook entry: {identity}")
            identities.add(identity)
        leaked = sorted(digest for digest, splits in splits_by_hash.items() if len(splits) > 1)
        if leaked:
            raise ValueError(f"source SHA appears across validation and test splits: {leaked}")
        return self

    def split_for(self, source_file_sha256: str, sheet: str, source_format: str) -> EvaluationSplit:
        key = (source_file_sha256.strip().lower(), sheet.strip(), source_format.strip())
        matches = [item.split for item in self.workbooks if (
            item.source_file_sha256.strip().lower(), item.sheet.strip(), item.source_format.strip()
        ) == key]
        if len(matches) != 1:
            raise ValueError(f"manifest must contain exactly one matching workbook entry for {key}")
        return matches[0]


def assert_calibration_split(split: EvaluationSplit | str) -> None:
    if EvaluationSplit(split) is EvaluationSplit.TEST:
        raise ValueError("test split is evaluation-only and cannot be used for calibration or tuning")
