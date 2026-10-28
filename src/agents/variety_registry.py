"""Dynamic Variety Registry for Vision Classification and Entity Grounding.

Merges known plant varieties from the current run spreadsheet and committed
database knowledge documents, providing alias resolution and deterministic
matching against image filenames and captions.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable


STOP_WORDS = {
    "cabai",
    "cabe",
    "chili",
    "pepper",
    "capsicum",
    "annuum",
    "frutescens",
    "chinense",
    "tanaman",
    "foto",
    "daun",
    "buah",
    "batang",
    "bunga",
    "sample",
    "lokasi",
    "sp",
    "l",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "dsc",
}


def normalize_variety_tokens(text: str) -> list[str]:
    """Tokenize and filter stop words from text."""
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def normalize_clean_string(text: str) -> str:
    """Normalize text into a unified string without stop words."""
    tokens = normalize_variety_tokens(text)
    return " ".join(tokens)


_FILENAME_NOISE = {"img", "image", "pic", "photo", "foto", "dsc", "dscn", "p"}


def exact_comparison_tokens(text: str) -> frozenset[str]:
    """Tokens used to decide whether a filename names a variety EXACTLY.

    Indices (digits only), camera prefixes (IMG/DSC...), plant-part words and generic
    words (cabai/cabe) never discriminate between varieties, so they are ignored.
    A discriminating alphabetic token (e.g. "merah") keeps the match non-exact.
    """
    return frozenset(
        t for t in normalize_variety_tokens(text)
        if not t.isdigit() and t not in _FILENAME_NOISE
    )


@dataclass(frozen=True)
class VarietyEntry:
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    morphology: dict[str, Any] = field(default_factory=dict)
    source: str = "spreadsheet"  # "spreadsheet", "db", "both"


@dataclass(frozen=True)
class VarietyMatchResult:
    canonical_name: str
    score: float
    reason: str
    is_exact: bool = False


class VarietyRegistry:
    def __init__(self, entries: dict[str, VarietyEntry] | None = None):
        self._entries: dict[str, VarietyEntry] = entries or {}

    def get_canonical_names(self) -> list[str]:
        """Return list of canonical variety names sorted deterministically."""
        return sorted(self._entries.keys())

    def get_entry(self, name: str) -> VarietyEntry | None:
        """Retrieve entry by canonical name (case-insensitive)."""
        for k, v in self._entries.items():
            if k.lower() == name.lower():
                return v
        return None

    @classmethod
    def build(
        cls,
        spreadsheet_varieties: Iterable[str | dict[str, Any]] | None = None,
        db_varieties: Iterable[str | dict[str, Any]] | None = None,
    ) -> VarietyRegistry:
        """Build registry by merging spreadsheet and database variety definitions."""
        entries: dict[str, VarietyEntry] = {}

        def _extract_name_aliases(item: str | dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
            if isinstance(item, str):
                return item.strip(), [], {}
            if isinstance(item, dict):
                name = item.get("label") or item.get("name") or item.get("canonical_name") or item.get("id") or ""
                aliases = list(item.get("aliases") or [])
                morph = dict(item.get("morphology") or {})
                return str(name).strip(), [str(a).strip() for a in aliases if a], morph
            return "", [], {}

        # 1. Process spreadsheet varieties
        if spreadsheet_varieties:
            for item in spreadsheet_varieties:
                name, aliases, morph = _extract_name_aliases(item)
                if not name:
                    continue
                entries[name] = VarietyEntry(
                    canonical_name=name,
                    aliases=sorted(set(aliases)),
                    morphology=morph,
                    source="spreadsheet",
                )

        # 2. Process database varieties
        if db_varieties:
            for item in db_varieties:
                name, aliases, morph = _extract_name_aliases(item)
                if not name:
                    continue
                if name in entries:
                    existing = entries[name]
                    combined_aliases = sorted(set(existing.aliases + aliases))
                    combined_morph = {**existing.morphology, **morph}
                    entries[name] = VarietyEntry(
                        canonical_name=name,
                        aliases=combined_aliases,
                        morphology=combined_morph,
                        source="both",
                    )
                else:
                    entries[name] = VarietyEntry(
                        canonical_name=name,
                        aliases=sorted(set(aliases)),
                        morphology=morph,
                        source="db",
                    )

        return cls(entries)

    def match(self, text: str, threshold: float = 0.6) -> list[VarietyMatchResult]:
        """Match query text against registered varieties deterministically."""
        cleaned_query = normalize_clean_string(text)
        query_tokens = set(normalize_variety_tokens(text))
        lowered_text = text.lower()

        results: list[VarietyMatchResult] = []

        for name, entry in sorted(self._entries.items()):
            cleaned_canonical = normalize_clean_string(name)
            canonical_tokens = set(normalize_variety_tokens(name))

            exact_query_tokens = exact_comparison_tokens(text)
            exact_canon_tokens = exact_comparison_tokens(name)
            is_exact_canonical = bool(exact_canon_tokens and exact_query_tokens == exact_canon_tokens)

            # 1. Check exact canonical match or token subset match
            if is_exact_canonical:
                results.append(VarietyMatchResult(canonical_name=name, score=1.0, reason="Exact canonical name match", is_exact=True))
                continue
            if cleaned_canonical and cleaned_canonical in cleaned_query:
                results.append(VarietyMatchResult(canonical_name=name, score=0.96, reason="Substring canonical match", is_exact=False))
                continue
            if canonical_tokens and canonical_tokens.issubset(query_tokens):
                results.append(VarietyMatchResult(canonical_name=name, score=0.95, reason="Canonical token subset match", is_exact=False))
                continue

            # 2. Check alias matches
            matched_alias = None
            alias_score = 0.0
            alias_exact = False
            for alias in entry.aliases:
                cleaned_alias = normalize_clean_string(alias)
                alias_tokens = set(normalize_variety_tokens(alias))
                exact_alias_tokens = exact_comparison_tokens(alias)

                if exact_alias_tokens and exact_query_tokens == exact_alias_tokens:
                    matched_alias = alias
                    alias_score = 0.98
                    alias_exact = True
                    break
                if cleaned_alias and (cleaned_alias in cleaned_query or alias.lower() in lowered_text):
                    matched_alias = alias
                    alias_score = 0.95
                    alias_exact = False
                    break
                if alias_tokens and alias_tokens.issubset(query_tokens):
                    matched_alias = alias
                    alias_score = 0.90
                    alias_exact = False
                    break

            if matched_alias:
                results.append(VarietyMatchResult(canonical_name=name, score=alias_score, reason=f"Matched alias '{matched_alias}'", is_exact=alias_exact))
                continue

            # 3. Fuzzy matching against canonical name and aliases
            if cleaned_query and cleaned_canonical:
                sim = difflib.SequenceMatcher(None, cleaned_query, cleaned_canonical).ratio()
                if sim >= threshold:
                    results.append(VarietyMatchResult(canonical_name=name, score=round(sim, 3), reason=f"Fuzzy canonical match ({sim:.2f})", is_exact=False))
                    continue

            for alias in entry.aliases:
                c_alias = normalize_clean_string(alias)
                if cleaned_query and c_alias:
                    sim = difflib.SequenceMatcher(None, cleaned_query, c_alias).ratio()
                    if sim >= threshold:
                        results.append(VarietyMatchResult(canonical_name=name, score=round(sim, 3), reason=f"Fuzzy alias match '{alias}' ({sim:.2f})", is_exact=False))
                        break

        # Deterministic sort: score descending, then canonical_name ascending
        results.sort(key=lambda r: (-r.score, r.canonical_name))
        return results

    def best_match(self, text: str, threshold: float = 0.6) -> VarietyMatchResult | None:
        """Return top match above threshold or None."""
        matches = self.match(text, threshold=threshold)
        return matches[0] if matches else None
