"""Integration tests for L5: Strict ledger compliance & migration readiness (T-30..T-34).

Tests:
T-30: Table kms.document_attribute_changes dropped in test DB -> commit fails (database error raised), doc unchanged.
T-31: Fully migrated test DB (0001, 0002, 0003) -> commit succeeds, 1 row written to ledger.
T-32: /readyz on unmigrated/partially migrated DB -> HTTP 503.
T-33: /readyz on fully migrated DB -> HTTP 200.
T-34: /livez returns HTTP 200 as long as process lives.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.testclient import TestClient

from src.kms_api.app import create_app
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_repository import DocumentRepository
from src.storage.identity_resolution import AdministrativeRegistry
from src.storage.image_storage import LocalCAS
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _setup_base_doc(repo: DocumentRepository) -> str:
    kms_repo = KmsRepository(repo.engine)
    sha = "1" * 64
    kms_repo.register_source(sha, "cas:///sources/l5_base.xlsx", 1000, actor="test-curator")

    plant = PlantIdentity(id="plant_l5", label="Cabai Rawit", identity_level="cultivar")
    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    doc_key = f"{plant.id}:{habitat.id}"
    attr = AttributeValue(
        label="tinggi tanaman",
        value=80.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="l5_base.xlsx", sheet="Sheet1", row=1, cell="A1", location_ref="loc_01"
        ),
    )
    doc = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[SamplingLocationDetail(location_ref="loc_01", raw_address="Sleman")],
        attributes={"attr_tinggi_tanaman": attr},
        media_refs=[],
        updated_by_run="run_l5_base",
    )
    draft = DocumentDraft(
        run_id="run_l5_base",
        source_filename="l5_base.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/l5_base.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc},
        reviews=[],
        base_versions={doc_key: 0},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")
    repo.commit("run_l5_base", staged["revision"], staged["payload_sha256"], actor="test-curator")
    return doc_key


def test_t30_dropped_ledger_table_fails_commit(db: Engine):
    """T-30: When document_attribute_changes is missing, commit fails (reraises error) and doc remains unchanged."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "2" * 64
    kms_repo.register_source(sha, "cas:///sources/l5_t30.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t30 = KnowledgeDocument.model_validate(clean_doc)
    doc_t30.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="tinggi tanaman",
        value=85.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="l5_t30.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_l5_t30",
        source_filename="l5_t30.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/l5_t30.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t30},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    # Temporarily drop or rename the ledger table
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    admin_engine = make_engine(Settings(_env_file=None, database_url=admin_url))
    with admin_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS kms.document_attribute_changes CASCADE"))

    try:
        # Commit must fail with database exception because table is missing (no silent fallback!)
        with pytest.raises(Exception):
            repo.commit("run_l5_t30", staged["revision"], staged["payload_sha256"], actor="test-curator")

        # Document remains at version 1 with original value 80.0
        doc_after = repo.get_document(doc_key)
        assert doc_after["version"] == 1
        assert doc_after["attributes"]["attr_tinggi_tanaman"]["value"] == 80.0
    finally:
        # Restore schema via raw DDL
        m0003_path = Path(__file__).resolve().parents[2] / "schema_0003_attribute_changes.sql"
        ddl = m0003_path.read_text(encoding="utf-8")
        with admin_engine.begin() as conn:
            conn.execute(text(ddl))


def test_t31_fully_migrated_db_writes_ledger_row(db: Engine):
    """T-31: Fully migrated test DB records 1 row in document_attribute_changes upon update."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "3" * 64
    kms_repo.register_source(sha, "cas:///sources/l5_t31.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t31 = KnowledgeDocument.model_validate(clean_doc)
    doc_t31.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="tinggi tanaman",
        value=86.5,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="l5_t31.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_l5_t31",
        source_filename="l5_t31.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/l5_t31.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t31},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")
    repo.commit("run_l5_t31", staged["revision"], staged["payload_sha256"], actor="test-curator")

    # Check ledger has 1 row recorded
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM kms.document_attribute_changes WHERE run_id = 'run_l5_t31'")
        ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["doc_id"] == doc_key
    assert rows[0]["attribute_id"] == "attr_tinggi_tanaman"
    assert rows[0]["actor"] == "test-curator"


def test_t32_readyz_on_unmigrated_db_returns_503(tmp_path):
    """T-32: /readyz returns HTTP 503 when required tables are missing."""
    url = os.getenv("TEST_DATABASE_URL")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    admin_engine = make_engine(Settings(_env_file=None, database_url=admin_url))
    # Drop document_attribute_changes (0003)
    with admin_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS kms.document_attribute_changes CASCADE"))

    media_dir = tmp_path / "media_readyz"
    media_dir.mkdir(parents=True, exist_ok=True)
    tokens = {"c" * 40: {"subject": "curator-1", "role": "curator"}}
    settings = Settings(
        _env_file=None,
        database_url=url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)

    try:
        with TestClient(app) as client:
            resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
            assert resp.status_code == 503
    finally:
        # Restore schema via raw DDL
        m0003_path = Path(__file__).resolve().parents[2] / "schema_0003_attribute_changes.sql"
        ddl = m0003_path.read_text(encoding="utf-8")
        with admin_engine.begin() as conn:
            conn.execute(text(ddl))


def test_t33_readyz_on_fully_migrated_db_returns_200(tmp_path):
    """T-33: /readyz returns HTTP 200 when all tables (0001, 0002, 0003) exist."""
    url = os.getenv("TEST_DATABASE_URL")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    media_dir = tmp_path / "media_readyz_200"
    media_dir.mkdir(parents=True, exist_ok=True)
    tokens = {"c" * 40: {"subject": "curator-1", "role": "curator"}}
    settings = Settings(
        _env_file=None,
        database_url=url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


def test_t34_livez_returns_200(tmp_path):
    """T-34: /livez returns HTTP 200 as long as process is alive."""
    url = os.getenv("TEST_DATABASE_URL")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    media_dir = tmp_path / "media_livez"
    media_dir.mkdir(parents=True, exist_ok=True)
    tokens = {"c" * 40: {"subject": "curator-1", "role": "curator"}}
    settings = Settings(
        _env_file=None,
        database_url=url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        resp = client.get("/livez")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"
