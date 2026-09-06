"""Pure deterministic verification of a proposed schema mapping."""

from __future__ import annotations

from typing import Any

from src.agents.schema_matching.exact_match import (
    ExactNameResolution,
    ExactNameStatus,
    normalize_canonical_name,
)
from src.agents.schema_matching.review_queue import (
    AcceptanceStatus,
    MappingAcceptance,
)
from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping
from src.schema.mapping_verification import (
    MappingVerificationResult,
    MappingVerificationStatus,
    RetrievalEvidence,
)
from src.schema.provenance import MappingMethod


def _retrieval_evidence(
    candidates: list[RetrievalHit], target_row_id: str, schema: CanonicalSchema
) -> RetrievalEvidence:
    top1 = candidates[0] if candidates else None
    top2 = candidates[1] if len(candidates) > 1 else None
    target_rank = next(
        (rank for rank, hit in enumerate(candidates, start=1) if hit.row_id == target_row_id),
        None,
    )
    target = candidates[target_rank - 1] if target_rank is not None else None
    top1_row = schema.row_by_id(top1.row_id) if top1 is not None else None
    top2_row = schema.row_by_id(top2.row_id) if top2 is not None else None
    return RetrievalEvidence(
        candidate_count=len(candidates),
        target_in_candidates=target is not None,
        target_rank=target_rank,
        target_distance=target.distance if target is not None else None,
        top1_row_id=top1.row_id if top1 is not None else None,
        top1_canonical_key=(
            top1.canonical_key or (top1_row.canonical_key if top1_row is not None else None)
            if top1 is not None
            else None
        ),
        top1_distance=top1.distance if top1 is not None else None,
        top2_row_id=top2.row_id if top2 is not None else None,
        top2_canonical_key=(
            top2.canonical_key or (top2_row.canonical_key if top2_row is not None else None)
            if top2 is not None
            else None
        ),
        top2_distance=top2.distance if top2 is not None else None,
        top1_top2_margin=(
            top2.distance - top1.distance if top1 is not None and top2 is not None else None
        ),
        target_vs_top1_distance_gap=(
            target.distance - top1.distance if target is not None and top1 is not None else None
        ),
    )


def verify_mapping(
    *,
    profile: SourceAttributeProfile,
    mapping: SchemaMapping | None,
    mapping_method: MappingMethod,
    schema: CanonicalSchema,
    exact_resolution: ExactNameResolution,
    candidates: list[RetrievalHit] | None,
    source_format: str,
    reliability_patch: dict[str, Any] | None = None,
) -> MappingVerificationResult:
    """Collect independent evidence and enforce only deterministic invariants."""
    hard: list[str] = []
    warnings: list[str] = []
    review_signals: list[str] = []
    evidence: RetrievalEvidence | None = None

    if mapping is None:
        hard.append("MAPPING_MISSING")
    else:
        if mapping.source_format != source_format:
            hard.append("SOURCE_FORMAT_MISMATCH")
        if normalize_canonical_name(mapping.source_attribute) != normalize_canonical_name(
            profile.attribute_name
        ):
            warnings.append("SOURCE_ATTRIBUTE_MISMATCH")
            review_signals.append("SOURCE_ATTRIBUTE_MISMATCH")
        if profile.structural_context is not None:
            if mapping.source_context is None:
                warnings.append("SOURCE_CONTEXT_DROPPED")
                review_signals.append("SOURCE_CONTEXT_DROPPED")
            elif normalize_canonical_name(mapping.source_context) != normalize_canonical_name(
                profile.structural_context
            ):
                warnings.append("SOURCE_CONTEXT_MISMATCH")
                review_signals.append("SOURCE_CONTEXT_MISMATCH")

        target_row = (
            None
            if mapping.target_canonical_row == NULL_ROW
            else schema.row_by_id(mapping.target_canonical_row)
        )
        if mapping.target_canonical_row == NULL_ROW:
            warnings.append("NULL_TARGET")
            review_signals.append("NULL_TARGET")
        elif target_row is None:
            hard.append("TARGET_NOT_IN_CANONICAL_SCHEMA")

        if mapping_method == "exact_name":
            exact_consistent = (
                exact_resolution.status is ExactNameStatus.MATCH
                and mapping.target_canonical_row == exact_resolution.canonical_row_id
                and target_row is not None
                and target_row.canonical_key == exact_resolution.canonical_key
            )
            if not exact_consistent:
                hard.append("EXACT_RESOLUTION_TARGET_MISMATCH")
        elif (
            mapping_method == "retrieve_rerank"
            and mapping.target_canonical_row != NULL_ROW
        ):
            if candidates is None:
                hard.append("RETRIEVAL_CANDIDATES_MISSING")
            elif not candidates:
                hard.append("RETRIEVAL_CANDIDATES_EMPTY")
            else:
                candidate_ids = [hit.row_id for hit in candidates]
                if len(candidate_ids) != len(set(candidate_ids)):
                    hard.append("DUPLICATE_RETRIEVAL_CANDIDATE")
                else:
                    evidence = _retrieval_evidence(
                        candidates, mapping.target_canonical_row, schema
                    )
                    if not evidence.target_in_candidates:
                        hard.append("TARGET_NOT_IN_RETRIEVED_CANDIDATES")
                    elif evidence.target_rank != 1:
                        warnings.append("TARGET_NOT_RETRIEVAL_TOP1")

    if (
        exact_resolution.status is ExactNameStatus.AMBIGUOUS
        and mapping_method == "retrieve_rerank"
    ):
        warnings.append("EXACT_NAME_COLLISION_RESOLVED_SEMANTICALLY")

    trace = list((reliability_patch or {}).get("error_trace", []))
    if trace:
        warnings.append("RERANK_RELIABILITY_PATCH")
        review_signals.append("RERANK_RELIABILITY_PATCH")

    if hard:
        status = MappingVerificationStatus.REJECT
        summary = "deterministic hard invariant violation: " + ", ".join(hard)
    elif review_signals:
        status = MappingVerificationStatus.REVIEW
        summary = "soft verifier review signal(s): " + ", ".join(review_signals)
    else:
        status = MappingVerificationStatus.PASS
        summary = "no deterministic verifier violation observed"

    target = (
        schema.row_by_id(mapping.target_canonical_row)
        if mapping is not None and mapping.target_canonical_row != NULL_ROW
        else None
    )
    return MappingVerificationResult(
        status=status,
        mapping_method=mapping_method,
        source_attribute=profile.attribute_name,
        source_context=profile.structural_context,
        source_attribute_id=profile.source_attribute_id,
        proposed_target_row_id=mapping.target_canonical_row if mapping is not None else None,
        proposed_target_canonical_key=target.canonical_key if target is not None else None,
        exact_name_status=exact_resolution.status.value,
        exact_candidate_canonical_keys=list(exact_resolution.candidate_canonical_keys),
        hard_issue_codes=hard,
        warning_codes=warnings,
        retrieval_evidence=evidence,
        model_confidence=mapping.confidence if mapping is not None else None,
        recommendation_summary=summary,
    )


def combine_mapping_acceptance(
    current_acceptance: MappingAcceptance,
    verification: MappingVerificationResult,
) -> MappingAcceptance:
    """Phase 7C1 policy: hard REJECT blocks; all other legacy decisions stand."""
    if verification.status is MappingVerificationStatus.REJECT:
        return MappingAcceptance(
            AcceptanceStatus.NO_WRITE,
            "mapping verifier REJECT: " + ", ".join(verification.hard_issue_codes),
        )
    return current_acceptance
