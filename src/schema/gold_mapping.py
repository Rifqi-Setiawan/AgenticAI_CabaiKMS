"""Versioned, human-authored ground truth for schema-mapping evaluation."""

from __future__ import annotations

import hashlib
import json
import math
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


class MappingIdentityKind(str, Enum):
    SOURCE_ATTRIBUTE_DISPLAY = "source_attribute_display"
    SOURCE_ATTRIBUTE_ID = "source_attribute_id"
    UNAVAILABLE = "unavailable"


class MappingItemIdentity(BaseModel):
    mapping_item_id: str | None = None
    identity_kind: MappingIdentityKind
    identity_value: str | None = None
    issue_code: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "MappingItemIdentity":
        unavailable = self.identity_kind is MappingIdentityKind.UNAVAILABLE
        if unavailable and (self.mapping_item_id is not None or self.identity_value is not None):
            raise ValueError("unavailable mapping identity cannot contain an ID or identity value")
        if unavailable and self.issue_code != "STABLE_MAPPING_IDENTITY_UNAVAILABLE":
            raise ValueError("unavailable mapping identity requires its stable-identity issue code")
        if not unavailable and (not self.mapping_item_id or not self.identity_value or self.issue_code):
            raise ValueError("available mapping identity requires ID/value and no issue code")
        return self


