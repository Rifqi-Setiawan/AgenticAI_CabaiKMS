from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from src.storage.config import Settings, get_settings
from src.storage.errors import Conflict, InvalidState


def enabled() -> bool:
    load_dotenv(override=False)
    return os.getenv('KMS_ENABLED', 'false').lower() in {'1', 'true', 'yes'}


class KmsClient:
    def __init__(self, settings: Settings, token: str | None = None):
        self.settings = settings
        self.token = token or (settings.kms_api_token.get_secret_value() if settings.kms_api_token else '')
        if not self.token:
            raise InvalidState('Configure a server-side KMS_API_TOKEN or enter a reviewer token.')

    def request(self, method: str, path: str, **kwargs) -> Any:
        with httpx.Client(base_url=self.settings.kms_api_base_url,
                          headers={'Authorization': 'Bearer ' + self.token},
                          timeout=httpx.Timeout(120, connect=8), follow_redirects=False) as client:
            response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get('detail', 'KMS request failed.')
                if not isinstance(detail, str):
                    detail = 'KMS payload contract validation failed; inspect without logging private input.'
            except ValueError:
                detail = 'KMS request failed.'
            if response.status_code == 409:
                raise Conflict(detail)
            raise InvalidState(f'HTTP {response.status_code}: {detail}')
        if response.headers.get('content-type', '').startswith('application/json'):
            return response.json()
        return response.content

    def source(self, data: bytes) -> dict:
        return self.request('POST', '/sources', content=data, headers={'Content-Type': 'application/octet-stream'})


def ui_client() -> KmsClient:
    import streamlit as st
    return KmsClient(get_settings(), token=st.session_state.get('kms_reviewer_token') or None)
