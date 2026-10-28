from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from .config import get_settings

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [
    ('0001', ROOT / 'schema.sql'),
    ('0002', ROOT / 'schema_0002_jsonb.sql'),
    ('0003', ROOT / 'schema_0003_attribute_changes.sql'),
    ('0004', ROOT / 'schema_0004_image_candidates.sql'),
]


def migrate(admin_url: str) -> list[str]:
    """Serialized, transactional, checksummed DDL; runtime credentials never need DDL."""
    import psycopg
    from sqlalchemy.engine import make_url

    url = make_url(admin_url)
    if url.drivername != 'postgresql+psycopg':
        raise ValueError('Expected a postgresql+psycopg URL.')
    dsn = url.set(drivername='postgresql').render_as_string(hide_password=False)
    applied: list[str] = []
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute('SELECT pg_advisory_xact_lock(733922159482)')
        connection.execute('CREATE SCHEMA IF NOT EXISTS kms')
        connection.execute('''CREATE TABLE IF NOT EXISTS kms.schema_migrations
          (version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())''')
        for version, path in MIGRATIONS:
            ddl = path.read_text(encoding='utf-8')
            checksum = hashlib.sha256(ddl.encode()).hexdigest()
            previous = connection.execute('SELECT sha256 FROM kms.schema_migrations WHERE version=%s', (version,)).fetchone()
            if previous:
                if previous[0] != checksum:
                    raise RuntimeError(f'Migration {version} checksum mismatch; add a new migration, never edit applied DDL.')
                table_to_check = None
                if version == '0004':
                    table_to_check = 'kms.image_candidates'
                elif version == '0003':
                    table_to_check = 'kms.document_attribute_changes'
                elif version == '0002':
                    table_to_check = 'kms.knowledge_documents'
                elif version == '0001':
                    table_to_check = 'kms.acquisition_runs'

                if table_to_check:
                    missing = bool(connection.execute('SELECT to_regclass(%s) IS NULL', (table_to_check,)).fetchone()[0])
                    if missing:
                        raise RuntimeError(
                            f'Migration {version} recorded but object {table_to_check} missing; manual intervention required.'
                        )
                continue
            # psycopg simple query supports the complete multi-statement migration.
            connection.execute(ddl, prepare=False)
            connection.execute('INSERT INTO kms.schema_migrations(version,sha256) VALUES (%s,%s)', (version, checksum))
            applied.append(version)
    return applied


def main() -> None:
    argparse.ArgumentParser(description='Apply pending CABAI-KMS DDL migrations').parse_args()
    settings = get_settings()
    if settings.database_admin_url is None:
        raise SystemExit('Set DATABASE_ADMIN_URL for this deployment command only.')
    print({'applied': migrate(settings.database_admin_url.get_secret_value())})


if __name__ == '__main__':
    main()
