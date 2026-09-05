"""Bounded probabilistic structure understanding over deterministic profile facts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.ingestion.structure_evidence import (
    EvidenceRequestError,
    MAX_TOTAL_TARGETED_CELLS,
    build_initial_evidence,
    render_targeted_evidence,
    validate_requested_ranges,
)
from src.ingestion.structure_verifier import verify_structure
from src.ingestion.workbook_profiler import SheetProfile
from src.llm.providers import call_with_fallback
from src.schema.structure import (
    StructureProposal,
    StructureStatus,
    StructureUnderstandingResult,
    VerifiedStructure,
)

MAX_EVIDENCE_ROUNDS = 2

SYSTEM_PROMPT = """You classify one worksheet's physical table structure from observed facts.
Return only the constrained StructureProposal. Supported orientations are exactly row-oriented
and transposed. Do not invent cell values or normalized labels. For a RESOLVED proposal, cite
source coordinates. If evidence is insufficient, request only specific bounded Excel ranges with
NEED_MORE_EVIDENCE. AMBIGUOUS and UNSUPPORTED are valid abstentions. Give compact reason_codes
and evidence_summary; do not provide chain-of-thought."""

LLMCall = Callable[..., StructureProposal]


def _messages(initial_json: str, targeted_rounds: list[str] | None = None) -> list[dict[str, str]]:
    user = "Initial compact worksheet evidence:\n" + initial_json
    for index, targeted_json in enumerate(targeted_rounds or [], start=1):
        user += f"\nTargeted evidence round {index}:\n{targeted_json}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _ambiguous(proposal: StructureProposal, code: str, summary: str) -> StructureProposal:
    return StructureProposal(
        status=StructureStatus.AMBIGUOUS,
        confidence=proposal.confidence,
        reason_codes=[*proposal.reason_codes, code],
        evidence_summary=summary,
    )


def understand_sheet_structure(
    sheet_profile: SheetProfile,
    *,
    llm_call: LLMCall | None = None,
) -> StructureUnderstandingResult:
    """Propose then deterministically verify one sheet, with bounded evidence seeking."""
    invoke: Callable[..., Any] = llm_call or call_with_fallback
    initial = build_initial_evidence(sheet_profile).model_dump_json()
    proposal = invoke(response_model=StructureProposal, messages=_messages(initial))
    history: list[list[str]] = []
    targeted_rounds: list[str] = []
    seen_normalized_ranges: set[str] = set()
    total_targeted_cells = 0
    rounds = 0

    while proposal.status is StructureStatus.NEED_MORE_EVIDENCE:
        if rounds >= MAX_EVIDENCE_ROUNDS:
            proposal = _ambiguous(
                proposal,
                "EVIDENCE_ROUND_LIMIT",
                f"Structure remained unresolved after {MAX_EVIDENCE_ROUNDS} targeted evidence rounds.",
            )
            break
        requested = list(proposal.requested_ranges)
        history.append(requested)
        try:
            validated = validate_requested_ranges(sheet_profile, requested)
        except EvidenceRequestError as exc:
            proposal = _ambiguous(
                proposal,
                "INVALID_EVIDENCE_REQUEST",
                f"Requested evidence was rejected: {exc}",
            )
            break
        normalized_ranges = [bounds.coordinate for _, bounds in validated]
        if (
            len(normalized_ranges) != len(set(normalized_ranges))
            or any(item in seen_normalized_ranges for item in normalized_ranges)
        ):
            proposal = _ambiguous(
                proposal,
                "DUPLICATE_EVIDENCE_REQUEST",
                "Requested evidence repeats an already acquired normalized range.",
            )
            break
        requested_cell_count = sum(bounds.cell_count for _, bounds in validated)
        if total_targeted_cells + requested_cell_count > MAX_TOTAL_TARGETED_CELLS:
            proposal = _ambiguous(
                proposal,
                "EVIDENCE_BUDGET_EXCEEDED",
                f"Cumulative targeted evidence would exceed {MAX_TOTAL_TARGETED_CELLS} cells.",
            )
            break
        targeted = render_targeted_evidence(sheet_profile, requested)
        seen_normalized_ranges.update(normalized_ranges)
        total_targeted_cells += requested_cell_count
        rounds += 1
        targeted_json = "[" + ",".join(item.model_dump_json() for item in targeted) + "]"
        targeted_rounds.append(targeted_json)
        proposal = invoke(
            response_model=StructureProposal,
            messages=_messages(initial, targeted_rounds),
        )

    if proposal.status is not StructureStatus.RESOLVED:
        return StructureUnderstandingResult(
            final_proposal=proposal,
            evidence_rounds=rounds,
            requested_ranges_history=history,
        )

    verification = verify_structure(sheet_profile, proposal)
    verified = (
        VerifiedStructure(proposal=proposal, verification=verification)
        if verification.valid
        else None
    )
    return StructureUnderstandingResult(
        final_proposal=proposal,
        verification=verification,
        verified_structure=verified,
        evidence_rounds=rounds,
        requested_ranges_history=history,
    )
