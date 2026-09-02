"""Fase 3f — post-mapping value normalization N(v_raw, r_i).

Rules are conservative by design: they never touch botanical meaning, only
notation. A value normalization CANNOT confidently resolve (a garbled
number/range fragment, an unrecognized-but-digit-bearing token) is left
exactly as given, with a note meant for GlobalState.error_trace — never
silently guessed. Real messy examples this was built and tested against are
catalogued in docs/PROFILING.md §1.2/§2.3.

Rules applied, in order:
1. empty tokens ("-", "NA", "null", "", whitespace-only, ...) -> None
   (the controlled empty value)
2. decimal comma -> dot, only between two digits (never touches a
   ";"-separated list or a trailing stray comma)
3. numeric range separator unified to "--" (e.g. "60 - 89 cm" -> "60--89 cm")
4. multi-value separator unified to "; " (only acts on an already-present
   ";" — never invents a split from a bare comma, which could just as
   easily be a decimal or free text)
5. whitespace runs collapsed to a single space
6. categorical values snapped to the target row's own contoh_nilai
   vocabulary (Fase 1) on a case-insensitive exact match, otherwise left
   untouched — never forced into the "closest" vocabulary word
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.agents.schema_matching.review_queue import append_error_trace
from src.schema.canonical import CanonicalRow
from src.schema.state import GlobalState

EMPTY_TOKENS = {"-", "na", "n/a", "null", "none", "kosong", "tidak ada", "tt", "-.", ""}

_DECIMAL_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
_RANGE_RE = re.compile(r"(?P<a>\d+(?:\.\d+)?)\s*[-–—]{1,2}\s*(?P<b>\d+(?:\.\d+)?)")
_WHITESPACE_RE = re.compile(r"\s+")

_CLEAN_NUMBER_RE = re.compile(r"^[±\-]?\d+(?:\.\d+)?\s*[a-zA-Z°²%]*\.?$")
_CLEAN_RANGE_RE = re.compile(r"^[±\-]?\d+(?:\.\d+)?--[±\-]?\d+(?:\.\d+)?\s*[a-zA-Z°²%]*\.?$")

# A value "looks like" a number/measurement if it's built only from digits,
# whitespace, and punctuation numbers commonly appear with (decimal point,
# dashes, quotes for stray apostrophes, comparison symbols), with at most a
# short trailing unit. Anything with substantial alphabetic content
# (color names, shape descriptions, ...) never matches this, regardless of
# any digits embedded in it (e.g. "green group 137 A") — those are
# categorical/textual values, not broken numbers, and must never be
# treated as one.
_NUMERIC_SHAPE_RE = re.compile(r"^[\d\s.,'\"˃<>=+\-–—]+[a-zA-Z°²%]{0,4}\.?$")


def _is_numeric_shaped(segment: str) -> bool:
    segment = segment.strip()
    return bool(segment) and any(ch.isdigit() for ch in segment) and bool(_NUMERIC_SHAPE_RE.match(segment))


def _is_numeric_shaped_but_unparsed(segment: str) -> bool:
    segment = segment.strip()
    if not _is_numeric_shaped(segment):
        return False
    return not (_CLEAN_NUMBER_RE.fullmatch(segment) or _CLEAN_RANGE_RE.fullmatch(segment))


@dataclass
class NormalizationResult:
    value: str | None
    changed: bool
    note: str | None = None


def _normalize_decimal_comma(text: str) -> str:
    return _DECIMAL_COMMA_RE.sub(".", text)


def _normalize_range_dash(text: str) -> str:
    return _RANGE_RE.sub(lambda m: f"{m.group('a')}--{m.group('b')}", text)


def _normalize_multi_value_separator(text: str) -> str:
    if ";" not in text:
        return text
    parts = [p.strip() for p in text.split(";") if p.strip()]
    return "; ".join(parts)


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _match_vocabulary(text: str, contoh_nilai: tuple[str, ...]) -> str | None:
    """Exact case-insensitive match against the target row's own example
    values — but only the genuinely categorical/textual ones. A
    number-shaped example (clean OR already-garbled, e.g. the template's
    own unresolved "5 1," — see docs/PROFILING.md §1.2) is never used as a
    vocabulary target: matching against it would "validate" a broken
    numeric value just because that exact garbled string already happens
    to sit in the template somewhere, which defeats the point of the
    ambiguous-value check below."""
    lowered = text.lower()
    for candidate in contoh_nilai:
        candidate_clean = candidate.strip()
        if not candidate_clean or _is_numeric_shaped(candidate_clean):
            continue
        if candidate_clean.lower() == lowered:
            return candidate_clean
    return None


def normalize(raw_value: Any, target_row: CanonicalRow) -> NormalizationResult:
    """N(v_raw, r_i) — normalize one raw cell value for one canonical row.
    Domain-dependence comes entirely through `target_row.contoh_nilai`
    (Fase 1); there is no separate per-domain rule table."""
    if raw_value is None:
        return NormalizationResult(value=None, changed=False)

    original = str(raw_value)
    text = original.strip()

    if not text or text.lower() in EMPTY_TOKENS:
        return NormalizationResult(value=None, changed=True)

    text = _normalize_decimal_comma(text)
    text = _normalize_range_dash(text)
    text = _normalize_multi_value_separator(text)
    text = _collapse_whitespace(text)

    vocab_match = _match_vocabulary(text, target_row.contoh_nilai)
    if vocab_match is not None:
        text = vocab_match

    note = None
    if vocab_match is None:
        # Check each ";"-separated segment on its own — a compound value
        # like "green group 137 B; gren group 137 A" must not be judged as
        # one blob against a bare-number regex.
        segments = text.split(";") if ";" in text else [text]
        bad_segment = next((s.strip() for s in segments if _is_numeric_shaped_but_unparsed(s)), None)
        if bad_segment is not None:
            note = (
                "nilai tidak dapat dinormalisasi dengan yakin (angka/rentang tidak "
                f"terbentuk bersih), dipertahankan apa adanya untuk baris "
                f"{target_row.id} ({target_row.label!r}): {bad_segment!r}"
            )

    return NormalizationResult(value=text, changed=(text != original), note=note)


def normalize_with_trace(
    raw_value: Any, target_row: CanonicalRow, state: GlobalState
) -> tuple[NormalizationResult, dict[str, Any]]:
    """Convenience for an orchestrator node: normalize, and if the result
    carries a note, return the GlobalState.error_trace patch for it (same
    append-don't-overwrite convention as review_queue.process_mapping).
    Returns ({}, ) — an empty patch — when there's nothing to record."""
    result = normalize(raw_value, target_row)
    patch = append_error_trace(state, result.note) if result.note else {}
    return result, patch
