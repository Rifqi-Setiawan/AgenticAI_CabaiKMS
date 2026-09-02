"""Reliability-wrapped entry points for the two agents that make real
network calls (schema-matching's reranker, vision classification) — this
is where retry (src/reliability/retry.py), rate limiting
(src/reliability/rate_limit.py), and the revise loop
(src/reliability/verifier.py) actually get composed around a real agent
call, and where GlobalState.error_trace ends up consistently filled at
every failure point named in the brief:

  - "link citra tak terakses"  -> safe_classify_image, image download step
  - "format tak valid"          -> the shared verify-then-revise loop
                                    (pydantic.ValidationError from either
                                    agent's constrained decoding)
  - "status UNCERTAIN"          -> safe_classify_image, post-success check
  - "atribut tak terpetakan"    -> safe_rerank, delegates to
                                    review_queue.process_mapping (Fase 3e) —
                                    not reimplemented here

A real provider call (LLMCallError / VisionCallError) is retried first —
transient network blips, momentary rate limits — via run_with_retry, INSIDE
each attempt the outer verify-then-revise loop makes. If retry exhausts
anyway (e.g. a rate limit that won't clear for a while, not just a blip),
that same exception type is also in the OUTER loop's revisable_exceptions:
without that, an exhausted retry would propagate straight out of
verify_with_revision uncaught, crashing the whole pipeline run over ONE
attribute's provider failure — confirmed the hard way against a real Groq
daily quota limit, not a hypothetical. A contract failure
(ValidationError, or classify_image's own TypeError guard) is revisable
for the same reason but for a different cause: the model produced
something structurally invalid, so asking again (not just retrying the
identical request) is the correct remedy.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.agents.schema_matching import review_queue
from src.agents.schema_matching.reranking import rerank
from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile
from src.agents.vision_classification import VarietyDescription, classify_image, download_image_bytes
from src.llm.providers import LLMCallError
from src.llm.vision_providers import VisionCallError
from src.reliability.rate_limit import RateLimiter
from src.reliability.retry import DEFAULT_BASE_DELAY, DEFAULT_MAX_ATTEMPTS, DEFAULT_MAX_DELAY, run_with_retry
from src.reliability.verifier import DEFAULT_MAX_REVISIONS, verify_with_trace
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import ImageMetadata, SchemaMapping, VisionResult
from src.schema.state import GlobalState

VISION_REVISABLE_EXCEPTIONS = (ValidationError, TypeError, VisionCallError)
SCHEMA_MATCHING_REVISABLE_EXCEPTIONS = (ValidationError, LLMCallError)


def safe_classify_image(
    image: ImageMetadata,
    knowledge_source_text: str,
    varieties: list[VarietyDescription],
    state: GlobalState,
    *,
    image_bytes: bytes | None = None,
    drive_service: Any = None,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    max_retry_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_base_delay: float = DEFAULT_BASE_DELAY,
    retry_max_delay: float = DEFAULT_MAX_DELAY,
    rate_limiter: RateLimiter | None = None,
    **classify_kwargs: Any,
) -> tuple[VisionResult | None, dict[str, Any]]:
    """Returns (result, state_patch). `result` is None whenever nothing
    usable could be produced (download failed, or the contract loop
    exhausted its revisions) — the patch always explains why in that
    case. A successful UNCERTAIN result IS returned (the caller may still
    want it) but is also flagged in the patch for review."""

    # Step 1: download — retried (transient infra), never revised (a
    # missing/inaccessible file isn't fixed by asking the model again).
    if image_bytes is None:
        try:
            image_bytes = run_with_retry(
                download_image_bytes,
                image.file_id,
                service=drive_service,
                exceptions=(Exception,),
                max_attempts=max_retry_attempts,
                base_delay=retry_base_delay,
                max_delay=retry_max_delay,
                rate_limiter=rate_limiter,
            )
        except Exception as exc:
            patch = review_queue.append_error_trace(
                state, f"link citra tak terakses (file_id={image.file_id!r}): {exc}"
            )
            return None, patch

    # Step 2: classify — transient provider errors retried; contract
    # failures revised (the model gets another shot at a valid answer).
    def _attempt() -> VisionResult:
        return run_with_retry(
            classify_image,
            image,
            knowledge_source_text,
            varieties,
            image_bytes=image_bytes,
            drive_service=drive_service,
            **classify_kwargs,
            exceptions=(VisionCallError,),
            max_attempts=max_retry_attempts,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
            rate_limiter=rate_limiter,
        )

    outcome, patch = verify_with_trace(
        _attempt,
        state,
        max_revisions=max_revisions,
        revisable_exceptions=VISION_REVISABLE_EXCEPTIONS,
        context=f"vision_classification file_id={image.file_id!r}",
    )
    if not outcome.accepted:
        return None, patch

    result = outcome.result
    if result.classification_status == "UNCERTAIN":
        uncertain_patch = review_queue.append_error_trace(
            state,
            f"status UNCERTAIN untuk file_id={image.file_id!r}: {result.visual_evidence}",
        )
        return result, uncertain_patch

    return result, {}


def safe_rerank(
    profile: SourceAttributeProfile,
    candidates: list[RetrievalHit],
    state: GlobalState,
    *,
    source_format: str,
    schema: CanonicalSchema | None = None,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    max_retry_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_base_delay: float = DEFAULT_BASE_DELAY,
    retry_max_delay: float = DEFAULT_MAX_DELAY,
    rate_limiter: RateLimiter | None = None,
    confidence_threshold: float = review_queue.DEFAULT_CONFIDENCE_THRESHOLD,
    **rerank_kwargs: Any,
) -> tuple[SchemaMapping | None, dict[str, Any]]:
    """Returns (mapping, state_patch). `mapping` is None only if the
    contract loop itself exhausted its revisions (never produced a valid
    SchemaMapping at all) — a successfully-produced but NULL/low-confidence
    mapping ("atribut tak terpetakan") IS returned, with the patch
    explaining why via review_queue.process_mapping (Fase 3e), not a
    second, competing mechanism."""

    def _attempt() -> SchemaMapping:
        return run_with_retry(
            rerank,
            profile,
            candidates,
            source_format=source_format,
            schema=schema,
            **rerank_kwargs,
            exceptions=(LLMCallError,),
            max_attempts=max_retry_attempts,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
            rate_limiter=rate_limiter,
        )

    outcome, patch = verify_with_trace(
        _attempt,
        state,
        max_revisions=max_revisions,
        revisable_exceptions=SCHEMA_MATCHING_REVISABLE_EXCEPTIONS,
        context=f"schema_matching atribut={profile.attribute_name!r}",
    )
    if not outcome.accepted:
        return None, patch

    mapping = outcome.result
    review_patch = review_queue.process_mapping(mapping, state, confidence_threshold=confidence_threshold)
    return mapping, review_patch