def build_mapping_item_id(
    *, source_file_sha256: str, source_sheet: str, source_format: str,
    identity_kind: MappingIdentityKind | str | None = None,
    identity_value: str | None = None,
    source_attribute_id: str | None = None,
    source_attribute_display: str | None = None,
) -> str:
    """Hash an explicit identity basis; legacy source arguments remain compatible."""
    if identity_kind is None:
        if source_attribute_id:
            identity_kind = MappingIdentityKind.SOURCE_ATTRIBUTE_ID
            identity_value = source_attribute_id
        elif source_attribute_display:
            identity_kind = MappingIdentityKind.SOURCE_ATTRIBUTE_DISPLAY
            identity_value = source_attribute_display
        else:
            raise ValueError("explicit identity_kind and identity_value are required")
    kind = MappingIdentityKind(identity_kind)
    if kind is MappingIdentityKind.UNAVAILABLE:
        raise ValueError("cannot build a hash for unavailable mapping identity")
    components = [
        source_file_sha256.strip().lower(), source_sheet.strip(), source_format.strip(),
        kind.value, (identity_value or "").strip(),
    ]
    if any(not item for item in components):
        raise ValueError("mapping item identity fields must be non-blank")
    serialized = json.dumps(components, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_mapping_item_identities(
    *, source_file_sha256: str, source_sheet: str, source_format: str,
    source_items: Iterable[tuple[str | None, str]],
) -> list[MappingItemIdentity]:
    """Choose identity independently for each display group without raising."""
    items = list(source_items)
    displays = [display.strip() for _, display in items]
    counts = Counter(displays)
    attribute_id_counts = Counter(
        attribute_id.strip() for attribute_id, _ in items
        if attribute_id and attribute_id.strip()
    )
    result: list[MappingItemIdentity] = []
    for (attribute_id, _), display in zip(items, displays):
        if counts[display] == 1:
            kind = MappingIdentityKind.SOURCE_ATTRIBUTE_DISPLAY
            value = display
        elif attribute_id and attribute_id.strip() and attribute_id_counts[attribute_id.strip()] == 1:
            kind = MappingIdentityKind.SOURCE_ATTRIBUTE_ID
            value = attribute_id.strip()
        else:
            result.append(MappingItemIdentity(
                identity_kind=MappingIdentityKind.UNAVAILABLE,
                issue_code="STABLE_MAPPING_IDENTITY_UNAVAILABLE",
            ))
            continue
        item_id = build_mapping_item_id(
            source_file_sha256=source_file_sha256, source_sheet=source_sheet,
            source_format=source_format, identity_kind=kind, identity_value=value,
        )
        result.append(MappingItemIdentity(
            mapping_item_id=item_id, identity_kind=kind, identity_value=value,
        ))
    return result


def build_mapping_item_ids(
    *, source_file_sha256: str, source_sheet: str, source_format: str,
    source_items: Iterable[tuple[str | None, str]],
) -> list[str | None]:
    """Backward-compatible ID-only view of ``build_mapping_item_identities``."""
    return [item.mapping_item_id for item in build_mapping_item_identities(
        source_file_sha256=source_file_sha256, source_sheet=source_sheet,
        source_format=source_format, source_items=source_items,
    )]


def validate_mapping_item_identity(
    *, mapping_item_id: str, source_file_sha256: str, source_sheet: str,
    source_format: str, identity_kind: MappingIdentityKind | str,
    identity_value: str,
) -> None:
    expected = build_mapping_item_id(
        source_file_sha256=source_file_sha256, source_sheet=source_sheet,
        source_format=source_format, identity_kind=identity_kind,
        identity_value=identity_value,
    )
    if mapping_item_id != expected:
        raise ValueError("mapping_item_id does not match immutable source identity fields")


class GoldMappingAnnotation(BaseModel):
    annotation_version: Literal["schema-mapping-gold-v1"] = GOLD_MAPPING_VERSION
    mapping_item_id: str = Field(min_length=1)
    mapping_identity_kind: MappingIdentityKind | None = None
    mapping_identity_value: str | None = None
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


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _pipe_keys(value: object) -> list[str]:
    text = _cell_text(value)
    return [part.strip() for part in text.split("|") if part.strip()] if text else []


def load_gold_annotations(
    path: Path | str,
    *,
    schema: CanonicalSchema,
    require_completed: bool = True,
) -> GoldAnnotationSet:
    """Strictly reload a human-edited CSV/XLSX annotation artifact."""
    annotation_path = Path(path)
    suffix = annotation_path.suffix.casefold()
    if suffix == ".xlsx":
        frame = pd.read_excel(annotation_path, dtype=object)
    elif suffix == ".csv":
        frame = pd.read_csv(annotation_path, dtype=object, keep_default_na=False)
    else:
        raise ValueError("annotation input must be .xlsx or .csv")
    required_columns = {
        "annotation_version", "mapping_item_id", "mapping_identity_kind",
        "mapping_identity_value", "source_file_name", "source_file_sha256",
        "source_sheet", "source_format", "source_attribute_display",
        "source_attribute", "gold_status", "gold_canonical_keys",
        "annotator_id", "annotation_round",
    }
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise ValueError(f"annotation artifact missing required column(s): {missing}")
    records: list[GoldMappingAnnotation] = []
    for index, row in frame.iterrows():
        row_number = index + 2
        status_text = _cell_text(row["gold_status"])
        annotator_id = _cell_text(row["annotator_id"])
        round_text = _cell_text(row["annotation_round"])
        if require_completed and (not status_text or not annotator_id or not round_text):
            raise ValueError(f"annotation row {row_number} is incomplete")
        if not status_text or not annotator_id or not round_text:
            raise ValueError("partial annotation loading is not supported by the finalized gold contract")
        try:
            annotation_round = int(float(round_text))
            if float(round_text) != annotation_round:
                raise ValueError
        except ValueError as exc:
            raise ValueError(f"annotation row {row_number} has invalid annotation_round") from exc
        item_id = _cell_text(row["mapping_item_id"])
        kind = _cell_text(row["mapping_identity_kind"])
        identity_value = _cell_text(row["mapping_identity_value"])
        if not item_id or not identity_value or kind == MappingIdentityKind.UNAVAILABLE.value:
            raise ValueError(f"stable annotation identity unavailable at row {row_number}")
        identity_fields = {
            "mapping_item_id": item_id,
            "source_file_sha256": _cell_text(row["source_file_sha256"]),
            "source_sheet": _cell_text(row["source_sheet"]),
            "source_format": _cell_text(row["source_format"]),
            "identity_kind": kind,
            "identity_value": identity_value,
        }
        try:
            validate_mapping_item_identity(**identity_fields)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"annotation identity verification failed at row {row_number}: {exc}") from exc
        record = GoldMappingAnnotation(
            annotation_version=_cell_text(row["annotation_version"]),
            mapping_item_id=item_id,
            mapping_identity_kind=MappingIdentityKind(kind),
            mapping_identity_value=identity_value,
            source_file_name=_cell_text(row["source_file_name"]),
            source_file_sha256=identity_fields["source_file_sha256"],
            source_sheet=identity_fields["source_sheet"],
            source_format=identity_fields["source_format"],
            source_attribute_id=_cell_text(row.get("source_attribute_id")) or None,
            source_attribute_display=_cell_text(row["source_attribute_display"]),
            source_attribute=_cell_text(row["source_attribute"]),
            source_context=_cell_text(row.get("source_context")) or None,
            gold_status=GoldMappingStatus(status_text),
            gold_canonical_keys=_pipe_keys(row["gold_canonical_keys"]),
            ambiguous_candidate_canonical_keys=_pipe_keys(row.get("ambiguous_candidate_canonical_keys")),
            annotator_id=annotator_id,
            annotation_round=annotation_round,
            notes=_cell_text(row.get("notes")) or None,
            annotation_source=_cell_text(row.get("annotation_source")) or "human_independent",
        )
        records.append(record)
    validated = validate_gold_annotations(records, schema)
    return GoldAnnotationSet(annotations=validated)


