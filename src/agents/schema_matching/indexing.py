"""Fase 3a — index the N canonical rows into ChromaDB for schema-matching
retrieval (Fase 3b queries against this collection).

Each row's `repr()` (CanonicalRow.serialize() from Fase 1: label ⊕ domain ⊕
contoh_nilai ⊕ altLabels) is embedded with a multilingual sentence-transformer
and stored with its row_id + domain as metadata. Indexing is idempotent: if
the collection already holds a vector for every current row AND the
template hasn't drifted since, ensure_indexed() is a no-op. If the template
*has* changed (row count, labels, or reordering — see
`CanonicalSchema.template_hash`), the collection is rebuilt automatically,
which is the "Fase 3a" auto re-index promised in canonical.py's docstring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

from src.schema.canonical import CanonicalSchema

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "data" / ".chroma"
COLLECTION_NAME = "canonical_rows"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict[str, Any] = {}


def get_embedding_model(model_name: str = EMBEDDING_MODEL_NAME) -> Any:
    """Lazily loaded + cached — sentence-transformers model construction is
    expensive, and most callers in a process want the same model repeatedly
    (indexing here, querying in Fase 3b)."""
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer

        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def encode(texts: list[str], model_name: str = EMBEDDING_MODEL_NAME) -> list[list[float]]:
    model = get_embedding_model(model_name)
    return model.encode(texts, normalize_embeddings=True).tolist()


def get_client(persist_dir: Path | str = DEFAULT_CHROMA_DIR) -> chromadb.ClientAPI:
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def get_collection(
    client: chromadb.ClientAPI | None = None,
    *,
    persist_dir: Path | str = DEFAULT_CHROMA_DIR,
) -> chromadb.api.models.Collection.Collection:
    client = client or get_client(persist_dir)
    # hnsw:space="cosine" so Fase 3b's ANN query is cosine similarity, not
    # chromadb's default (L2). collection.modify() REPLACES metadata rather
    # than merging it, so every modify() call below re-asserts this too.
    return client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def _collection_metadata(schema: CanonicalSchema) -> dict[str, Any]:
    # NOTE: "hnsw:space" is intentionally excluded — chromadb bakes the
    # distance function in at collection creation and rejects any modify()
    # call that even mentions the key again, matching value or not.
    return {
        "template_hash": schema.template_hash,
        "n_rows": len(schema.rows),
    }


def _is_up_to_date(collection: chromadb.api.models.Collection.Collection, schema: CanonicalSchema) -> bool:
    if collection.count() != len(schema.rows):
        return False
    if collection.metadata.get("template_hash") != schema.template_hash:
        return False
    existing_ids = set(collection.get(include=[])["ids"])
    return existing_ids == schema.row_ids


def ensure_indexed(
    schema: CanonicalSchema | None = None,
    *,
    client: chromadb.ClientAPI | None = None,
    persist_dir: Path | str = DEFAULT_CHROMA_DIR,
    model_name: str = EMBEDDING_MODEL_NAME,
    force: bool = False,
) -> chromadb.api.models.Collection.Collection:
    """Index every canonical row exactly once. Safe to call on every process
    startup: it re-embeds only if the collection is missing rows, stale
    (template drifted), or `force=True`."""
    schema = schema or CanonicalSchema.from_template()
    collection = get_collection(client, persist_dir=persist_dir)

    if not force and _is_up_to_date(collection, schema):
        return collection

    # Rebuild from scratch rather than a partial upsert: row ids are
    # positional (r_1..r_N), so if the template shrank, stale trailing ids
    # from a previous, longer template would otherwise linger forever.
    existing_ids = collection.get(include=[])["ids"]
    if existing_ids:
        collection.delete(ids=existing_ids)

    documents = [row.serialize() for row in schema.rows]
    embeddings = encode(documents, model_name=model_name)
    metadatas = [{"row_id": row.id, "domain": row.domain, "label": row.label} for row in schema.rows]
    ids = [row.id for row in schema.rows]

    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    collection.modify(metadata=_collection_metadata(schema))
    return collection
