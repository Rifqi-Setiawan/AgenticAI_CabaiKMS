"""Versioned deterministic diagnostics for legacy versus Source IR shadow parity."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SHADOW_PARITY_VERSION = "shadow-parity-v1"


class ShadowStatus(str, Enum):
    MATCH = "MATCH"
    DIFFERENT = "DIFFERENT"
    NEW_PATH_ABSTAINED = "NEW_PATH_ABSTAINED"
    NEW_PATH_FAILED = "NEW_PATH_FAILED"
    LEGACY_FAILED = "LEGACY_FAILED"
    BOTH_FAILED = "BOTH_FAILED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class PositionMismatch(BaseModel):
    position_index: int
    legacy_value: Any = None
    source_ir_value: Any = None


class AttributeParity(BaseModel):
    legacy_identity: str
    source_ir_identity: str
    legacy_index: int
    source_ir_index: int
    identity_match: bool
    context_match: bool
    order_match: bool
    legacy_value_count: int
    source_ir_value_count: int
    matching_positions: int
    differing_positions: int
    values_match: bool
    position_mismatches: list[PositionMismatch] = Field(default_factory=list)


class ShadowParityReport(BaseModel):
    parity_version: Literal["shadow-parity-v1"] = SHADOW_PARITY_VERSION
    status: ShadowStatus
    source_format: Literal["row-oriented", "transposed"]
    new_orientation: Literal["row-oriented", "transposed"] | None = None
    orientation_match: bool | None = None
    issue_codes: list[str] = Field(default_factory=list)
    structure_status: str | None = None
    structure_reason_codes: list[str] = Field(default_factory=list)
    verification_issue_codes: list[str] = Field(default_factory=list)
    evidence_rounds: int = 0
    new_path_resolved: bool = False
    legacy_error_type: str | None = None
    legacy_error_message: str | None = None
    new_path_error_type: str | None = None
    new_path_error_message: str | None = None
    legacy_attribute_count: int = 0
    source_ir_attribute_count: int = 0
    matched_attribute_count: int = 0
    attribute_identity_matches: int = 0
    attribute_context_matches: int = 0
    attributes_with_full_value_match: int = 0
    total_value_positions_compared: int = 0
    matching_value_positions: int = 0
    differing_value_positions: int = 0
    legacy_only_count: int = 0
    source_ir_only_count: int = 0
    attribute_identity_parity: float | None = None
    value_position_parity: float | None = None
    order_match: bool | None = None
    attributes: list[AttributeParity] = Field(default_factory=list)
    legacy_only_attributes: list[str] = Field(default_factory=list)
    source_ir_only_attributes: list[str] = Field(default_factory=list)
    legacy_anchor_status: str | None = None
    source_ir_anchor_status: str | None = None
    legacy_anchor_identity: str | None = None
    source_ir_anchor_identity: str | None = None
    anchor_match: bool | None = None
    anchor_values_match: bool | None = None
    entity_names_match: bool | None = None
    entity_position_mismatches: list[PositionMismatch] = Field(default_factory=list)
    summary: str
