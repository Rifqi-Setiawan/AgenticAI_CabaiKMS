"""Exhaustive cosine retrieval over the complete canonical schema.

This backend intentionally shares the Chroma backend's embedding model and
serialized canonical/query representations.  It changes only candidate
search: every canonical vector is scored in memory with exact matrix-vector
cosine similarity.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from src.agents.schema_matching.indexing import EMBEDDING_MODEL_NAME, encode
from src.schema.canonical import CanonicalSchema

EncodeCall = Callable[..., object]
_TIE_DECIMALS = 12


@dataclass(frozen=True)
class ExactCanonicalIndex:
    """Aligned, read-only metadata and normalized canonical embeddings."""

    model_name: str
    schema_version: str
    template_hash: str
    representation_fingerprint: str
    row_ids: tuple[str, ...]
    canonical_keys: tuple[str, ...]
    labels: tuple[str, ...]
    domains: tuple[str, ...]
    embeddings: NDArray[np.float64]

    def __post_init__(self) -> None:
        row_count = len(self.row_ids)
        if not (
            len(self.canonical_keys)
            == len(self.labels)
            == len(self.domains)
            == row_count
        ):
            raise ValueError("exact index metadata arrays are not aligned")
        if self.embeddings.ndim != 2 or self.embeddings.shape[0] != row_count:
            raise ValueError(
                "exact index embedding rows must align exactly with canonical metadata"
            )
        self.embeddings.setflags(write=False)


# The encoder identity is included in addition to the required semantic key so
# injected/offline encoders can never accidentally reuse production vectors.
_exact_index_cache: dict[tuple[object, ...], ExactCanonicalIndex] = {}


def canonical_representation_fingerprint(schema: CanonicalSchema) -> str:
    """SHA-256 of every embedded semantic identity in schema order."""
    source = "\n".join(
        f"{row.canonical_key}:{row.serialize()}" for row in schema.rows
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def clear_exact_index_cache() -> None:
    """Clear process-local canonical embeddings (primarily for tests)."""
    _exact_index_cache.clear()


def _call_encoder(
    encode_call: EncodeCall, texts: list[str], model_name: str
) -> object:
    """Use the existing encoder contract while permitting simple test fakes."""
    try:
        return encode_call(texts, model_name=model_name)
    except TypeError as exc:
        # Small unit-test fakes often accept only the document list. Do not
        # mask TypeErrors raised from inside a callable that supports model_name.
        if "model_name" not in str(exc):
            raise
        return encode_call(texts)


def _normalized_matrix(vectors: object, *, expected_rows: int) -> NDArray[np.float64]:
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != expected_rows:
        raise ValueError(
            f"encoder returned shape {matrix.shape}; expected ({expected_rows}, dimensions)"
        )
    if matrix.shape[1] == 0 or not np.all(np.isfinite(matrix)):
        raise ValueError("canonical embeddings must be finite, non-empty vectors")
    norms = np.linalg.norm(matrix, axis=1)
    zero_rows = np.flatnonzero(norms == 0)
    if zero_rows.size:
        raise ValueError(
            "zero-norm canonical embedding(s) at matrix row(s): "
            + ", ".join(str(int(index)) for index in zero_rows)
        )
    normalized = np.ascontiguousarray(matrix / norms[:, None], dtype=np.float64)
    normalized.setflags(write=False)
    return normalized


def _normalized_query(vector: object, *, dimensions: int) -> NDArray[np.float64]:
    query = np.asarray(vector, dtype=np.float64)
    if query.ndim == 2 and query.shape[0] == 1:
        query = query[0]
    if query.ndim != 1 or query.shape[0] != dimensions:
        raise ValueError(
            f"query embedding has shape {query.shape}; expected ({dimensions},)"
        )
    if not np.all(np.isfinite(query)):
        raise ValueError("query embedding must contain only finite values")
    norm = float(np.linalg.norm(query))
    if norm == 0:
        raise ValueError("query embedding has zero norm")
    return query / norm


def build_exact_index(
    schema: CanonicalSchema | None = None,
    *,
    model_name: str = EMBEDDING_MODEL_NAME,
    encode_call: EncodeCall = encode,
    use_cache: bool = True,
) -> ExactCanonicalIndex:
    """Embed all canonical rows in one batch and return an aligned index."""
    schema = schema or CanonicalSchema.from_template()
    if not schema.rows:
        raise ValueError("cannot build an exact index for an empty canonical schema")

    fingerprint = canonical_representation_fingerprint(schema)
    cache_key = (
        model_name,
        fingerprint,
        schema.schema_version,
        schema.template_hash,
        tuple(row.id for row in schema.rows),
        id(encode_call),
    )
    if use_cache and cache_key in _exact_index_cache:
        return _exact_index_cache[cache_key]

    documents = [row.serialize() for row in schema.rows]
    raw_embeddings = _call_encoder(encode_call, documents, model_name)
    embeddings = _normalized_matrix(raw_embeddings, expected_rows=len(schema.rows))
    index = ExactCanonicalIndex(
        model_name=model_name,
        schema_version=schema.schema_version,
        template_hash=schema.template_hash,
        representation_fingerprint=fingerprint,
        row_ids=tuple(row.id for row in schema.rows),
        canonical_keys=tuple(row.canonical_key for row in schema.rows),
        labels=tuple(row.label for row in schema.rows),
        domains=tuple(row.domain for row in schema.rows),
        embeddings=embeddings,
    )
    if use_cache:
        _exact_index_cache[cache_key] = index
    return index


def retrieve_exact(
    profile: object,
    *,
    k: int,
    exact_index: ExactCanonicalIndex,
    encode_call: EncodeCall = encode,
) -> list[object]:
    """Return exhaustive cosine-distance hits with deterministic tie order."""
    # Imported lazily to keep RetrievalHit's public home in retrieval.py
    # without introducing a module import cycle.
    from src.agents.schema_matching.retrieval import RetrievalHit

    row_count = len(exact_index.row_ids)
    if row_count < k:
        raise ValueError(
            f"canonical schema has {row_count} rows, fewer than requested k={k}"
        )
    query_text = profile.build_query()
    raw_query = _call_encoder(encode_call, [query_text], exact_index.model_name)
    query = _normalized_query(raw_query, dimensions=exact_index.embeddings.shape[1])

    similarities = np.clip(exact_index.embeddings @ query, -1.0, 1.0)
    distances = 1.0 - similarities
    # Rounding defines "near-identical" at numerical-noise scale. Semantic
    # canonical_key, never positional r_N, breaks those ties.
    order = sorted(
        range(row_count),
        key=lambda index: (
            round(float(distances[index]), _TIE_DECIMALS),
            exact_index.canonical_keys[index],
        ),
    )[:k]
    return [
        RetrievalHit(
            row_id=exact_index.row_ids[index],
            label=exact_index.labels[index],
            domain=exact_index.domains[index],
            distance=float(distances[index]),
            canonical_key=exact_index.canonical_keys[index],
        )
        for index in order
    ]
