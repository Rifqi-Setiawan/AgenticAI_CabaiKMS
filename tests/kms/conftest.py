import io
import json
from pathlib import Path

import pytest
from PIL import Image

from src.storage.config import Settings
from src.storage.contracts import RunDraft


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url='postgresql+psycopg://app:secret@127.0.0.1/cabai_kms_test',
        media_storage_path=tmp_path / 'media', media_min_free_bytes=0,
        kms_tokens_json=json.dumps({'r'*40: {'subject': 'reader-test', 'role': 'reader'},
                                  'w'*40: {'subject': 'reviewer-test', 'role': 'reviewer'},
                                  'c'*40: {'subject': 'curator-test', 'role': 'curator'}}))


@pytest.fixture
def draft():
    return RunDraft(run_id='test-run', source_filename='lapangan.xlsx', file_sha256='a'*64,
        source_scope='research-team', schema_version='v1', template_hash='b'*64, config_fingerprint='config-v1',
        total_attributes=1, auto_accepted_count=1, reviewed_count=0,
        characteristics=[dict(canonical_key='panjang_buah', label_id='Panjang buah', organ_domain='buah',
                              source_domain='buah', data_type='number', standard_unit='cm')],
        varieties=[dict(canonical_name='Katokkon', local_aliases=['Katokkon'])],
        values=[dict(variety_name='Katokkon', canonical_key='panjang_buah', normalized_value=5.5,
            raw_source_value='5,5 cm', value_type='number', confidence_score=0.9, status='AUTO_ACCEPT',
            provenance=[{'source_cells': ['C4'], 'raw_value': '5,5 cm', 'normalized_value': 5.5}])],
        metadata={'legacy_source_unavailable': True})


@pytest.fixture
def png_bytes():
    stream = io.BytesIO()
    image = Image.new('RGBA', (600, 300), (12, 90, 33, 255))
    image.save(stream, format='PNG')
    return stream.getvalue()
