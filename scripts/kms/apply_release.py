#!/usr/bin/env python3
"""One release migration with a root-only env file; avoids putting secrets on argv."""
import argparse
import os
from pathlib import Path
import sys
for candidate in Path(__file__).resolve().parents:
    if (candidate / 'src' / 'storage').is_dir() and (candidate / 'schema.sql').is_file():
        sys.path.insert(0, str(candidate))
        break

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from src.storage.migrate import migrate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, default=Path('/etc/cabai-kms/migration.env'))
    parser.add_argument('--grants', type=Path, default=Path('deploy/grants.sql'))
    args = parser.parse_args()
    if args.env_file.stat().st_mode & 0o077:
        raise SystemExit('Migration credentials must have mode 0600.')
    config = dotenv_values(args.env_file)
    url = config.get('DATABASE_ADMIN_URL')
    if not url:
        raise SystemExit('DATABASE_ADMIN_URL is missing.')
    import psycopg
    print({'applied': migrate(url)})
    dsn = make_url(url).set(drivername='postgresql').render_as_string(hide_password=False)
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute(args.grants.read_text(), prepare=False)
    print('Runtime role grants applied. Schema owner and API identity remain separate.')


if __name__ == '__main__':
    main()
