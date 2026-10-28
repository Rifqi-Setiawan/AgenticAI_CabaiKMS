"""Data contracts for CabaiKMS JSONB document storage."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from src.storage.contracts import Contract, Sha256


class PlantIdentity(Contract):
    """Taxonomic plant identity contract."""

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=256)
    identity_level: Literal["source_category", "species", "cultivar"]
    scientific_name: str | None = None
    source_category: str | None = None

    @property
    def variety_id(self) -> str:
        return self.id

    @property
    def canonical_name(self) -> str:
        return self.label


class AdministrativePath(Contract):
    """Four-tier administrative hierarchy contract."""

    province_id: str = ""
    regency_id: str = ""
    district_id: str = ""
    village_id: str = ""
    province_name: str
    regency_name: str
    district_name: str
    village_name: str

    @field_validator(
        "province_name", "regency_name", "district_name", "village_name", mode="before"
    )
    @classmethod
    def strip_text(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="before")
    @classmethod
    def populate_name_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "province" in data and "province_name" not in data:
                data["province_name"] = data["province"]
            if "regency" in data and "regency_name" not in data:
                data["regency_name"] = data["regency"]
            if "district" in data and "district_name" not in data:
                data["district_name"] = data["district"]
            if "village" in data and "village_name" not in data:
                data["village_name"] = data["village"]
        return data

    @property
    def province(self) -> str:
        return self.province_name

    @property
    def regency(self) -> str:
        return self.regency_name

    @property
    def district(self) -> str:
        return self.district_name

    @property
    def village(self) -> str:
        return self.village_name


class HabitatIdentity(Contract):
    """Geographical habitat identity contract."""

    id: str = Field(min_length=1, max_length=64)
    definition: Literal["administrative_village_v1"] = "administrative_village_v1"
    administrative_path: AdministrativePath
    label: str

    @property
    def habitat_id(self) -> str:
        return self.id

    @model_validator(mode="before")
    @classmethod
    def populate_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "habitat_id" in data and "id" not in data:
                data["id"] = data["habitat_id"]
        return data


def make_unknown_habitat() -> HabitatIdentity:
    """Return sentinel habitat identity for varieties discovered without location."""
    return HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Unknown",
            regency_name="Unknown",
            district_name="Unknown",
            village_name="Unknown",
        ),
        label="Habitat Tidak Diketahui",
    )


class SamplingLocationDetail(Contract):
    """Sampling location metadata contract."""

    location_ref: str
    raw_address: str
    hamlet: str | None = None
    sampling_marker: str | None = None
    coordinates: dict[str, float] | None = None
    elevation_mdpl: float | None = None
    soil_ph: float | None = None

    @property
    def sample_marker(self) -> str | None:
        return self.sampling_marker

    @model_validator(mode="before")
    @classmethod
    def map_marker(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "sample_marker" in data and "sampling_marker" not in data:
                data["sampling_marker"] = data["sample_marker"]
        return data


class CurrentSourceReference(Contract):
    """Source cell reference provenance contract."""

    source_ref: str
    sheet: str
    row: int
    cell: str
    location_ref: str = ""
    run_id: str | None = None
    workbook_name: str | None = None
    sheet_name: str | None = None
    row_index: int | None = None
    timestamp: datetime | None = None

    @property
    def sheet_title(self) -> str:
        return self.sheet

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "sheet_name" in data and "sheet" not in data:
                data["sheet"] = data["sheet_name"]
            if "row_index" in data and "row" not in data:
                data["row"] = data["row_index"]
            if "workbook_name" in data and "source_ref" not in data:
                data["source_ref"] = data["workbook_name"]
            if "run_id" in data and "source_ref" not in data:
                data["source_ref"] = data["run_id"]
        return data


class AttributeValue(Contract):
    """Single attribute measurement value contract."""

    label: str = Field(min_length=1)
    value: Any
    value_type: Literal["text", "number", "range", "boolean", "list"]
    unit: str | None = None
    resolution: Literal["AUTO_ACCEPT", "HUMAN_REVIEW"]
    mapping_policy_version: str = "exact-alias-policy-v1"
    current_source: CurrentSourceReference
    attribute_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    updated_at: datetime | None = None

    @property
    def status(self) -> str:
        return self.resolution

    @property
    def source_ref(self) -> CurrentSourceReference:
        return self.current_source

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "status" in data and "resolution" not in data:
                data["resolution"] = data["status"]
            if "source_ref" in data and "current_source" not in data:
                data["current_source"] = data["source_ref"]
        return data

    @model_validator(mode="after")
    def validate_value_shape(self) -> AttributeValue:
        val = self.value
        vt = self.value_type

        def _is_num(x: Any) -> bool:
            return (
                type(x) in (int, float)
                and not isinstance(x, bool)
                and math.isfinite(x)
            )

        if vt == "number":
            if not _is_num(val):
                raise ValueError(
                    f"Value '{val}' is not a valid finite number for value_type 'number'."
                )
        elif vt == "boolean":
            if not isinstance(val, bool):
                raise ValueError(
                    f"Value '{val}' is not a boolean for value_type 'boolean'."
                )
        elif vt == "range":
            if not isinstance(val, dict) or set(val.keys()) != {"min", "max"}:
                raise ValueError(
                    f"Value '{val}' is not a dict with 'min' and 'max' for value_type 'range'."
                )
            if not _is_num(val.get("min")) or not _is_num(val.get("max")):
                raise ValueError(f"Range bounds '{val}' must be finite numbers.")
            if val["min"] > val["max"]:
                raise ValueError(f"Range min {val['min']} must be <= max {val['max']}.")
        elif vt == "list":
            if not isinstance(val, list) or len(val) == 0:
                raise ValueError(
                    f"Value '{val}' must be a non-empty list for value_type 'list'."
                )
        elif vt == "text":
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"Value '{val}' must be a non-empty text string for value_type 'text'."
                )
        return self


class MediaReference(Contract):
    """Media asset reference contract."""

    asset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    organ_part: Literal["habitus", "daun", "batang", "bunga", "buah", "biji"]
    caption: str | None = None
    source_filename: str | None = None
    provenance_run_id: str
    assigned_via: Literal["AUTO_ACCEPT", "HITL_REVIEW"]
    resolution_status: Literal["linked", "discarded"] = "linked"


class KnowledgeDocument(Contract):
    """JSONB Knowledge Document entity contract."""

    schema_version: Literal["kms-document-v1"] = "kms-document-v1"
    variety: PlantIdentity
    habitat: HabitatIdentity
    sampling_locations: list[SamplingLocationDetail] = Field(default_factory=list)
    attributes: dict[str, AttributeValue]
    media_refs: list[MediaReference] = Field(default_factory=list)
    updated_by_run: str = ""
    doc_id: str | None = None
    version: int = Field(default=1, ge=1)
    updated_at: datetime | None = None
    habitat_unknown: bool = Field(default=False)

    @model_validator(mode="before")
    @classmethod
    def reject_history_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            prohibited = {
                "previous_value",
                "observations",
                "history",
                "previous_values",
            }
            found = prohibited.intersection(data.keys())
            if found:
                raise ValueError(f"Historical arrays are strictly prohibited: {found}")
        return data

    @model_validator(mode="after")
    def set_deterministic_doc_id(self) -> KnowledgeDocument:
        if not self.doc_id and self.variety and self.habitat:
            self.doc_id = f"{self.variety.id}:{self.habitat.id}"
        return self


class PhotoContextSignal(Contract):
    """Context signal extracted from photo filename and metadata."""

    filename: str
    caption: str | None = None
    extracted_part: Literal["DAUN", "BATANG", "BUAH", "BUNGA"] | None = None
    suggested_variety_hint: str | None = None
    is_exact_hint: bool = True
    raw_tokens: list[str] = Field(default_factory=list)
    extracted_organ: str | None = None
    extracted_variety_hints: list[str] = Field(default_factory=list)

    @property
    def organ(self) -> str | None:
        return self.extracted_organ or self.extracted_part

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "extracted_organ" in data and "extracted_part" not in data:
                data["extracted_part"] = data["extracted_organ"]
            if (
                "extracted_variety_hints" in data
                and "suggested_variety_hint" not in data
            ):
                hints = data["extracted_variety_hints"]
                if isinstance(hints, list) and hints:
                    data["suggested_variety_hint"] = hints[0]
        return data


class VisionClassificationResult(Contract):
    """Vision classification result contract."""

    classification_status: Literal["KNOWN", "OTHER", "UNCERTAIN"]
    matched_variety: str | None = None
    identified_part: Literal["DAUN", "BATANG", "BUAH", "BUNGA"]
    visual_confidence: float = Field(ge=0.0, le=1.0)
    text_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    visual_evidence: str
    options_evaluated: list[str] = Field(default_factory=list)
    signals_consistent: bool = False
    predicted_variety: str | None = None
    status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "predicted_variety" in data and "matched_variety" not in data:
                data["matched_variety"] = data["predicted_variety"]
            if "status" in data and "classification_status" not in data:
                status_map = {
                    "AUTO_ASSIGN": "KNOWN",
                    "NO_MATCH": "OTHER",
                    "UNCERTAIN": "UNCERTAIN",
                }
                data["classification_status"] = status_map.get(
                    data["status"], data["status"]
                )
        return data


class PhotoMismatchDecision(Contract):
    """Curator decision for photo mismatch review."""

    action: Literal["ASSIGN_EXISTING", "CREATE_NEW_DOCUMENT", "DISCARD"]
    selected_variety_id: str | None = None
    selected_variety_label: str | None = None
    target_habitat_id: str | None = None
    new_variety_name: str | None = None
    identity_level: Literal["source_category", "species", "cultivar"] | None = None
    discard_reason: str | None = None
    notes: str | None = None


class OverwriteDecision(Contract):
    """Curator decision for overwrite review resolution."""

    action: Literal["KEEP_EXISTING", "APPLY_INCOMING", "REVISE"]
    corrected_value: Any = None
    corrected_unit: str | None = None
    reason: str | None = None
    notes: str | None = None


class DocumentReviewItem(Contract):
    """Review item contract for document discrepancies."""

    item_id: str
    category: Literal[
        "LOCATION_UNRESOLVED",
        "LOCATION_AMBIGUOUS",
        "LOCATION_CONFLICT",
        "PLANT_IDENTITY_UNRESOLVED",
        "NEW_ATTRIBUTE",
        "AMBIGUOUS_MAPPING",
        "VALUE_INVALID",
        "INTRA_RUN_VALUE_CONFLICT",
        "PHOTO_VARIETY_MISMATCH",
        "LOW_CONFIDENCE_MATCH",
        "INTRA_WORKBOOK_CONFLICT",
        "UNRESOLVED_LOCATION",
        "OVERWRITE_BLOCKED",
        "UNIT_MISMATCH",
    ]
    target_document_key: str | None = None
    source_label: str = ""
    source_context: str = ""
    raw_values: list[Any] = Field(default_factory=list)
    candidate_resolutions: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "approved", "revised", "rejected"] = "pending"
    decision: dict[str, Any] | None = None
    notes: str | None = None
    run_id: str | None = None
    doc_id: str | None = None
    review_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "review_type" in data and "category" not in data:
                data["category"] = data["review_type"]
            if "doc_id" in data and "target_document_key" not in data:
                data["target_document_key"] = data["doc_id"]
        return data


class DocumentDraft(Contract):
    """Draft staging envelope for atomic document persistence."""

    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    source_filename: str
    file_sha256: Sha256
    source_uri: str | None = None
    source_scope: str
    schema_version: str
    template_hash: Sha256
    config_fingerprint: str
    revision: int = Field(ge=1)
    documents: dict[str, KnowledgeDocument]
    reviews: list[DocumentReviewItem] = Field(default_factory=list)
    base_versions: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("documents")
    @classmethod
    def validate_document_keys(
        cls, documents: dict[str, KnowledgeDocument]
    ) -> dict[str, KnowledgeDocument]:
        for key, doc in documents.items():
            expected_key = f"{doc.variety.id}:{doc.habitat.id}"
            if key != expected_key:
                raise ValueError(
                    f"Document key '{key}' does not match expected identity '{expected_key}'."
                )
        return documents


class StageV2Request(Contract):
    """Draft staging envelope request for atomic document persistence."""

    draft: DocumentDraft
    expected_revision: int = Field(default=0, ge=0)


class CommitReceipt(Contract):
    """Receipt documenting successful atomic document commit."""

    run_id: str
    revision: int = 1
    documents_created: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    reviews_resolved: int = 0
    attributes_committed: int = 0
    media_linked: int = 0
    media_discarded: int = 0
    replayed: bool = False
    committed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    receipt_id: str | None = None
    committed_documents_count: int | None = None

    @property
    def timestamp(self) -> datetime:
        return self.committed_at

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "timestamp" in data and "committed_at" not in data:
                data["committed_at"] = data["timestamp"]
        return data


def validate_document(
    payload: KnowledgeDocument | dict[str, Any],
) -> KnowledgeDocument:
    """Validate JSONB document envelope fail-closed."""
    if isinstance(payload, KnowledgeDocument):
        return payload
    return KnowledgeDocument.model_validate(payload)


__all__ = [
    "AdministrativePath",
    "AttributeValue",
    "CommitReceipt",
    "CurrentSourceReference",
    "DocumentDraft",
    "DocumentReviewItem",
    "HabitatIdentity",
    "KnowledgeDocument",
    "MediaReference",
    "PhotoContextSignal",
    "PhotoMismatchDecision",
    "OverwriteDecision",
    "PlantIdentity",
    "SamplingLocationDetail",
    "StageV2Request",
    "VisionClassificationResult",
    "validate_document",
]
