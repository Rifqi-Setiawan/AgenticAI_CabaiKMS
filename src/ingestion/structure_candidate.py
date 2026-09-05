"""Single-execution construction of a verified Source IR migration candidate."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.ingestion.source_ir_builder import build_source_ir
from src.ingestion.structure_understanding import understand_sheet_structure
from src.ingestion.workbook_profiler import WorkbookProfile, profile_workbook
from src.schema.source_ir import SourceIR
from src.schema.structure import StructureUnderstandingResult


@dataclass
class StructureCandidateResult:
    understanding_result: StructureUnderstandingResult | None = None
    source_ir: SourceIR | None = None
    error_type: str | None = None
    error_message: str | None = None


def sanitize_structure_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    message = re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        message,
    )
    return message[:500]


def build_structure_candidate(
    file_path: Path,
    sheet_name: str,
    *,
    llm_call: Callable | None = None,
    profile_call: Callable[[Path], WorkbookProfile] = profile_workbook,
) -> StructureCandidateResult:
    """Profile, reason, verify, and build Source IR exactly once per attempt."""
    understanding = None
    try:
        profile = profile_call(file_path)
        sheet = next(item for item in profile.sheets if item.sheet_name == sheet_name)
        understanding = understand_sheet_structure(sheet, llm_call=llm_call)
        source_ir = None
        if understanding.verified_structure is not None:
            source_ir = build_source_ir(profile, sheet_name, understanding.verified_structure)
        return StructureCandidateResult(
            understanding_result=understanding,
            source_ir=source_ir,
        )
    except Exception as exc:  # noqa: BLE001 - candidate failure is migration evidence
        return StructureCandidateResult(
            understanding_result=understanding,
            error_type=type(exc).__name__,
            error_message=sanitize_structure_error_message(exc),
        )
