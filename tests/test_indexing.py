from __future__ import annotations

import dataclasses

import pytest

from src.agents.schema_matching import indexing
from src.schema.canonical import CanonicalSchema

pytestmark = pytest.mark.indexing  # needs network on first run (HF model download)


@pytest.fixture(scope="module")
def schema() -> CanonicalSchema:
    return CanonicalSchema.from_template()


@pytest.fixture
def client(tmp_path):
    return indexing.get_client(tmp_path)


class TestEnsureIndexed:
    def test_collection_has_n_vectors(self, schema, client):
        collection = indexing.ensure_indexed(schema, client=client)
        assert collection.count() == len(schema.rows)

    def test_metadata_carries_row_id_and_domain(self, schema, client):
        collection = indexing.ensure_indexed(schema, client=client)
        stored = collection.get(include=["metadatas"])
        by_id = dict(zip(stored["ids"], stored["metadatas"]))
        for row in schema.rows:
            assert by_id[row.id]["row_id"] == row.id
            assert by_id[row.id]["domain"] == row.domain

    @pytest.mark.parametrize("row_id", ["r_1", "r_7", "r_23", "r_45", "r_56", "r_60"])
    def test_trivial_self_query_returns_the_same_row(self, schema, client, row_id):
        """The plumbing sanity check: querying with a row's own repr() must
        retrieve that row as the top hit — this is the "query trivial" from
        the spec. Retrieval *quality* for realistic, much shorter source
        attribute queries is Fase 3b's job, not this one; a bare 2-3 word
        label query against these example-heavy documents is not reliably
        nearest-neighbor to its own row (long contoh_nilai tails dominate
        the pooled embedding) — Fase 3b's richer query construction is what
        addresses that, not the indexing step itself."""
        collection = indexing.ensure_indexed(schema, client=client)
        row = schema.row_by_id(row_id)
        query_embedding = indexing.encode([row.serialize()])
        result = collection.query(query_embeddings=query_embedding, n_results=1)
        assert result["ids"][0][0] == row_id

    def test_second_call_is_a_noop_when_unchanged(self, schema, client, monkeypatch):
        indexing.ensure_indexed(schema, client=client)

        calls = []
        original_encode = indexing.encode

        def spy_encode(texts, model_name=indexing.EMBEDDING_MODEL_NAME):
            calls.append(texts)
            return original_encode(texts, model_name=model_name)

        monkeypatch.setattr(indexing, "encode", spy_encode)
        indexing.ensure_indexed(schema, client=client)
        assert calls == []  # no re-embedding happened

    def test_force_reembeds_even_when_unchanged(self, schema, client, monkeypatch):
        indexing.ensure_indexed(schema, client=client)

        calls = []
        original_encode = indexing.encode

        def spy_encode(texts, model_name=indexing.EMBEDDING_MODEL_NAME):
            calls.append(texts)
            return original_encode(texts, model_name=model_name)

        monkeypatch.setattr(indexing, "encode", spy_encode)
        collection = indexing.ensure_indexed(schema, client=client, force=True)
        assert len(calls) == 1
        assert collection.count() == len(schema.rows)

    def test_rebuilds_automatically_when_template_has_drifted(self, schema, client):
        indexing.ensure_indexed(schema, client=client)

        drifted = dataclasses.replace(
            schema,
            rows=schema.rows[:5],
            template_hash="synthetic-different-hash-for-test",
        )
        collection = indexing.ensure_indexed(drifted, client=client)

        assert collection.count() == 5
        stored_ids = set(collection.get(include=[])["ids"])
        assert stored_ids == {row.id for row in drifted.rows}
        # stale ids from the pre-drift (60-row) template must be gone, not
        # left behind as orphans
        assert "r_60" not in stored_ids
