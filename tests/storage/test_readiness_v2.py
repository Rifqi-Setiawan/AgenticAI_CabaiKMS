"""Unit and integration tests for L4: Hardened readiness probe with authentication and migration checksum validation (P-01..P-06).

Tests:
P-01: /readyz without token -> 401 Unauthorized.
P-02: DB missing 0003 migration -> 503 mentioning '0003' in missing_migrations.
P-03: Recorded checksum in DB differs from migration file -> 503 with checksum_mismatch.
P-04: 503 response on database error does not leak exception strings, hostnames, or DSNs.
P-05: Fully migrated DB with valid checksums -> 200 OK {'status': 'ready'}.
P-06: /livez returns 200 OK {'status': 'alive'} without requiring any token.
"""

from __future__ import annotations

import json
import os
import uuid
import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from src.kms_api.app import create_app
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.image_storage import LocalCAS
from src.storage.migrate import MIGRATIONS, migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def base_settings(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    tokens = {
        "r" * 40: {"subject": "reader-1", "role": "reader"},
        "c" * 40: {"subject": "curator-1", "role": "curator"},
    }
    media_dir = tmp_path / "media_readyz_v2"
    media_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        _env_file=None,
        database_url=url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )


def test_p01_readyz_without_token_returns_401(base_settings):
    """P-01: /readyz without token returns HTTP 401 Unauthorized."""
    engine = make_engine(base_settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(base_settings.media_storage_path, min_free_bytes=0)
    app = create_app(base_settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 401
        assert "detail" in resp.json()


def test_p02_readyz_missing_0003_returns_503(base_settings):
    """P-02: DB without 0003 migration returns HTTP 503 mentioning '0003'."""
    engine = make_engine(base_settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(base_settings.media_storage_path, min_free_bytes=0)
    app = create_app(base_settings, repository=repo, blob_store=blob_store)

    # Delete 0003 record temporarily in test db
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('kms.actor', 'curator-1', true)"))
        conn.execute(text("DELETE FROM kms.schema_migrations WHERE version = '0003'"))

    try:
        with TestClient(app) as client:
            resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "not_ready"
            assert "missing_migrations" in body
            assert "0003" in body["missing_migrations"]
    finally:
        migrate(base_settings.database_admin_url.get_secret_value())


def test_p03_readyz_checksum_mismatch_returns_503(base_settings):
    """P-03: Recorded checksum differing from migration file returns HTTP 503 mentioning checksum_mismatch."""
    engine = make_engine(base_settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(base_settings.media_storage_path, min_free_bytes=0)
    app = create_app(base_settings, repository=repo, blob_store=blob_store)

    # Tamper 0003 checksum in test db
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('kms.actor', 'curator-1', true)"))
        conn.execute(text("UPDATE kms.schema_migrations SET sha256 = 'tampered_sha_xyz' WHERE version = '0003'"))

    try:
        with TestClient(app) as client:
            resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "not_ready"
            assert "checksum_mismatch" in body
            assert "0003" in body["checksum_mismatch"]
    finally:
        # Re-apply correct migration checksum
        import hashlib
        m0003_path = [p for v, p in MIGRATIONS if v == "0003"][0]
        correct_sha = hashlib.sha256(m0003_path.read_text(encoding="utf-8").encode()).hexdigest()
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('kms.actor', 'curator-1', true)"))
            conn.execute(
                text("UPDATE kms.schema_migrations SET sha256 = :s WHERE version = '0003'"),
                {"s": correct_sha},
            )


def test_p04_readyz_database_error_does_not_leak_exception_string(base_settings):
    """P-04: Response 503 on database error does not leak exception strings, DSNs, or hostnames."""
    # Configure an unreachable database port to simulate connection failure
    unreachable_settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cabai_test:dummy@127.0.0.1:54329/cabai_kms_unreachable",
        kms_tokens_json=base_settings.kms_tokens_json.get_secret_value(),
        media_storage_path=base_settings.media_storage_path,
        media_min_free_bytes=0,
    )
    engine = make_engine(unreachable_settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(base_settings.media_storage_path, min_free_bytes=0)
    app = create_app(unreachable_settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
        assert resp.status_code == 503
        data = resp.json()
        assert data.get("status") == "not_ready"
        # Must NOT leak exception details, credentials, or internal connection strings
        resp_text = resp.text.lower()
        assert "traceback" not in resp_text
        assert "54329" not in resp_text
        assert "operationalerror" not in resp_text
        assert "psycopg" not in resp_text
        assert "password" not in resp_text


def test_p05_readyz_fully_migrated_returns_200(base_settings):
    """P-05: Fully migrated DB with matching checksums returns HTTP 200 {'status': 'ready'}."""
    engine = make_engine(base_settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(base_settings.media_storage_path, min_free_bytes=0)
    app = create_app(base_settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ready"}


def test_p06_livez_returns_200_without_token(base_settings):
    """P-06: /livez returns HTTP 200 without token."""
    engine = make_engine(base_settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(base_settings.media_storage_path, min_free_bytes=0)
    app = create_app(base_settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        resp = client.get("/livez")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}
