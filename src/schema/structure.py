"""Versioned contracts for probabilistic structure proposals and verification."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

STRUCTURE_CONTRACT_VERSION = "structure-understanding-v1"
Orientation = Literal["row-oriented", "transposed"]


class StructureStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NEED_MORE_EVIDENCE = "NEED_MORE_EVIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"


class ColumnHeaderBinding(BaseModel):
    column_letter: str
    header_cells: list[str]


class RowOrientedStructure(BaseModel):
    table_range: str
    header_rows: list[int]
    data_start_row: int
    data_end_row: int
    attribute_columns: list[str]
    header_bindings: list[ColumnHeaderBinding]


class TransposedStructure(BaseModel):
    table_range: str
    header_row: int
    label_column: str
    data_columns: list[str]
    attribute_start_row: int
    attribute_end_row: int


class StructureProposal(BaseModel):
    contract_version: Literal["structure-understanding-v1"] = STRUCTURE_CONTRACT_VERSION
    status: StructureStatus
    orientation: Orientation | None = None
    row_oriented: RowOrientedStructure | None = None
    transposed: TransposedStructure | None = None
    requested_ranges: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    evidence_summary: str

    @model_validator(mode="after")
    def _validate_logical_shape(self) -> StructureProposal:
        if self.status is StructureStatus.RESOLVED:
            if self.orientation == "row-oriented":
                if self.row_oriented is None or self.transposed is not None:
                    raise ValueError("resolved row-oriented proposal requires only row_oriented")
            elif self.orientation == "transposed":
                if self.transposed is None or self.row_oriented is not None:
                    raise ValueError("resolved transposed proposal requires only transposed")
            else:
                raise ValueError("resolved proposal requires a supported orientation")
            if self.requested_ranges:
                raise ValueError("resolved proposal cannot request more evidence")
        elif self.status is StructureStatus.NEED_MORE_EVIDENCE:
            if not self.requested_ranges:
                raise ValueError("NEED_MORE_EVIDENCE requires requested_ranges")
            if self.row_oriented is not None or self.transposed is not None:
                raise ValueError("NEED_MORE_EVIDENCE cannot include a resolved structure")
        else:
            if self.row_oriented is not None or self.transposed is not None:
                raise ValueError("abstention proposals cannot include a resolved structure")
        return self


class StructureVerificationResult(BaseModel):
    valid: bool
    issue_codes: list[str] = Field(default_factory=list)
    issue_details: list[str] = Field(default_factory=list)
    verified_orientation: Orientation | None = None


class VerifiedStructure(BaseModel):
    proposal: StructureProposal
    verification: StructureVerificationResult

    @model_validator(mode="after")
    def _require_verified_resolution(self) -> VerifiedStructure:
        if self.proposal.status is not StructureStatus.RESOLVED or not self.verification.valid:
            raise ValueError("VerifiedStructure requires a RESOLVED proposal and valid verification")
        if self.verification.verified_orientation != self.proposal.orientation:
            raise ValueError("verified orientation does not match proposal")
        return self


class StructureUnderstandingResult(BaseModel):
    final_proposal: StructureProposal
    verification: StructureVerificationResult | None = None
    verified_structure: VerifiedStructure | None = None
    evidence_rounds: int = 0
    requested_ranges_history: list[list[str]] = Field(default_factory=list)
