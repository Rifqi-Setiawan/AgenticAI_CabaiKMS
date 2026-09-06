from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from src.agents.schema_matching import indexing, retrieval
from src.agents.schema_matching.exact_retrieval import (
    build_exact_index,
    canonical_representation_fingerprint,
    clear_exact_index_cache,
    retrieve_exact,
)
from src.agents.schema_matching.retrieval import SourceAttributeProfile
from src.schema.canonical import CanonicalRow, CanonicalSchema


def _schema(keys=("a", "b", "c"), *, aliases=None):
    aliases = aliases or {}
    rows = [
        CanonicalRow(
            id=f"r_{position}",
            canonical_key=key,
            label=key.upper(),
            domain="test",
            contoh_nilai=(f"example-{key}",),
            alt_labels=tuple(aliases.get(key, ())),
        )
        for position, key in enumerate(keys, start=1)
    ]
    return CanonicalSchema(
        rows=rows,
        schema_version="test-v1",
        template_hash="template-test",
        template_path=Path("synthetic.xlsx"),
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_exact_index_cache()
    yield
    clear_exact_index_cache()


def _encoder_for(schema, canonical_vectors, query_vector):
    vectors = {
        row.serialize(): vector for row, vector in zip(schema.rows, canonical_vectors)
    }

    def encode_call(texts, model_name=None):
        return [vectors.get(text, query_vector) for text in texts]

    return encode_call


def test_controlled_embeddings_rank_exactly_and_distances_ascend():
    schema = _schema()
    encode_call = _encoder_for(
        schema, [[1, 0], [0.8, 0.2], [0, 1]], [1, 0]
    )
    index = build_exact_index(schema, encode_call=encode_call)
    hits = retrieve_exact(
        SourceAttributeProfile("query"), k=3, exact_index=index, encode_call=encode_call
    )
    assert [hit.canonical_key for hit in hits] == ["a", "b", "c"]
    assert [hit.distance for hit in hits] == sorted(hit.distance for hit in hits)


def test_non_normalized_vectors_are_normalized_defensively():
    schema = _schema(("a", "b"))
    encode_call = _encoder_for(schema, [[10, 0], [1, 1]], [5, 0])
    index = build_exact_index(schema, encode_call=encode_call)
    hits = retrieve_exact(
        SourceAttributeProfile("query"), k=2, exact_index=index, encode_call=encode_call
    )
    assert [hit.canonical_key for hit in hits] == ["a", "b"]
    assert hits[0].distance == pytest.approx(0.0)


@pytest.mark.parametrize("zero_in", ["canonical", "query"])
def test_zero_vector_fails_clearly(zero_in):
    schema = _schema(("a", "b"))
    canonical = [[0, 0], [1, 0]] if zero_in == "canonical" else [[1, 0], [0, 1]]
    query = [0, 0] if zero_in == "query" else [1, 0]
    encode_call = _encoder_for(schema, canonical, query)
    if zero_in == "canonical":
        with pytest.raises(ValueError, match="zero-norm canonical"):
            build_exact_index(schema, encode_call=encode_call)
    else:
        index = build_exact_index(schema, encode_call=encode_call)
        with pytest.raises(ValueError, match="query embedding has zero norm"):
            retrieve_exact(
                SourceAttributeProfile("query"),
                k=2,
                exact_index=index,
                encode_call=encode_call,
            )


def test_ties_use_canonical_key_not_schema_position():
    schema = _schema(("zeta", "alpha"))
    encode_call = _encoder_for(schema, [[1, 0], [1, 0]], [1, 0])
    index = build_exact_index(schema, encode_call=encode_call)
    hits = retrieve_exact(
        SourceAttributeProfile("query"), k=2, exact_index=index, encode_call=encode_call
    )
    assert [hit.canonical_key for hit in hits] == ["alpha", "zeta"]
    assert [hit.row_id for hit in hits] == ["r_2", "r_1"]


def test_same_inputs_produce_equivalent_hit_sequences():
    schema = _schema()
    encode_call = _encoder_for(schema, [[1, 0], [0.5, 0.5], [0, 1]], [1, 0])
    index = build_exact_index(schema, encode_call=encode_call)
    profile = SourceAttributeProfile("query")
    first = retrieve_exact(profile, k=3, exact_index=index, encode_call=encode_call)
    second = retrieve_exact(profile, k=3, exact_index=index, encode_call=encode_call)
    assert [asdict(hit) for hit in first] == [asdict(hit) for hit in second]


def test_cache_embeds_canonical_documents_once_but_each_query_once():
    schema = _schema()
    calls = []
    base = _encoder_for(schema, [[1, 0], [0, 1], [-1, 0]], [1, 0])

    def encode_call(texts, model_name=None):
        calls.append(tuple(texts))
        return base(texts, model_name=model_name)

    first = build_exact_index(schema, encode_call=encode_call)
    second = build_exact_index(schema, encode_call=encode_call)
    assert first is second
    retrieve_exact(SourceAttributeProfile("q1"), k=3, exact_index=first, encode_call=encode_call)
    retrieve_exact(SourceAttributeProfile("q2"), k=3, exact_index=first, encode_call=encode_call)
    assert sum(len(call) == len(schema.rows) for call in calls) == 1
    assert sum(len(call) == 1 for call in calls) == 2


def test_representation_drift_changes_fingerprint_and_invalidates_cache():
    original = _schema()
    changed = _schema(aliases={"b": ("bee",)})
    calls = []

    def encode_call(texts, model_name=None):
        calls.append(tuple(texts))
        return [[1, position + 1] for position, _ in enumerate(texts)]

    assert canonical_representation_fingerprint(original) != canonical_representation_fingerprint(changed)
    build_exact_index(original, encode_call=encode_call)
    build_exact_index(changed, encode_call=encode_call)
    assert len(calls) == 2


def test_reordering_keeps_semantic_tie_order_even_when_row_ids_change():
    outcomes = []
    for schema in (_schema(("zeta", "alpha")), _schema(("alpha", "zeta"))):
        encode_call = _encoder_for(schema, [[1, 0], [1, 0]], [1, 0])
        index = build_exact_index(schema, encode_call=encode_call)
        hits = retrieve_exact(
            SourceAttributeProfile("query"), k=2, exact_index=index, encode_call=encode_call
        )
        outcomes.append([hit.canonical_key for hit in hits])
    assert outcomes == [["alpha", "zeta"], ["alpha", "zeta"]]


def test_exact_dispatch_never_touches_chroma(monkeypatch):
    schema = _schema(("a", "b", "c", "d", "e"))
    encode_call = _encoder_for(
        schema,
        [[1, 0], [0.8, 0.2], [0.5, 0.5], [0.2, 0.8], [0, 1]],
        [1, 0],
    )

    def forbidden(*args, **kwargs):
        pytest.fail("exact retrieval must not access Chroma")

    monkeypatch.setattr(retrieval, "ensure_indexed", forbidden)
    monkeypatch.setattr(indexing, "get_client", forbidden)
    monkeypatch.setattr(indexing, "get_collection", forbidden)
    hits = retrieval.retrieve(
        SourceAttributeProfile("query"),
        k=5,
        schema=schema,
        backend="exact",
        encode_call=encode_call,
    )
    assert len(hits) == 5


def test_default_dispatch_still_uses_chroma(monkeypatch):
    schema = _schema(("a", "b", "c", "d", "e"))
    calls = []

    class Collection:
        def query(self, **kwargs):
            return {
                "metadatas": [[
                    {"row_id": row.id, "label": row.label, "domain": row.domain}
                    for row in schema.rows
                ]],
                "distances": [[0.1, 0.2, 0.3, 0.4, 0.5]],
            }

    def ensure(*args, **kwargs):
        calls.append("chroma")
        return Collection()

    monkeypatch.setattr(retrieval, "ensure_indexed", ensure)
    hits = retrieval.retrieve(
        SourceAttributeProfile("query"),
        k=5,
        schema=schema,
        encode_call=lambda texts, model_name=None: [[1, 0]],
    )
    assert calls == ["chroma"]
    assert [hit.row_id for hit in hits] == ["r_1", "r_2", "r_3", "r_4", "r_5"]


@pytest.mark.parametrize("backend", ["excat", "faiss", ""])
def test_unknown_backend_is_rejected(backend):
    with pytest.raises(ValueError, match="unknown retrieval backend"):
        retrieval.retrieve(SourceAttributeProfile("query"), backend=backend)


def test_schema_smaller_than_k_fails_clearly():
    schema = _schema()
    with pytest.raises(ValueError, match="fewer than requested"):
        retrieval.retrieve(SourceAttributeProfile("query"), k=5, schema=schema)


def test_index_metadata_and_matrix_are_aligned_and_read_only():
    schema = _schema()
    encode_call = _encoder_for(schema, [[1, 0], [0, 1], [-1, 0]], [1, 0])
    index = build_exact_index(schema, encode_call=encode_call)
    assert index.row_ids == ("r_1", "r_2", "r_3")
    assert index.canonical_keys == ("a", "b", "c")
    assert index.embeddings.shape == (3, 2)
    assert not index.embeddings.flags.writeable
    with pytest.raises(ValueError):
        index.embeddings[0, 0] = 2
