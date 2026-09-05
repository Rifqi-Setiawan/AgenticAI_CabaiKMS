"""Deterministic parity gate for explicit Source IR production promotion."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.ingestion.runtime_source import (
    AnchorDetector,
    RuntimeSourceBundle,
    SourceFormat,
    parsed_attribute_from_runtime,
    prepare_legacy_runtime_source,
    prepare_source_ir_runtime_source,
)
from src.ingestion.shadow_parity import compare_shadow_parity
from src.ingestion.source_ir_adapter import source_ir_to_parsed_attributes
from src.ingestion.structure_candidate import (
    build_structure_candidate,
    sanitize_structure_error_message,
)
from src.schema.shadow_parity import ShadowParityReport, ShadowStatus
from src.schema.structure import StructureStatus


class SourceMigrationGateError(RuntimeError):
    def __init__(self, report: ShadowParityReport):
        self.status = report.status
        self.issue_codes = list(report.issue_codes)
        self.summary = report.summary
        self.report = report
        super().__init__(
            f"Source IR migration gate rejected {report.status.value}: "
            f"{', '.join(report.issue_codes) or report.summary}"
        )


def _candidate_metadata(candidate) -> dict:
    understanding = candidate.understanding_result
    return {
        "structure_status": (
            understanding.final_proposal.status.value if understanding else None
        ),
        "structure_reason_codes": (
            understanding.final_proposal.reason_codes if understanding else []
        ),
        "verification_issue_codes": (
            understanding.verification.issue_codes
            if understanding and understanding.verification is not None
            else []
        ),
        "evidence_rounds": understanding.evidence_rounds if understanding else 0,
    }


def prepare_gated_runtime_source(
    file_path: Path,
    sheet_name: str,
    *,
    source_format: SourceFormat,
    header_rows: int | None = None,
    llm_call: Callable | None = None,
    anchor_detector: AnchorDetector | None = None,
) -> RuntimeSourceBundle:
    """Promote one Source IR candidate only after exact legacy parity MATCH."""
    legacy_bundle = None
    legacy_error = None
    try:
        legacy_bundle = prepare_legacy_runtime_source(
            file_path,
            sheet_name,
            source_format=source_format,
            header_rows=header_rows,
            anchor_detector=anchor_detector,
        )
    except Exception as exc:  # noqa: BLE001 - converted to explicit gate evidence
        legacy_error = exc

    candidate = build_structure_candidate(
        file_path,
        sheet_name,
        llm_call=llm_call,
    )
    metadata = _candidate_metadata(candidate)

    if legacy_error is not None:
        resolved = candidate.source_ir is not None
        report = ShadowParityReport(
            status=ShadowStatus.LEGACY_FAILED if resolved else ShadowStatus.BOTH_FAILED,
            source_format=source_format,
            new_orientation=(
                candidate.source_ir.tables[0].orientation if resolved else None
            ),
            new_path_resolved=resolved,
            legacy_error_type=type(legacy_error).__name__,
            legacy_error_message=sanitize_structure_error_message(legacy_error),
            new_path_error_type=candidate.error_type,
            new_path_error_message=candidate.error_message,
            source_ir_attribute_count=(
                len(source_ir_to_parsed_attributes(candidate.source_ir))
                if candidate.source_ir is not None
                else 0
            ),
            issue_codes=["LEGACY_REFERENCE_UNAVAILABLE"],
            summary=(
                "LEGACY_FAILED — Source IR candidate resolved but cannot be promoted "
                "without a legacy parity reference"
                if resolved
                else "BOTH_FAILED — no legacy reference and no Source IR candidate"
            ),
            **metadata,
        )
        raise SourceMigrationGateError(report)

    assert legacy_bundle is not None
    if candidate.source_ir is None:
        understanding = candidate.understanding_result
        abstained = (
            understanding is not None
            and understanding.final_proposal.status
            in {StructureStatus.AMBIGUOUS, StructureStatus.UNSUPPORTED}
        )
        status = ShadowStatus.NEW_PATH_ABSTAINED if abstained else ShadowStatus.NEW_PATH_FAILED
        report = ShadowParityReport(
            status=status,
            source_format=source_format,
            legacy_attribute_count=len(legacy_bundle.all_attributes),
            new_path_error_type=candidate.error_type,
            new_path_error_message=candidate.error_message,
            issue_codes=[status.value],
            summary=f"{status.value} — Source IR cannot be promoted",
            **metadata,
        )
        raise SourceMigrationGateError(report)

    legacy_attributes = [
        parsed_attribute_from_runtime(item) for item in legacy_bundle.all_attributes
    ]
    report = compare_shadow_parity(
        legacy_attributes,
        candidate.source_ir,
        source_format=source_format,
        legacy_entity_names=legacy_bundle.position_to_variety,
        anchor_detector=anchor_detector,
    ).model_copy(update=metadata)
    if report.status is not ShadowStatus.MATCH:
        raise SourceMigrationGateError(report)

    return prepare_source_ir_runtime_source(
        candidate.source_ir,
        anchor_detector=anchor_detector,
        migration_report=report,
    )
