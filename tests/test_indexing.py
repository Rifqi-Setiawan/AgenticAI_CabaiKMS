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

    def test_model_change_recreates_collection_with_new_dimension(self, schema, client, monkeypatch):
        """D22: vectors from another model (different space and dimension) must not be reused,
        and chromadb cannot upsert a new dimension into an existing collection."""
        dims = {"fake-a": 3, "fake-b": 5}

        def fake_encode(texts, model_name=indexing.EMBEDDING_MODEL_NAME):
            d = dims[model_name]
            return [[1.0 if j == i % d else 0.0 for j in range(d)] for i, _ in enumerate(texts)]

        monkeypatch.setattr(indexing, "encode", fake_encode)
        first = indexing.ensure_indexed(schema, client=client, model_name="fake-a")
        assert first.metadata["embedding_model"] == "fake-a"
        assert not indexing._is_up_to_date(first, schema, "fake-b")

        second = indexing.ensure_indexed(schema, client=client, model_name="fake-b")
        assert second.count() == len(schema.rows)
        assert second.metadata["embedding_model"] == "fake-b"
        stored = second.get(include=["embeddings"])
        assert len(stored["embeddings"][0]) == 5

    def test_collection_without_recorded_model_is_rebuilt(self, schema, client, monkeypatch):
        monkeypatch.setattr(indexing, "encode", lambda texts, model_name=None: [[1.0, 0.0]] * len(texts))
        col = indexing.ensure_indexed(schema, client=client, model_name="fake-a")
        meta = {k: v for k, v in col.metadata.items() if k not in ("embedding_model", "hnsw:space")}
        col.modify(metadata=meta)  # simulate an index built before D22
        assert indexing._built_with_other_model(indexing.get_collection(client), "fake-a")

    def test_representation_hash_changes_when_alias_changes(self, schema):
        row = dataclasses.replace(schema.rows[0], alt_labels=("growth habit",))
        changed = dataclasses.replace(schema, rows=[row, *schema.rows[1:]])

        assert indexing._representation_hash(changed) != indexing._representation_hash(schema)