class AnnotatorAgreementMetrics(BaseModel):
    raw_agreement: float | None
    cohens_kappa: float | None
    number_compared: int
    number_excluded_from_kappa: int
    kappa_defined: bool
    kappa_undefined_reason: str | None = None


def _cohens_kappa(labels_a: list[str], labels_b: list[str]) -> tuple[float | None, str | None]:
    if not labels_a:
        return None, "NO_RESOLVED_ITEMS"
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / len(labels_a)
    counts_a, counts_b = Counter(labels_a), Counter(labels_b)
    classes = set(counts_a) | set(counts_b)
    expected = sum((counts_a[c] / len(labels_a)) * (counts_b[c] / len(labels_b)) for c in classes)
    if math.isclose(expected, 1.0):
        return None, "SINGLE_CLASS_DEGENERATE"
    return (observed - expected) / (1.0 - expected), None


def compare_annotators(
    annotations_a: GoldAnnotationSet | Sequence[GoldMappingAnnotation],
    annotations_b: GoldAnnotationSet | Sequence[GoldMappingAnnotation],
) -> tuple[pd.DataFrame, AnnotatorAgreementMetrics]:
    """Compare independent files by stable item identity, never row position."""
    a = annotations_a.annotations if isinstance(annotations_a, GoldAnnotationSet) else list(annotations_a)
    b = annotations_b.annotations if isinstance(annotations_b, GoldAnnotationSet) else list(annotations_b)
    annotators_a = {item.annotator_id for item in a}
    annotators_b = {item.annotator_id for item in b}
    if len(annotators_a) != 1 or len(annotators_b) != 1:
        raise ValueError("each independent annotation input must contain exactly one annotator_id")
    if annotators_a == annotators_b:
        raise ValueError("independent annotators must have different IDs")
    if any(item.annotation_source != "human_independent" for item in [*a, *b]):
        raise ValueError("independent comparison requires annotation_source='human_independent'")
    rounds_a = {item.annotation_round for item in a}
    rounds_b = {item.annotation_round for item in b}
    if len(rounds_a) != 1 or len(rounds_b) != 1 or rounds_a != rounds_b:
        raise ValueError("independent annotations must use one matching annotation_round")
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
    kappa, undefined_reason = _cohens_kappa(labels_a, labels_b)
    return pd.DataFrame(rows), AnnotatorAgreementMetrics(
        raw_agreement=raw, cohens_kappa=kappa,
        number_compared=len(rows), number_excluded_from_kappa=excluded,
        kappa_defined=kappa is not None, kappa_undefined_reason=undefined_reason,
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
