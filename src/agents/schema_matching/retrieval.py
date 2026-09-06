"""Fase 3b — retrieve top-k canonical row candidates for one source
spreadsheet attribute (a column header in row-oriented data, or a row label
in transposed data).

The query embeds attribute name + structural context + up to 10 sample
values + a heuristically detected data type, using the same model/collection
Fase 3a built. Retrieval quality depends on this richer query: a bare label
alone is not reliably nearest-neighbor to its own canonical row, because the
indexed documents (Fase 1's repr(), including long contoh_nilai lists) pool
into embeddings that a short query doesn't match well. Real attribute
profiles — name + real sample values + type — do match well; validated
empirically against data/samples/ before writing this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from src.agents.schema_matching.indexing import (
    DEFAULT_CHROMA_DIR,
    EMBEDDING_MODEL_NAME,
    encode,
    ensure_indexed,
)
from src.schema.canonical import SEPARATOR, CanonicalSchema

DataType = Literal["numerik", "kategorik", "tekstual"]

MIN_K = 5
MAX_K = 10
DEFAULT_K = 8

MAX_SAMPLE_VALUES = 10

# A number, optionally signed/approx (±), optionally a "a - b" or "a-b"
# range, optionally with a unit suffix (cm, cm², %, °C, ...). Decimal comma
# or dot both accepted, matching the messy-value patterns catalogued in
# docs/PROFILING.md.
_NUMERIC_RE = re.compile(
    r"^\s*[±]?\s*\d+([.,]\d+)?\s*(-{1,2}\s*\d+([.,]\d+)?)?\s*[a-zA-Z°²%]*\s*\.?\s*$"
)


def detect_data_type(sample_values: list[str]) -> DataType:
    """Heuristic, not a guarantee — good enough to steer the retrieval
    query, not a validated type system."""
    values = [str(v).strip() for v in sample_values if v is not None and str(v).strip()]
    if not values:
        return "tekstual"

    numeric_like = sum(1 for v in values if _NUMERIC_RE.match(v))
    if numeric_like / len(values) >= 0.6:
        return "numerik"

    # Categorical values are drawn from a small vocabulary AND look like
    # short tokens/phrases — distinct-count alone misfires on a handful of
    # free-text values (e.g. 3 different address strings has distinct == 3
    # too, same as 3 different short category words).
    avg_len = sum(len(v) for v in values) / len(values)
    distinct = len({v.lower() for v in values})
    if avg_len <= 20 and distinct <= max(2, len(values) // 2):
        return "kategorik"

    return "tekstual"


@dataclass
class SourceAttributeProfile:
    """Everything Fase 3b needs about one source attribute to build a
    retrieval query. `attribute_name` is the column header (row-oriented) or
    row label (transposed); `structural_context` is a parent/sub-header if
    the source has one (e.g. a merged section header above the real header
    row — see docs/PROFILING.md §2.2)."""

    attribute_name: str
    structural_context: str | None = None
    sample_values: list[str] = field(default_factory=list)
    data_type: DataType | None = None

    def __post_init__(self) -> None:
        self.sample_values = [str(v) for v in self.sample_values][:MAX_SAMPLE_VALUES]
        if self.data_type is None:
            self.data_type = detect_data_type(self.sample_values)

    def build_query(self) -> str:
        parts = [self.attribute_name]
        if self.structural_context:
            parts.append(self.structural_context)
        if self.sample_values:
            parts.append(", ".join(self.sample_values))
        parts.append(f"tipe data: {self.data_type}")
        return SEPARATOR.join(parts)


@dataclass
class RetrievalHit:
    row_id: str
    label: str
    domain: str
    distance: float
    canonical_key: str | None = None


RetrievalBackend = Literal["chroma", "exact"]
SUPPORTED_RETRIEVAL_BACKENDS = frozenset({"chroma", "exact"})


def validate_retrieval_backend(backend: str) -> None:
    if backend not in SUPPORTED_RETRIEVAL_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_RETRIEVAL_BACKENDS))
        raise ValueError(
            f"unknown retrieval backend {backend!r}; expected one of: {supported}"
        )


def retrieve(
    profile: SourceAttributeProfile,
    *,
    k: int = DEFAULT_K,
    schema: CanonicalSchema | None = None,
    client: object | None = None,
    persist_dir: object = DEFAULT_CHROMA_DIR,
    model_name: str = EMBEDDING_MODEL_NAME,
    backend: RetrievalBackend = "chroma",
    exact_index: object | None = None,
    encode_call: object = encode,
) -> list[RetrievalHit]:
    """Top-k canonical row candidates for `profile`, nearest first (cosine
    distance, ascending)."""
    validate_retrieval_backend(backend)
    if not (MIN_K <= k <= MAX_K):
        raise ValueError(f"k must be between {MIN_K} and {MAX_K}, got {k}")

    schema = schema or CanonicalSchema.from_template()
    if len(schema.rows) < k:
        raise ValueError(
            f"canonical schema has {len(schema.rows)} rows, fewer than requested k={k}"
        )

    if backend == "exact":
        from src.agents.schema_matching.exact_retrieval import (
            ExactCanonicalIndex,
            build_exact_index,
            retrieve_exact,
        )

        if exact_index is None:
            exact_index = build_exact_index(
                schema, model_name=model_name, encode_call=encode_call
            )
        if not isinstance(exact_index, ExactCanonicalIndex):
            raise TypeError("exact_index must be an ExactCanonicalIndex")
        from src.agents.schema_matching.exact_retrieval import (
            canonical_representation_fingerprint,
        )

        expected_fingerprint = canonical_representation_fingerprint(schema)
        if exact_index.representation_fingerprint != expected_fingerprint:
            raise ValueError("exact_index does not match the supplied canonical schema")
        if exact_index.row_ids != tuple(row.id for row in schema.rows):
            raise ValueError("exact_index row ids do not align with the supplied schema")
        if exact_index.canonical_keys != tuple(row.canonical_key for row in schema.rows):
            raise ValueError("exact_index canonical keys do not align with the supplied schema")
        if exact_index.model_name != model_name:
            raise ValueError(
                "exact_index model does not match the requested embedding model"
            )
        return retrieve_exact(
            profile, k=k, exact_index=exact_index, encode_call=encode_call
        )

    # Explicit branch after validation: exact mode cannot reach Chroma.
    collection = ensure_indexed(schema, client=client, persist_dir=persist_dir, model_name=model_name)

    query_embedding = encode_call([profile.build_query()], model_name=model_name)
    result = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
        include=["metadatas", "distances"],
    )

    return [
        RetrievalHit(row_id=meta["row_id"], label=meta["label"], domain=meta["domain"], distance=dist)
        for meta, dist in zip(result["metadatas"][0], result["distances"][0])
    ]
