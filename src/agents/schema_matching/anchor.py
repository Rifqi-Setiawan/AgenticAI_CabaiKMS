"""Fase 3d — anchor field detection ("jenis cabai" / varietas identity).

For row-oriented spreadsheets, exactly one column carries the varietas/
accession identity per observation (the "Jenis Cabai" column in
data/samples/data_input.xlsx is the running example — see
docs/PROFILING.md §2). This module finds that column by embedding each
candidate's HEADER TEXT ONLY with the same multilingual model Fase 3a/3b
use, and ranking cosine similarity against a small set of reference
phrases for the concept "varietas cabai / aksesi". If more than one
candidate clears the similarity threshold, the highest-scoring one wins —
no LLM call needed, this is a much narrower decision than schema-row
matching.

Header-only, deliberately: an earlier version blended each candidate's
sample values into the embedded text (matching Fase 3b's retrieval
pattern), but that measurably backfired here — a column like "Bentuk Buah
Cabai" (fruit shape, nothing to do with variety identity) outscored the
real anchor "Jenis Cabai" once its long list of sample values got folded
in, because the *values themselves* don't carry an "this is an identity
column" signal the embedding model can use, while the noise they add can
still shift the pooled embedding. The header name alone is a much more
direct, deliberate signal of a column's role, and was verified empirically
against both real data/samples/data_input.xlsx and the synthetic
data_input_sintetis_1.xlsx (the header-only score for "Jenis Cabai" clears
0.74 in both, with the next-highest real candidate — "Lokasi Sampling" —
around 0.64, hence DEFAULT_THRESHOLD sitting between the two).

For transposed spreadsheets, varietas identity is already the column
headers, so anchor detection is skipped entirely (`status="not_required"`).

If no candidate clears the threshold, the result is `status="escalate"` —
this module does NOT guess; wiring that into the Manual Review Queue is
Fase 3e's job (kept decoupled here on purpose).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.agents.schema_matching.indexing import EMBEDDING_MODEL_NAME, encode

ANCHOR_CONCEPT_PHRASES = [
    "variety",  # explicit English identity header, as in flat observation tables
    "varietas cabai",
    "aksesi cabai",
    "jenis cabai",
    "nama kultivar cabai",
    "accession name of chili pepper variety",
]

DEFAULT_THRESHOLD = 0.7

_concept_embedding_cache: dict[str, list[list[float]]] = {}


def _concept_embeddings(model_name: str = EMBEDDING_MODEL_NAME) -> list[list[float]]:
    if model_name not in _concept_embedding_cache:
        _concept_embedding_cache[model_name] = encode(ANCHOR_CONCEPT_PHRASES, model_name=model_name)
    return _concept_embedding_cache[model_name]


def _cosine(a: list[float], b: list[float]) -> float:
    # embeddings from indexing.encode() are already unit-normalized, so
    # cosine similarity is just the dot product.
    return sum(x * y for x, y in zip(a, b))


@dataclass
class AnchorCandidate:
    column_name: str
    # Kept for API/call-site compatibility and for a human reviewing an
    # AnchorResult's reasoning, but NOT used in scoring — see the module
    # docstring for why sample values measurably hurt this decision.
    sample_values: list[str] = field(default_factory=list)


@dataclass
class AnchorResult:
    status: Literal["found", "not_required", "escalate"]
    column_name: str | None
    similarity: float | None
    reason: str


def detect_anchor(
    candidates: list[AnchorCandidate],
    *,
    source_format: Literal["transposed", "row-oriented"],
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = EMBEDDING_MODEL_NAME,
) -> AnchorResult:
    if source_format == "transposed":
        return AnchorResult(
            status="not_required",
            column_name=None,
            similarity=None,
            reason="varietas sudah menjadi header kolom pada format transposed; anchor tidak diperlukan",
        )

    if not candidates:
        return AnchorResult(
            status="escalate",
            column_name=None,
            similarity=None,
            reason="tidak ada kolom kandidat untuk dievaluasi",
        )

    concept_embeddings = _concept_embeddings(model_name)
    candidate_embeddings = encode([c.column_name for c in candidates], model_name=model_name)

    scored = [
        (candidate, max(_cosine(emb, concept) for concept in concept_embeddings))
        for candidate, emb in zip(candidates, candidate_embeddings)
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    best_candidate, best_score = scored[0]

    if best_score < threshold:
        return AnchorResult(
            status="escalate",
            column_name=None,
            similarity=best_score,
            reason=(
                f"tidak ada kandidat anchor eksplisit di atas ambang {threshold} "
                f'(tertinggi: "{best_candidate.column_name}"={best_score:.3f}) — jangan menebak'
            ),
        )

    return AnchorResult(
        status="found",
        column_name=best_candidate.column_name,
        similarity=best_score,
        reason="kemiripan tertinggi terhadap konsep 'varietas cabai / aksesi'",
    )
