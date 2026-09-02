"""Pydantic data contracts for the acquisition pipeline (proposal boundary spec).

These are the shapes LLM/vision agent output gets parsed into. Validation
against the canonical schema (which canonical rows exist right now) is done
dynamically against a loaded CanonicalSchema — never against a hardcoded
Literal of row ids — so adding a row to the template requires no code change
here.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from .canonical import CanonicalSchema

NULL_ROW = "NULL"


@lru_cache(maxsize=1)
def _default_schema() -> CanonicalSchema:
    return CanonicalSchema.from_template()


def clear_default_schema_cache() -> None:
    """Call after the template changes so contracts re-validate against the
    fresh row set instead of a stale cached one (full auto re-index lands in
    Fase 3a; this is the manual escape hatch until then)."""
    _default_schema.cache_clear()


def valid_row_ids(schema: CanonicalSchema | None = None) -> frozenset[str]:
    schema = schema or _default_schema()
    return schema.row_ids | {NULL_ROW}


class SchemaMapping(BaseModel):
    """One agent's proposed mapping of a source spreadsheet attribute onto a
    canonical row (or NULL, meaning "doesn't map to any canonical row")."""

    source_attribute: str
    source_context: str | None = None
    source_format: Literal["transposed", "row-oriented"]
    target_canonical_row: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    normalization_required: bool

    @field_validator("target_canonical_row")
    @classmethod
    def _validate_target_row(cls, value: str) -> str:
        valid = valid_row_ids()
        if value not in valid:
            raise ValueError(
                f"target_canonical_row {value!r} is not a known canonical row id "
                f"(expected one of {sorted(valid)})"
            )
        return value

    @computed_field  # type: ignore[misc]
    @property
    def target_domain(self) -> str | None:
        """Derived from target_canonical_row via row_domains.yaml — never
        requested from the LLM directly (see docs/DESIGN_DECISIONS.md (b))."""
        if self.target_canonical_row == NULL_ROW:
            return None
        row = _default_schema().row_by_id(self.target_canonical_row)
        return row.domain if row is not None else None


class VisionResult(BaseModel):
    """Output of the image-to-plant-part classification agent for one photo."""

    classification_status: Literal["KNOWN", "OTHER", "UNCERTAIN"]
    matched_variety: str | None = None
    identified_part: Literal["DAUN", "BATANG", "BUAH", "BUNGA"]
    confidence: float = Field(ge=0.0, le=1.0)
    visual_evidence: str


class ImageMetadata(BaseModel):
    """Drive file metadata for one image. No relative_path — Drive listing is
    flat (see docs/DESIGN_DECISIONS.md (c))."""

    file_id: str
    filename: str
    mime_type: str
    size: int
    created_time: datetime
