"""Isolated legacy-versus-Source-IR shadow execution with structured failures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from src.ingestion.runtime_source import (
    AnchorDetector,
    parsed_attribute_from_runtime,
    prepare_legacy_runtime_source,
)
from src.ingestion.shadow_parity import compare_shadow_parity
from src.ingestion.source_ir_adapter import source_ir_to_parsed_attributes
from src.ingestion.structure_candidate import (
    build_structure_candidate,
    sanitize_structure_error_message,
)
from src.ingestion.workbook_profiler import profile_workbook
from src.schema.shadow_parity import ShadowParityReport, ShadowStatus
from src.schema.structure import StructureStatus


def sanitize_shadow_error_message(exc: Exception) -> str:
    """Backward-compatible name for the shared candidate error sanitizer."""
    return sanitize_structure_error_message(exc)


def _error(exc: Exception) -> tuple[str, str]:
    return type(exc).__name__, sanitize_structure_error_message(exc)


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
    legacy_bundle = None
    legacy_error: tuple[str, str] | None = None
    try:
        legacy_bundle = prepare_legacy_runtime_source(
            file_path,
            sheet_name,
            source_format=source_format,
            header_rows=header_rows,
            anchor_detector=anchor_detector,
        )
    except Exception as exc:  # noqa: BLE001 - shadow failures are report data
        legacy_error = _error(exc)

    candidate = build_structure_candidate(
        file_path,
        sheet_name,
        llm_call=llm_call,
        profile_call=profile_workbook,
    )
    understanding = candidate.understanding_result
    source_ir = candidate.source_ir
    structure_status = (
        understanding.final_proposal.status.value if understanding is not None else None
    )
    reason_codes = understanding.final_proposal.reason_codes if understanding else []
    verification_codes = (
        understanding.verification.issue_codes
        if understanding is not None and understanding.verification is not None
        else []
    )
    evidence_rounds = understanding.evidence_rounds if understanding else 0

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
            new_path_error_type=candidate.error_type,
            new_path_error_message=candidate.error_message,
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

    assert legacy_bundle is not None
    legacy_attributes = [
        parsed_attribute_from_runtime(item) for item in legacy_bundle.all_attributes
    ]
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
            new_path_error_type=candidate.error_type,
            new_path_error_message=candidate.error_message,
            issue_codes=[issue],
            summary=f"{status.value} — legacy output remains available and authoritative",
        )

    report = compare_shadow_parity(
        legacy_attributes,
        source_ir,
        source_format=source_format,
        legacy_entity_names=legacy_bundle.position_to_variety,
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
