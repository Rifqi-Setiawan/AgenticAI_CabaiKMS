"""Versioned, human-authored ground truth for schema-mapping evaluation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable, Literal, Sequence

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from src.schema.canonical import CanonicalSchema

GOLD_MAPPING_VERSION = "schema-mapping-gold-v1"


class GoldMappingStatus(str, Enum):
    ONE_TO_ONE = "ONE_TO_ONE"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    COMPOSITE = "COMPOSITE"
    EXCLUDE = "EXCLUDE"


def build_mapping_item_id(
    *, source_file_sha256: str, source_sheet: str, source_format: str,
    source_attribute_id: str | None = None,
    source_attribute_display: str | None = None,
) -> str:
    """Hash stable source identity only; predictions can change independently."""
    source_identity = (source_attribute_id or source_attribute_display or "").strip()
    components = [source_file_sha256.strip().lower(), source_sheet.strip(), source_format.strip(), source_identity]
    if any(not item for item in components):
        raise ValueError("mapping item identity fields must be non-blank")
    serialized = json.dumps(components, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_mapping_item_ids(
    *, source_file_sha256: str, source_sheet: str, source_format: str,
    source_items: Iterable[tuple[str | None, str]],
) -> list[str]:
    """Build IDs and fail if a legacy display fallback is not unique."""
    items = list(source_items)
    displays = [display.strip() for _, display in items]
    duplicates = sorted(name for name, count in Counter(displays).items() if count > 1)
    if duplicates and any(not attr_id for attr_id, _ in items):
        raise ValueError(f"legacy source display identity is not unique: {duplicates}")
    # A unique display identity is shared by legacy and SourceIR-backed runs,
    # so it keeps item IDs stable across backend experiments. Coordinate IDs
    # are preferred only where duplicate displays require disambiguation.
    identities = [attr_id if duplicates else None for attr_id, _ in items]
    result = [build_mapping_item_id(
        source_file_sha256=source_file_sha256, source_sheet=source_sheet,
        source_format=source_format, source_attribute_id=identity,
        source_attribute_display=display,
    ) for identity, (_, display) in zip(identities, items)]
    if len(result) != len(set(result)):
        raise ValueError("mapping item identities collide")
    return result


class GoldMappingAnnotation(BaseModel):
    annotation_version: Literal["schema-mapping-gold-v1"] = GOLD_MAPPING_VERSION
    mapping_item_id: str = Field(min_length=1)
    source_file_name: str = Field(min_length=1)
    source_file_sha256: str = Field(min_length=1)
    source_sheet: str = Field(min_length=1)
    source_format: str = Field(min_length=1)
    source_attribute_id: str | None = None
    source_attribute_display: str = Field(min_length=1)
    source_attribute: str = Field(min_length=1)
    source_context: str | None = None
    gold_status: GoldMappingStatus
    gold_canonical_keys: list[str] = Field(default_factory=list)
    ambiguous_candidate_canonical_keys: list[str] = Field(default_factory=list)
    annotator_id: str = Field(min_length=1)
    annotation_round: int = Field(ge=1)
    notes: str | None = None
    created_at: datetime | None = None
    annotation_source: Literal["human_independent", "adjudicated", "legacy_unverified"] = "human_independent"
    calibration_eligible: bool = True

    @field_validator(
        "mapping_item_id", "source_file_name", "source_file_sha256", "source_sheet",
        "source_format", "source_attribute_display", "source_attribute", "annotator_id"
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identity and annotator fields must be non-blank")
        return value

    @model_validator(mode="after")
    def _validate_status_cardinality(self) -> "GoldMappingAnnotation":
        keys = self.gold_canonical_keys
        if len(keys) != len(set(keys)):
            raise ValueError("gold_canonical_keys must not contain duplicates")
        valid = {
            GoldMappingStatus.ONE_TO_ONE: len(keys) == 1,
            GoldMappingStatus.NO_MATCH: len(keys) == 0,
            GoldMappingStatus.COMPOSITE: len(keys) >= 2,
        }
        if self.gold_status in valid and not valid[self.gold_status]:
            raise ValueError(f"invalid canonical-key cardinality for {self.gold_status.value}")
        eligible = self.gold_status in {GoldMappingStatus.ONE_TO_ONE, GoldMappingStatus.NO_MATCH}
        if self.annotation_source == "legacy_unverified":
            eligible = False
        self.calibration_eligible = bool(self.calibration_eligible and eligible)
        return self

    @property
    def resolved_label(self) -> str | None:
        if self.gold_status is GoldMappingStatus.ONE_TO_ONE:
            return self.gold_canonical_keys[0]
        return "NO_MATCH" if self.gold_status is GoldMappingStatus.NO_MATCH else None


class GoldAnnotationSet(BaseModel):
    annotation_version: Literal["schema-mapping-gold-v1"] = GOLD_MAPPING_VERSION
    annotations: list[GoldMappingAnnotation]

    @model_validator(mode="after")
    def _unique_items(self) -> "GoldAnnotationSet":
        ids = [item.mapping_item_id for item in self.annotations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate mapping_item_id in annotation set")
        keys = [(item.mapping_item_id, item.annotator_id, item.annotation_round) for item in self.annotations]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate annotator annotation for item/round")
        return self


def validate_gold_annotations(
    annotations: GoldAnnotationSet | Sequence[GoldMappingAnnotation], schema: CanonicalSchema,
) -> list[GoldMappingAnnotation]:
    records = annotations.annotations if isinstance(annotations, GoldAnnotationSet) else list(annotations)
    GoldAnnotationSet(annotations=records)
    for record in records:
        unknown = (set(record.gold_canonical_keys) | set(record.ambiguous_candidate_canonical_keys)) - schema.row_keys
        if unknown:
            raise ValueError(f"unknown canonical key(s) for {record.mapping_item_id}: {sorted(unknown)}")
    return records


class AnnotatorAgreementMetrics(BaseModel):
    raw_agreement: float | None
    cohens_kappa: float | None
    number_compared: int
    number_excluded_from_kappa: int


def _cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    if not labels_a:
        return None
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / len(labels_a)
    counts_a, counts_b = Counter(labels_a), Counter(labels_b)
    classes = set(counts_a) | set(counts_b)
    expected = sum((counts_a[c] / len(labels_a)) * (counts_b[c] / len(labels_b)) for c in classes)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else None
    return (observed - expected) / (1.0 - expected)


def compare_annotators(
    annotations_a: GoldAnnotationSet | Sequence[GoldMappingAnnotation],
    annotations_b: GoldAnnotationSet | Sequence[GoldMappingAnnotation],
) -> tuple[pd.DataFrame, AnnotatorAgreementMetrics]:
    """Compare independent files by stable item identity, never row position."""
    a = annotations_a.annotations if isinstance(annotations_a, GoldAnnotationSet) else list(annotations_a)
    b = annotations_b.annotations if isinstance(annotations_b, GoldAnnotationSet) else list(annotations_b)
    by_a, by_b = {x.mapping_item_id: x for x in a}, {x.mapping_item_id: x for x in b}
    if len(by_a) != len(a) or len(by_b) != len(b):
        raise ValueError("annotator inputs must have unique mapping_item_id values")
    if set(by_a) != set(by_b):
        raise ValueError("annotator item sets differ")
    rows, labels_a, labels_b = [], [], []
    excluded = 0
    for item_id in sorted(by_a):
        left, right = by_a[item_id], by_b[item_id]
        agrees = left.gold_status == right.gold_status and set(left.gold_canonical_keys) == set(right.gold_canonical_keys)
        if left.gold_status != right.gold_status:
            disagreement = "STATUS"
        elif set(left.gold_canonical_keys) != set(right.gold_canonical_keys):
            disagreement = "CANONICAL_KEYS"
        else:
            disagreement = "NONE"
        rows.append({
            "mapping_item_id": item_id,
            "status_A": left.gold_status.value,
            "status_B": right.gold_status.value,
            "canonical_keys_A": "|".join(sorted(left.gold_canonical_keys)),
            "canonical_keys_B": "|".join(sorted(right.gold_canonical_keys)),
            "agrees": agrees,
            "disagreement_type": disagreement,
        })
        if left.resolved_label is None or right.resolved_label is None:
            excluded += 1
        else:
            labels_a.append(left.resolved_label)
            labels_b.append(right.resolved_label)
    raw = sum(row["agrees"] for row in rows) / len(rows) if rows else None
    return pd.DataFrame(rows), AnnotatorAgreementMetrics(
        raw_agreement=raw, cohens_kappa=_cohens_kappa(labels_a, labels_b),
        number_compared=len(rows), number_excluded_from_kappa=excluded,
    )


def create_adjudication_template(
    annotations_a: Sequence[GoldMappingAnnotation],
    annotations_b: Sequence[GoldMappingAnnotation],
    output_path: Path | str | None = None,
) -> pd.DataFrame:
    agreement, _ = compare_annotators(annotations_a, annotations_b)
    disagreements = agreement.loc[~agreement["agrees"]].copy()
    for column in ("adjudicated_status", "adjudicated_canonical_keys", "adjudicator_id", "adjudication_notes"):
        disagreements[column] = ""
    if output_path is not None:
        path = Path(output_path)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite adjudication artifact: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        disagreements.to_excel(path, index=False)
    return disagreements


class AdjudicatedGoldRecord(BaseModel):
    """Final decision plus the immutable two-annotator decision history."""

    mapping_item_id: str
    annotation_a: GoldMappingAnnotation
    annotation_b: GoldMappingAnnotation
    agreement: bool
    final_annotation: GoldMappingAnnotation
    adjudicated: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> "AdjudicatedGoldRecord":
        ids = {self.mapping_item_id, self.annotation_a.mapping_item_id, self.annotation_b.mapping_item_id, self.final_annotation.mapping_item_id}
        if len(ids) != 1:
            raise ValueError("adjudication history mapping_item_id mismatch")
        independently_agrees = (
            self.annotation_a.gold_status == self.annotation_b.gold_status
            and set(self.annotation_a.gold_canonical_keys) == set(self.annotation_b.gold_canonical_keys)
        )
        if self.agreement != independently_agrees:
            raise ValueError("agreement flag does not match independent annotations")
        if not independently_agrees and not self.adjudicated:
            raise ValueError("disagreement requires explicit adjudication")
        if independently_agrees and (
            self.final_annotation.gold_status != self.annotation_a.gold_status
            or set(self.final_annotation.gold_canonical_keys) != set(self.annotation_a.gold_canonical_keys)
        ):
            raise ValueError("agreed annotations must be preserved as final gold")
        return self


def merge_adjudicated_gold(
    annotations_a: Sequence[GoldMappingAnnotation],
    annotations_b: Sequence[GoldMappingAnnotation],
    adjudicated_resolutions: Sequence[GoldMappingAnnotation] = (),
) -> list[AdjudicatedGoldRecord]:
    """Merge agreements and explicit resolutions while preserving full history."""
    by_a = {item.mapping_item_id: item for item in annotations_a}
    by_b = {item.mapping_item_id: item for item in annotations_b}
    resolutions = {item.mapping_item_id: item for item in adjudicated_resolutions}
    if len(by_a) != len(annotations_a) or len(by_b) != len(annotations_b) or len(resolutions) != len(adjudicated_resolutions):
        raise ValueError("all adjudication inputs require unique mapping_item_id values")
    if set(by_a) != set(by_b):
        raise ValueError("annotator item sets differ")
    unexpected = set(resolutions) - set(by_a)
    if unexpected:
        raise ValueError(f"adjudication contains unknown item(s): {sorted(unexpected)}")
    merged = []
    for item_id in sorted(by_a):
        left, right = by_a[item_id], by_b[item_id]
        agreement = left.gold_status == right.gold_status and set(left.gold_canonical_keys) == set(right.gold_canonical_keys)
        if agreement:
            if item_id in resolutions:
                raise ValueError(f"agreed item must not be overridden by adjudication: {item_id}")
            final, adjudicated = left, False
        else:
            if item_id not in resolutions:
                raise ValueError(f"explicit adjudicated resolution required for {item_id}")
            final, adjudicated = resolutions[item_id], True
            if final.annotation_source != "adjudicated":
                raise ValueError(f"adjudicated resolution must declare annotation_source='adjudicated': {item_id}")
        merged.append(AdjudicatedGoldRecord(
            mapping_item_id=item_id, annotation_a=left, annotation_b=right,
            agreement=agreement, final_annotation=final, adjudicated=adjudicated,
        ))
    return merged
