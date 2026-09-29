from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings


def make_engine(settings: Settings, *, admin: bool = False) -> Engine:
    secret = settings.database_admin_url if admin else settings.database_url
    if secret is None:
        raise ValueError('Database admin URL is not configured.')
    return create_engine(
        secret.get_secret_value(), pool_pre_ping=True,
        pool_size=settings.db_pool_size, max_overflow=2, pool_timeout=15,
        connect_args={'connect_timeout': 8, 'options': '-c timezone=UTC -c statement_timeout=30000 -c lock_timeout=10000'},
    )


def preflight(engine: Engine, *, require_migration: bool = True) -> dict[str, object]:
    with engine.connect() as connection:
        version = int(connection.scalar(text('SHOW server_version_num')))
        if version < 150000:
            raise RuntimeError('PostgreSQL >= 15 is required.')
        if connection.scalar(text('SHOW transaction_read_only')) == 'on':
            raise RuntimeError('Read-only database connection.')
        if connection.scalar(text('SHOW synchronous_commit')) == 'off':
            raise RuntimeError('synchronous_commit must not be off for authoritative commits.')
        if require_migration and connection.scalar(text("SELECT to_regclass('kms.acquisition_runs')")) is None:
            raise RuntimeError('KMS schema missing; execute the migration command first.')
        role = connection.execute(text('SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user')).one()
        owns_schema = connection.scalar(text("SELECT pg_has_role(current_user,nspowner,'MEMBER') FROM pg_namespace WHERE nspname='kms'"))
        privileged = bool(role.rolsuper or role.rolcreaterole or role.rolcreatedb or role.rolbypassrls or owns_schema)
        return {'postgres_version_num': version, 'writable': True, 'privileged_runtime_role': privileged}


@contextmanager
def transaction(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        # DB constraints remain authoritative; the service supplies audited actor context.
        session.execute(text('SET LOCAL synchronous_commit = on'))
        yield session
