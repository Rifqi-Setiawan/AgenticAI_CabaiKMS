"""Diagnostic ANN-versus-exact retrieval comparison (never a pipeline gate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.agents.schema_matching.exact_retrieval import (
    ExactCanonicalIndex,
    build_exact_index,
)
from src.agents.schema_matching.indexing import (
    DEFAULT_CHROMA_DIR,
    EMBEDDING_MODEL_NAME,
    encode,
)
from src.agents.schema_matching.retrieval import (
    DEFAULT_K,
    SourceAttributeProfile,
    retrieve,
)
from src.schema.canonical import CanonicalSchema


@dataclass(frozen=True)
class RetrievalBackendComparison:
    chroma_row_ids: tuple[str, ...]
    exact_row_ids: tuple[str, ...]
    intersection_count: int
    overlap_at_k: float
    same_top1: bool
    exact_only: tuple[str, ...]
    chroma_only: tuple[str, ...]
    chroma_ranks: dict[str, int]
    exact_ranks: dict[str, int]
    expected_row_id: str | None = None
    chroma_expected_hit_at_k: bool | None = None
    exact_expected_hit_at_k: bool | None = None


def compare_retrieval_backends(
    profile: SourceAttributeProfile,
    *,
    schema: CanonicalSchema | None = None,
    k: int = DEFAULT_K,
    exact_index: ExactCanonicalIndex | None = None,
    client: object | None = None,
    persist_dir: object = DEFAULT_CHROMA_DIR,
    model_name: str = EMBEDDING_MODEL_NAME,
    encode_call: Callable[..., object] = encode,
    expected_row_id: str | None = None,
) -> RetrievalBackendComparison:
    """Compare candidate sets only; agreement is not correctness evidence."""
    schema = schema or CanonicalSchema.from_template()
    exact_index = exact_index or build_exact_index(
        schema, model_name=model_name, encode_call=encode_call
    )
    chroma = retrieve(
        profile,
        k=k,
        schema=schema,
        client=client,
        persist_dir=persist_dir,
        model_name=model_name,
        encode_call=encode_call,
        backend="chroma",
    )
    exact = retrieve(
        profile,
        k=k,
        schema=schema,
        model_name=model_name,
        encode_call=encode_call,
        backend="exact",
        exact_index=exact_index,
    )

    chroma_ids = tuple(hit.row_id for hit in chroma)
    exact_ids = tuple(hit.row_id for hit in exact)
    intersection = set(chroma_ids) & set(exact_ids)
    expected_known = expected_row_id is not None
    return RetrievalBackendComparison(
        chroma_row_ids=chroma_ids,
        exact_row_ids=exact_ids,
        intersection_count=len(intersection),
        overlap_at_k=len(intersection) / k,
        same_top1=bool(chroma_ids and exact_ids and chroma_ids[0] == exact_ids[0]),
        exact_only=tuple(row_id for row_id in exact_ids if row_id not in intersection),
        chroma_only=tuple(row_id for row_id in chroma_ids if row_id not in intersection),
        chroma_ranks={row_id: rank for rank, row_id in enumerate(chroma_ids, start=1)},
        exact_ranks={row_id: rank for rank, row_id in enumerate(exact_ids, start=1)},
        expected_row_id=expected_row_id,
        chroma_expected_hit_at_k=(expected_row_id in chroma_ids) if expected_known else None,
        exact_expected_hit_at_k=(expected_row_id in exact_ids) if expected_known else None,
    )
