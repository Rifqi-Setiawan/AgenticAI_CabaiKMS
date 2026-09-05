"""Structured, cell-level provenance for committed canonical values."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def source_file_sha256(path: Path | str) -> str:
    """Fingerprint the exact source workbook bytes with SHA-256."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CellProvenanceRecord(BaseModel):
    run_id: str
    source_file_name: str
    source_file_sha256: str
    source_sheet: str
    source_attribute: str
    source_context: str | None = None
    source_attribute_display: str
    # Exact coordinates are unavailable until Source IR/structure understanding.
    source_cells: list[str] = Field(default_factory=list)
    variety: str
    canonical_row_id: str
    canonical_key: str
    canonical_label: str
    canonical_domain: str
    raw_value: Any
    normalized_value: Any
    normalization_required: bool
    mapping_confidence: float
    acceptance_status: Literal["AUTO_ACCEPT"]
    acceptance_reason: str
    canonical_write: Literal[True] = True
    schema_version: str
    template_hash: str
    mapping_method: str | None = None
