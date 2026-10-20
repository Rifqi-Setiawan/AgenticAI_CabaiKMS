import os
import pytest

if not os.getenv("TEST_DATABASE_URL"):
    os.environ["TEST_DATABASE_URL"] = "postgresql+psycopg://cabai_test@/cabai_kms_test?host=/tmp"
    os.environ["TEST_DATABASE_ADMIN_URL"] = os.environ["TEST_DATABASE_URL"]


@pytest.fixture(autouse=True)
def default_test_env(monkeypatch):
    """Ensure unit tests do not attempt external KMS network calls unless explicitly enabled.

    KMS integration tests configure their own client/settings fixtures.
    """
    if not os.getenv("KMS_TEST_RUN"):
        monkeypatch.setenv("KMS_ENABLED", "false")


@pytest.fixture(autouse=True)
def clean_test_database_if_needed(request):
    """Clean disposable PostgreSQL test database before integration tests run."""
    if any(name in getattr(request, "fixturenames", []) for name in ("db", "test_db")):
        url = os.getenv("TEST_DATABASE_URL")
        if url:
            from sqlalchemy.engine import make_url
            db_name = make_url(url).database or ""
            if db_name.endswith("_test"):
                import psycopg
                parsed = make_url(url)
                dsn = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
                try:
                    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
                        conn.execute("DROP SCHEMA IF EXISTS kms CASCADE;")
                except Exception:
                    pass
