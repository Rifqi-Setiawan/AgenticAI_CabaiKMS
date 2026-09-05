"""Bounded probabilistic structure understanding over deterministic profile facts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.ingestion.structure_evidence import (
    EvidenceRequestError,
    build_initial_evidence,
    render_targeted_evidence,
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


def _messages(initial_json: str, targeted_json: str | None = None) -> list[dict[str, str]]:
    user = "Initial compact worksheet evidence:\n" + initial_json
    if targeted_json is not None:
        user += "\nTargeted evidence requested in the previous proposal:\n" + targeted_json
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
            targeted = render_targeted_evidence(sheet_profile, requested)
        except EvidenceRequestError as exc:
            proposal = _ambiguous(
                proposal,
                "INVALID_EVIDENCE_REQUEST",
                f"Requested evidence was rejected: {exc}",
            )
            break
        rounds += 1
        targeted_json = "[" + ",".join(item.model_dump_json() for item in targeted) + "]"
        proposal = invoke(
            response_model=StructureProposal,
            messages=_messages(initial, targeted_json),
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
