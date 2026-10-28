import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.kms_api.app import create_app
from src.storage.errors import Conflict, NotFound
from src.storage.image_storage import LocalCAS


class MemoryRepository:
    def __init__(self):
        self.sources, self.assets, self.runs = {}, {}, {}
        self.last_actor = None

    def stage(self, draft, expected_revision, actor):
        self.last_actor = actor
        result = {'run_id': draft.run_id, 'revision': 1, 'payload_sha256': draft.fingerprint(), 'status': 'STAGED'}
        self.runs[draft.run_id] = result
        return result

    def get_run(self, run_id):
        if run_id not in self.runs:
            raise NotFound('Run not found.')
        return self.runs[run_id]

    def commit(self, run_id, revision, checksum, actor):
        raise Conflict('Stale draft.')

    def inspect_values(self, **kwargs):
        return []

    def register_source(self, checksum, uri, size, actor):
        self.sources[checksum] = dict(sha256=checksum, storage_uri=uri, file_size=size)
        return self.sources[checksum]

    def get_source(self, checksum):
        return self.sources[checksum]

    def register_asset(self, data, actor):
        self.assets[data['id']] = data
        return data

    def get_asset(self, asset_id):
        if asset_id not in self.assets:
            raise NotFound('Asset not found.')
        return self.assets[asset_id]


@pytest.fixture
def client(settings):
    repo = MemoryRepository()
    app = create_app(settings, repository=repo, blob_store=LocalCAS(settings.media_storage_path, min_free_bytes=0))
    with TestClient(app) as instance:
        yield instance, repo


def authorization(role='w'):
    return {'Authorization': 'Bearer ' + role*40}


def test_auth_and_health(client):
    connection, _ = client
    assert connection.get('/healthz').status_code == 200
    assert connection.get('/values').status_code == 401
    assert connection.get('/values', headers=authorization('r')).status_code == 200


def test_role_and_actor(client, draft):
    connection, repo = client
    payload = {'draft': draft.ordered_payload(), 'expected_revision': 0}
    assert connection.post('/runs/stage', json=payload, headers=authorization('r')).status_code == 403
    response = connection.post('/runs/stage', json=payload, headers=authorization())
    assert response.status_code == 200, response.text
    assert repo.last_actor == 'reviewer-test'


def test_bad_contract_and_conflict(client, draft):
    connection, _ = client
    assert connection.post('/runs/stage', json={'draft': {}}, headers=authorization()).status_code == 422
    assert connection.post('/runs/test-run/commit', json={'expected_revision': 1, 'payload_sha256': 'a'*64}, headers=authorization()).status_code == 409


def test_image_private_roundtrip(client, png_bytes):
    connection, _ = client
    response = connection.post('/assets', content=png_bytes, headers=authorization())
    assert response.status_code == 200, response.text
    image_id = response.json()['id']
    assert connection.get(f'/media/{image_id}/image').status_code == 401
    image = connection.get(f'/media/{image_id}/thumbnail', headers=authorization('r'))
    assert image.status_code == 200
    assert image.headers['cache-control'] == 'private, no-store'
    assert image.headers['content-type'] == 'image/webp'
    assert connection.get(f'/media/{image_id}/original', headers=authorization()).status_code == 422


def make_xlsx(macro=False):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as file:
        file.writestr('[Content_Types].xml', '<Types/>')
        file.writestr('xl/workbook.xml', '<workbook/>')
        if macro:
            file.writestr('xl/vbaProject.bin', b'bad')
    return payload.getvalue()


def test_sources_archive(client):
    connection, _ = client
    original = make_xlsx()
    result = connection.post('/sources', content=original, headers=authorization())
    assert result.status_code == 200, result.text
    fetched = connection.get('/sources/' + result.json()['sha256'], headers=authorization('r'))
    assert fetched.content == original
    assert connection.post('/sources', content=make_xlsx(True), headers=authorization()).status_code == 422
    assert connection.post('/sources', content=b'bad', headers=authorization()).status_code == 422


def test_body_limit(settings):
    settings.api_max_body_bytes = 1024
    with TestClient(create_app(settings, repository=MemoryRepository(), blob_store=LocalCAS(settings.media_storage_path, min_free_bytes=0))) as connection:
        assert connection.post('/assets', content=b'x'*1025, headers=authorization()).status_code == 413
