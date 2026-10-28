"""Deterministic, fail-closed canonical label and curated-alias resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from src.schema.canonical import CanonicalRow, CanonicalSchema
from src.schema.contracts import SchemaMapping


class ExactNameStatus(str, Enum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ExactNameResolution:
    status: ExactNameStatus
    normalized_source_name: str
    canonical_row_id: str | None = None
    canonical_key: str | None = None
    matched_name: str | None = None
    matched_name_type: Literal["label", "alias"] | None = None
    candidate_row_ids: tuple[str, ...] = ()
    candidate_canonical_keys: tuple[str, ...] = ()


def normalize_canonical_name(value: str) -> str:
    """Collapse whitespace and casefold; deliberately perform no fuzzy cleanup."""
    return " ".join(value.split()).casefold()


def _matching_name(row: CanonicalRow, normalized_name: str) -> tuple[str, str] | None:
    if normalize_canonical_name(row.label) == normalized_name:
        return row.label, "label"
    for alias in row.alt_labels:
        if normalize_canonical_name(alias) == normalized_name:
            return alias, "alias"
    return None


def build_normalized_name_index(
    schema: CanonicalSchema,
) -> dict[str, tuple[CanonicalRow, ...]]:
    """Map each normalized explicit name to every distinct owning row."""
    buckets: dict[str, list[CanonicalRow]] = {}
    for row in schema.rows:
        names_seen_for_row: set[str] = set()
        for name in (row.label, *row.alt_labels):
            normalized_name = normalize_canonical_name(name)
            if normalized_name in names_seen_for_row:
                continue
            names_seen_for_row.add(normalized_name)
            buckets.setdefault(normalized_name, []).append(row)
    return {
        name: tuple(sorted(rows, key=lambda row: row.canonical_key))
        for name, rows in buckets.items()
    }


def resolve_exact_name(
    attribute_name: str, schema: CanonicalSchema
) -> ExactNameResolution:
    """Resolve a leaf name only when exactly one canonical row owns it."""
    normalized_name = normalize_canonical_name(attribute_name)
    matches: list[tuple[CanonicalRow, str, str]] = []
    for row in build_normalized_name_index(schema).get(normalized_name, ()):
        matched = _matching_name(row, normalized_name)
        if matched is not None:
            matches.append((row, matched[0], matched[1]))

    # Stable semantic order makes collision diagnostics independent of template
    # position. Duplicate label/alias spellings within one row were already
    # collapsed because each row contributes at most one entry above.
    candidate_row_ids = tuple(item[0].id for item in matches)
    candidate_keys = tuple(item[0].canonical_key for item in matches)

    if not matches:
        return ExactNameResolution(
            status=ExactNameStatus.NO_MATCH,
            normalized_source_name=normalized_name,
        )
    if len(matches) > 1:
        return ExactNameResolution(
            status=ExactNameStatus.AMBIGUOUS,
            normalized_source_name=normalized_name,
            candidate_row_ids=candidate_row_ids,
            candidate_canonical_keys=candidate_keys,
        )

    row, matched_name, matched_name_type = matches[0]
    return ExactNameResolution(
        status=ExactNameStatus.MATCH,
        normalized_source_name=normalized_name,
        canonical_row_id=row.id,
        canonical_key=row.canonical_key,
        matched_name=matched_name,
        matched_name_type=matched_name_type,
        candidate_row_ids=candidate_row_ids,
        candidate_canonical_keys=candidate_keys,
    )


def mapping_from_exact_resolution(
    resolution: ExactNameResolution,
    *,
    source_attribute: str,
    source_context: str | None,
    source_format: str,
) -> SchemaMapping:
    if resolution.status is not ExactNameStatus.MATCH or resolution.canonical_row_id is None:
        raise ValueError("an exact SchemaMapping requires a unique MATCH resolution")
    name_kind = "label kanonik" if resolution.matched_name_type == "label" else "alias terkurasi"
    return SchemaMapping(
        source_attribute=source_attribute,
        source_context=source_context,
        source_format=source_format,
        target_canonical_row=resolution.canonical_row_id,
        confidence=1.0,
        reasoning=f"Nama atribut cocok persis dengan {name_kind}.",
        normalization_required=True,
    )
