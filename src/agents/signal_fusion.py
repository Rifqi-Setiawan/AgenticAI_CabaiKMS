"""Three-Way Signal Fusion Engine for Multimodal Plant Photo Alignment.

Fuses:
1. Signal 1 (Filename / Caption match)
2. Signal 2 (Dynamic Variety Registry match)
3. Signal 3 (Visual Model Classification)

Implements the rule: "Visual result wins over filename; contradictions trigger human review;
high-confidence new varieties (OTHER) route to candidate queue."
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class FusionAction(str, Enum):
    AUTO_LINK = "AUTO_LINK"
    REVIEW_MISMATCH = "REVIEW_MISMATCH"
    CANDIDATE = "CANDIDATE"
    REVIEW_UNCERTAIN = "REVIEW_UNCERTAIN"


@dataclass(frozen=True)
class FusionThresholds:
    known_threshold: float = 0.85
    other_threshold: float = 0.80


@dataclass(frozen=True)
class FusionOutcome:
    action: FusionAction
    matched_variety: str | None
    confidence: float
    reason: str
    signals_consistent: bool = True
    suggested_candidate_name: str | None = None


def _extract_known_set(registry_known: Iterable[str] | Any) -> set[str]:
    if hasattr(registry_known, "get_canonical_names"):
        return {n.lower().strip() for n in registry_known.get_canonical_names()}
    return {str(n).lower().strip() for n in registry_known}


def _is_in_registry(name: str | None, known_names: set[str]) -> bool:
    if not name:
        return False
    clean = name.lower().strip()
    if clean in known_names:
        return True
    stop_words = {"cabai", "cabe", "capsicum", "tanaman", "l", "sp"}
    tokens = set(re.findall(r"[a-z0-9]+", clean)) - stop_words
    for k in known_names:
        k_tokens = set(re.findall(r"[a-z0-9]+", k)) - stop_words
        if tokens and k_tokens and (tokens == k_tokens or tokens.issubset(k_tokens) or k_tokens.issubset(tokens)):
            return True
    return False


def _varieties_conflict(var1: str | None, var2: str | None) -> bool:
    if not var1 or not var2:
        return False
    stop_words = {"cabai", "cabe", "capsicum", "tanaman", "l", "sp"}
    toks1 = set(re.findall(r"[a-z0-9]+", var1.lower())) - stop_words
    toks2 = set(re.findall(r"[a-z0-9]+", var2.lower())) - stop_words
    return bool(toks1 and toks2 and not (toks1 & toks2))


def fuse_photo_signals(
    filename_match: str | None,
    registry_known: Iterable[str] | Any,
    visual_result: Any | None,
    thresholds: FusionThresholds | None = None,
) -> FusionOutcome:
    """Evaluate alignment across filename, registry, and visual model inference."""
    thresholds = thresholds or FusionThresholds()
    known_names = _extract_known_set(registry_known)

    if visual_result is None:
        return FusionOutcome(
            action=FusionAction.REVIEW_UNCERTAIN,
            matched_variety=None,
            confidence=0.0,
            reason="No visual classification result available",
            signals_consistent=False,
        )

    # Extract status, confidence, and matched variety from visual_result object or dict
    if isinstance(visual_result, dict):
        status = str(visual_result.get("classification_status") or "UNCERTAIN").upper()
        conf = float(visual_result.get("visual_confidence") or visual_result.get("confidence") or 0.0)
        vis_matched = visual_result.get("matched_variety")
    else:
        status = str(getattr(visual_result, "classification_status", "UNCERTAIN")).upper()
        conf = float(getattr(visual_result, "visual_confidence", getattr(visual_result, "confidence", 0.0)))
        vis_matched = getattr(visual_result, "matched_variety", None)

    # 1. UNCERTAIN status
    if status == "UNCERTAIN":
        return FusionOutcome(
            action=FusionAction.REVIEW_UNCERTAIN,
            matched_variety=None,
            confidence=conf,
            reason=f"Visual status UNCERTAIN (confidence {conf:.2f})",
            signals_consistent=True,
        )

    # 2. OTHER status (candidate detection)
    if status == "OTHER":
        if conf < thresholds.other_threshold:
            return FusionOutcome(
                action=FusionAction.REVIEW_UNCERTAIN,
                matched_variety=None,
                confidence=conf,
                reason=f"OTHER confidence {conf:.2f} below threshold {thresholds.other_threshold:.2f}",
                signals_consistent=True,
            )
        # Check if filename claims an existing registered variety
        if filename_match and _is_in_registry(filename_match, known_names):
            return FusionOutcome(
                action=FusionAction.REVIEW_MISMATCH,
                matched_variety=None,
                confidence=conf,
                reason=f"Visual classified as OTHER new variety but filename claims '{filename_match}'",
                signals_consistent=False,
            )
        return FusionOutcome(
            action=FusionAction.CANDIDATE,
            matched_variety=None,
            confidence=conf,
            reason=f"Visual classified as OTHER new variety with confidence {conf:.2f}",
            signals_consistent=True,
            suggested_candidate_name=filename_match,
        )

    # 3. KNOWN status
    if status == "KNOWN":
        if conf < thresholds.known_threshold:
            return FusionOutcome(
                action=FusionAction.REVIEW_UNCERTAIN,
                matched_variety=vis_matched,
                confidence=conf,
                reason=f"KNOWN confidence {conf:.2f} below threshold {thresholds.known_threshold:.2f}",
                signals_consistent=True,
            )

        if not vis_matched or not _is_in_registry(vis_matched, known_names):
            return FusionOutcome(
                action=FusionAction.REVIEW_MISMATCH,
                matched_variety=vis_matched,
                confidence=conf,
                reason=f"Visual matched variety '{vis_matched}' is not in registry",
                signals_consistent=False,
            )

        if filename_match and _varieties_conflict(filename_match, vis_matched):
            return FusionOutcome(
                action=FusionAction.REVIEW_MISMATCH,
                matched_variety=vis_matched,
                confidence=conf,
                reason=f"Filename hint '{filename_match}' contradicts visual result '{vis_matched}'",
                signals_consistent=False,
            )

        return FusionOutcome(
            action=FusionAction.AUTO_LINK,
            matched_variety=vis_matched,
            confidence=conf,
            reason="High-confidence visual match consistent with registry and filename",
            signals_consistent=True,
        )

    return FusionOutcome(
        action=FusionAction.REVIEW_UNCERTAIN,
        matched_variety=None,
        confidence=conf,
        reason=f"Unknown classification status '{status}'",
        signals_consistent=False,
    )
