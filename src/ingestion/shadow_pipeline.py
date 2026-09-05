"""Isolated legacy-versus-Source-IR shadow execution with structured failures."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from src.agents.schema_matching.source_parsing import (
    ParsedAttribute,
    load_row_oriented_columns,
    load_transposed_rows,
)
from src.ingestion.shadow_parity import AnchorDetector, compare_shadow_parity
from src.ingestion.source_ir_adapter import source_ir_to_parsed_attributes
from src.ingestion.source_ir_builder import build_source_ir
from src.ingestion.structure_understanding import understand_sheet_structure
from src.ingestion.workbook_profiler import profile_workbook
from src.schema.shadow_parity import ShadowParityReport, ShadowStatus
from src.schema.structure import StructureStatus


def sanitize_shadow_error_message(exc: Exception) -> str:
    """Bound and redact common credential assignments from observable failures."""
    message = " ".join(str(exc).split())
    message = re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        message,
    )
    return message[:500]


def _error(exc: Exception) -> tuple[str, str]:
    return type(exc).__name__, sanitize_shadow_error_message(exc)


def run_structure_shadow(
    file_path: Path,
    sheet_name: str,
    *,
    source_format: Literal["row-oriented", "transposed"],
    header_rows: int | None = None,
    llm_call: Callable | None = None,
    anchor_detector: AnchorDetector | None = None,
) -> ShadowParityReport:
    """Run both parsers for observation only; never feed shadow output downstream."""
    legacy_attributes: list[ParsedAttribute] | None = None
    legacy_entities: list[str] | None = None
    legacy_error: tuple[str, str] | None = None
    try:
        if source_format == "row-oriented":
            legacy_attributes = load_row_oriented_columns(
                file_path, sheet_name, header_rows=header_rows
            )
        else:
            legacy_attributes, legacy_entities = load_transposed_rows(file_path, sheet_name)
    except Exception as exc:  # noqa: BLE001 - shadow failures are report data
        legacy_error = _error(exc)

    understanding = None
    source_ir = None
    new_error: tuple[str, str] | None = None
    try:
        profile = profile_workbook(file_path)
        sheet = next(item for item in profile.sheets if item.sheet_name == sheet_name)
        understanding = understand_sheet_structure(sheet, llm_call=llm_call)
        if understanding.verified_structure is not None:
            source_ir = build_source_ir(profile, sheet_name, understanding.verified_structure)
    except Exception as exc:  # noqa: BLE001 - isolated shadow boundary
        new_error = _error(exc)

    structure_status = (
        understanding.final_proposal.status.value if understanding is not None else None
    )
    reason_codes = (
        understanding.final_proposal.reason_codes if understanding is not None else []
    )
    verification_codes = (
        understanding.verification.issue_codes
        if understanding is not None and understanding.verification is not None
        else []
    )
    evidence_rounds = understanding.evidence_rounds if understanding is not None else 0

    if legacy_error is not None and source_ir is None:
        return ShadowParityReport(
            status=ShadowStatus.BOTH_FAILED,
            source_format=source_format,
            structure_status=structure_status,
            structure_reason_codes=reason_codes,
            verification_issue_codes=verification_codes,
            evidence_rounds=evidence_rounds,
            legacy_error_type=legacy_error[0],
            legacy_error_message=legacy_error[1],
            new_path_error_type=new_error[0] if new_error else None,
            new_path_error_message=new_error[1] if new_error else None,
            issue_codes=["LEGACY_PATH_FAILED", "NEW_PATH_UNAVAILABLE"],
            summary="BOTH_FAILED — neither path produced comparable source attributes",
        )

    if legacy_error is not None and source_ir is not None:
        adapted = source_ir_to_parsed_attributes(source_ir)
        return ShadowParityReport(
            status=ShadowStatus.LEGACY_FAILED,
            source_format=source_format,
            new_orientation=source_ir.tables[0].orientation,
            structure_status=structure_status,
            structure_reason_codes=reason_codes,
            evidence_rounds=evidence_rounds,
            new_path_resolved=True,
            legacy_error_type=legacy_error[0],
            legacy_error_message=legacy_error[1],
            source_ir_attribute_count=len(adapted),
            issue_codes=["LEGACY_PATH_FAILED"],
            summary=(
                f"LEGACY_FAILED — shadow resolved {len(adapted)} attributes; "
                "no parity claim is possible"
            ),
        )

    assert legacy_attributes is not None
    if source_ir is None:
        abstained = (
            understanding is not None
            and understanding.final_proposal.status
            in {StructureStatus.AMBIGUOUS, StructureStatus.UNSUPPORTED}
        )
        status = ShadowStatus.NEW_PATH_ABSTAINED if abstained else ShadowStatus.NEW_PATH_FAILED
        issue = "NEW_PATH_ABSTAINED" if abstained else "NEW_PATH_FAILED"
        return ShadowParityReport(
            status=status,
            source_format=source_format,
            structure_status=structure_status,
            structure_reason_codes=reason_codes,
            verification_issue_codes=verification_codes,
            evidence_rounds=evidence_rounds,
            legacy_attribute_count=len(legacy_attributes),
            new_path_error_type=new_error[0] if new_error else None,
            new_path_error_message=new_error[1] if new_error else None,
            issue_codes=[issue],
            summary=f"{status.value} — legacy output remains available and authoritative",
        )

    report = compare_shadow_parity(
        legacy_attributes,
        source_ir,
        source_format=source_format,
        legacy_entity_names=legacy_entities,
        anchor_detector=anchor_detector,
    )
    return report.model_copy(
        update={
            "structure_status": structure_status,
            "structure_reason_codes": reason_codes,
            "verification_issue_codes": verification_codes,
            "evidence_rounds": evidence_rounds,
        }
    )
