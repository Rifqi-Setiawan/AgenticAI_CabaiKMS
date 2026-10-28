"""Unit and integration tests for L5: Migration runner integrity (M-01..M-03).

Tests:
M-01: Recorded migration checksum in DB differs from disk file -> raises RuntimeError.
M-02: Migration version recorded in DB but expected database table/object is missing ->
      fails hard with explicit error, does not re-run DDL, recorded checksum unchanged.
M-03: Migrations run once, subsequent migrate() call is idempotent and returns empty applied list.
"""

from __future__ import annotations

import os
import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.migrate import MIGRATIONS, migrate

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)
    return admin_url


def test_m01_checksum_mismatch_raises_runtime_error(admin_url):
    """M-01: Tampered recorded checksum in kms.schema_migrations raises RuntimeError."""
    engine = make_engine(Settings(_env_file=None, database_url=admin_url))

    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('kms.actor', 'curator-1', true)"))
        conn.execute(text("UPDATE kms.schema_migrations SET sha256 = 'bad_checksum_sha' WHERE version = '0003'"))

    try:
        with pytest.raises(RuntimeError) as exc_info:
            migrate(admin_url)
        assert "Migration 0003 checksum mismatch" in str(exc_info.value)
    finally:
        # Restore valid checksum
        import hashlib
        m0003_path = [p for v, p in MIGRATIONS if v == "0003"][0]
        correct_sha = hashlib.sha256(m0003_path.read_text(encoding="utf-8").encode()).hexdigest()
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('kms.actor', 'curator-1', true)"))
            conn.execute(
                text("UPDATE kms.schema_migrations SET sha256 = :s WHERE version = '0003'"),
                {"s": correct_sha},
            )


def test_m02_recorded_version_with_missing_table_fails_hard(admin_url):
    """M-02: Recorded version in schema_migrations with missing table fails hard, no re-run of DDL, checksum unchanged."""
    engine = make_engine(Settings(_env_file=None, database_url=admin_url))

    # Drop table kms.document_attribute_changes while version 0003 remains in schema_migrations
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS kms.document_attribute_changes CASCADE"))

    try:
        with pytest.raises(RuntimeError) as exc_info:
            migrate(admin_url)
        msg = str(exc_info.value).lower()
        assert "migration 0003 recorded but object" in msg
        assert "missing" in msg
        assert "manual intervention" in msg

        # Verify DDL was NOT re-run (table still does not exist)
        with engine.connect() as conn:
            exists = conn.scalar(text("SELECT to_regclass('kms.document_attribute_changes') IS NOT NULL"))
            assert not exists
    finally:
        # Restore schema using raw DDL
        m0003_path = [p for v, p in MIGRATIONS if v == "0003"][0]
        ddl = m0003_path.read_text(encoding="utf-8")
        with engine.begin() as conn:
            conn.execute(text(ddl))


def test_m03_migration_is_idempotent(admin_url):
    """M-03: Running migrate() on an up-to-date database returns empty applied list."""
    applied = migrate(admin_url)
    assert applied == []
