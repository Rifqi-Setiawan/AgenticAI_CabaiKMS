"""Versioned, machine-readable evidence from deterministic mapping verification."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from src.schema.provenance import MappingMethod

MAPPING_VERIFICATION_VERSION = "mapping-verification-v1"


class MappingVerificationStatus(str, Enum):
    """Verifier outcome; PASS is not a production acceptance decision."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class RetrievalEvidence(BaseModel):
    """Raw cosine-distance ranking evidence with one-based ranks.

    ``top1_top2_margin`` is ``top2_distance - top1_distance``.
    ``target_vs_top1_distance_gap`` is ``target_distance - top1_distance``.
    Values are stored without presentation rounding or verdict thresholds.
    """

    candidate_count: int = Field(ge=0)
    target_in_candidates: bool
    target_rank: int | None = Field(default=None, ge=1)
    target_distance: float | None = None
    top1_row_id: str | None = None
    top1_canonical_key: str | None = None
    top1_distance: float | None = None
    top2_row_id: str | None = None
    top2_canonical_key: str | None = None
    top2_distance: float | None = None
    top1_top2_margin: float | None = None
    target_vs_top1_distance_gap: float | None = None


class MappingVerificationResult(BaseModel):
    verification_version: Literal["mapping-verification-v1"] = MAPPING_VERIFICATION_VERSION
    status: MappingVerificationStatus
    mapping_method: MappingMethod
    source_attribute: str
    source_context: str | None = None
    source_attribute_id: str | None = None
    proposed_target_row_id: str | None = None
    proposed_target_canonical_key: str | None = None
    exact_name_status: Literal["MATCH", "NO_MATCH", "AMBIGUOUS"]
    exact_candidate_canonical_keys: list[str] = Field(default_factory=list)
    hard_issue_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    retrieval_evidence: RetrievalEvidence | None = None
    model_confidence: float | None = None
    recommendation_summary: str
