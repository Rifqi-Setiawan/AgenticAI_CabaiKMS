from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', case_sensitive=False)
    database_url: SecretStr
    database_admin_url: SecretStr | None = None
    db_pool_size: int = Field(default=4, ge=1, le=20)
    db_auto_migrate: bool = False
    allow_legacy_sourceless_runs: bool = False
    media_backend: Literal['local', 's3'] = 'local'
    media_storage_path: Path = Path('/srv/media/cabai-kms')
    # This is an authenticated API base, NEVER a public bucket URL.
    media_public_base_url: str = 'http://127.0.0.1:8091'
    kms_api_base_url: str = 'http://127.0.0.1:8091'
    kms_api_token: SecretStr | None = None
    kms_tokens_json: SecretStr = SecretStr('{}')
    kms_enabled: bool = False
    media_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    media_max_pixels: int = Field(default=40_000_000, ge=1024, le=80_000_000)
    media_min_free_bytes: int = Field(default=5 * 1024**3, ge=0)
    source_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    api_max_body_bytes: int = Field(default=64 * 1024 * 1024, ge=1024)
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = 'auto'
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    google_drive_credentials_path: Path | None = None
    outbox_webhook_url: str | None = None
    outbox_webhook_secret: SecretStr | None = None

    @field_validator('database_url', 'database_admin_url')
    @classmethod
    def postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith('postgresql+psycopg://'):
            raise ValueError('Use postgresql+psycopg:// (SQLAlchemy 2 + psycopg 3).')
        return value

    @field_validator('media_public_base_url', 'kms_api_base_url', 's3_endpoint_url', 'outbox_webhook_url')
    @classmethod
    def secure_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('URLs must not contain credentials, query strings or fragments.')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}):
            raise ValueError('HTTPS required except on loopback.')
        return value.rstrip('/')

    @model_validator(mode='after')
    def validate_backend(self) -> 'Settings':
        if self.media_backend == 's3' and not self.s3_bucket:
            raise ValueError('S3_BUCKET is required for MEDIA_BACKEND=s3.')
        if self.db_auto_migrate and self.database_admin_url is None:
            raise ValueError('DB_AUTO_MIGRATE requires a separate DATABASE_ADMIN_URL.')
        return self

    def principals(self) -> dict[str, dict[str, str]]:
        result = json.loads(self.kms_tokens_json.get_secret_value())
        if not isinstance(result, dict) or not result:
            raise ValueError('KMS_TOKENS_JSON must define at least one service token.')
        for token, principal in result.items():
            if len(token) < 32 or not isinstance(principal, dict):
                raise ValueError('Each service token must have at least 32 characters.')
            if not principal.get('subject') or principal.get('role') not in {'reader', 'reviewer', 'curator'}:
                raise ValueError('Each token needs a subject and a valid role.')
        return result


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
