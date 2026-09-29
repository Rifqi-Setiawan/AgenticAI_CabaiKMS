#!/usr/bin/env python3
"""Create fresh PG roles/database and private env files. Refuses existing identities."""
import argparse
import json
import os
import pwd
import secrets
import subprocess
from pathlib import Path


def psql(sql: str, database='postgres') -> str:
    result = subprocess.run(['runuser', '-u', 'postgres', '--', 'psql', '-X', '-A', '-t',
                             '-v', 'ON_ERROR_STOP=1', '--dbname', database],
                            input=sql, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('PostgreSQL bootstrap failed. Inspect PG service/permissions; credentials were not logged.')
    return result.stdout.strip()


def write_secret(path: Path, content: str, uid: int, gid: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(path, uid, gid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path('/etc/cabai-kms'))
    parser.add_argument('--runtime-user', default='cabai')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo; PostgreSQL peer administration and private env ownership require root.')
    account = pwd.getpwnam(args.runtime_user)
    args.output_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(args.output_dir, 0, account.pw_gid)
    os.chmod(args.output_dir, 0o750)
    files = ['runtime.env','ui.env','migration.env']
    if any((args.output_dir / name).exists() for name in files):
        raise SystemExit('Refusing to overwrite credentials. Reuse existing configuration or perform a deliberate rotation.')
    if int(psql("SELECT count(*) FROM pg_roles WHERE rolname IN ('cabai_migrator','cabai_app');")) or int(psql("SELECT count(*) FROM pg_database WHERE datname='cabai_kms';")):
        raise SystemExit('Database/roles already exist. Stop and reconcile their ownership and credentials; no destructive reset is permitted.')
    migrator_password, app_password = secrets.token_hex(32), secrets.token_hex(32)
    app_url = f'postgresql+psycopg://cabai_app:{app_password}@127.0.0.1:5432/cabai_kms'
    admin_url = f'postgresql+psycopg://cabai_migrator:{migrator_password}@127.0.0.1:5432/cabai_kms'
    token_reader, token_reviewer, token_curator = (secrets.token_urlsafe(40) for _ in range(3))
    tokens = {token_reader: {'subject': 'kms-read-service', 'role': 'reader'},
              token_reviewer: {'subject': 'streamlit-service', 'role': 'reviewer'},
              token_curator: {'subject': 'curation-service', 'role': 'curator'}}
    # Write recovery credentials before any database mutation. Do not print passwords or tokens.
    write_secret(args.output_dir / 'migration.env', f'DATABASE_URL={app_url}\nDATABASE_ADMIN_URL={admin_url}\n', 0, 0)
    common = f'DATABASE_URL={app_url}\nDB_AUTO_MIGRATE=false\nKMS_ENABLED=false\nMEDIA_BACKEND=local\nMEDIA_STORAGE_PATH=/srv/media/cabai-kms\nMEDIA_PUBLIC_BASE_URL=http://127.0.0.1:8091\nKMS_API_BASE_URL=http://127.0.0.1:8091\nALLOW_LEGACY_SOURCELESS_RUNS=false\n'
    write_secret(args.output_dir / 'runtime.env', common + "KMS_TOKENS_JSON='" + json.dumps(tokens, separators=(',', ':')) + "'\n", account.pw_uid, account.pw_gid)
    write_secret(args.output_dir / 'ui.env', common + f'KMS_API_TOKEN={token_reviewer}\nKMS_SOURCE_SCOPE=cabai-research\n', account.pw_uid, account.pw_gid)
    # Passwords below are generated hex, not user-supplied SQL. Passed over stdin, never argv.
    psql("SET password_encryption='scram-sha-256';\n"
         f"CREATE ROLE cabai_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{migrator_password}';\n"
         f"CREATE ROLE cabai_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{app_password}';\n")
    psql('CREATE DATABASE cabai_kms OWNER cabai_migrator;')
    psql('REVOKE ALL ON DATABASE cabai_kms FROM PUBLIC; GRANT CONNECT ON DATABASE cabai_kms TO cabai_app;')
    psql('REVOKE CREATE ON SCHEMA public FROM PUBLIC;', 'cabai_kms')
    print(f'Created cabai_kms and least-privilege identities. Private files: {args.output_dir}. KMS remains disabled.')


if __name__ == '__main__':
    main()
