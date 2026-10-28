import copy
import math

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from src.storage.config import Settings
from src.storage.contracts import RunDraft, ValueInput, normalize_identity
from src.storage.repository import value_upsert, variety_upsert


def test_name_identity(draft):
    assert draft.varieties[0].canonical_name == 'katokkon'
    assert normalize_identity('  CABAI\t Merah  ') == 'cabai merah'


def test_fingerprint_roundtrip(draft):
    assert RunDraft.model_validate_json(draft.model_dump_json()).fingerprint() == draft.fingerprint()


@pytest.mark.parametrize('kind,value,multi', [('number', True, False), ('number', math.nan, False),
    ('range', {'min': 9, 'max': 1}, False), ('range', {'min': '1', 'max': 2}, False),
    ('list', [1, 2], False), ('list', [], True), ('text', '', False), ('boolean', 1, False)])
def test_reject_invalid_value_shapes(draft, kind, value, multi):
    payload = draft.values[0].model_dump()
    payload.update(value_type=kind, normalized_value=value, is_multi_value=multi)
    with pytest.raises(ValidationError):
        ValueInput.model_validate(payload)


@pytest.mark.parametrize('kind,value,multi', [('number', 0, False), ('number', -0.3, False),
    ('range', {'min': -2, 'max': 1}, False), ('list', [0, 1], True), ('boolean', False, False)])
def test_accept_valid_shapes(draft, kind, value, multi):
    payload = draft.values[0].model_dump()
    payload.update(value_type=kind, normalized_value=value, is_multi_value=multi)
    assert ValueInput.model_validate(payload).normalized_value == value


def test_duplicate_identity_fails(draft):
    payload = draft.model_dump()
    payload['varieties'].append({'canonical_name': ' KATOKKON '})
    with pytest.raises(ValidationError):
        RunDraft.model_validate(payload)


def test_cross_catalog_fails(draft):
    payload = draft.model_dump()
    payload['values'][0]['canonical_key'] = 'unknown'
    with pytest.raises(ValidationError):
        RunDraft.model_validate(payload)


def test_config_rejects_public_http():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url='postgresql+psycopg://a:b@localhost/x', kms_api_base_url='http://evil.example')


def test_config_no_secrets_repr(settings):
    assert 'app:secret@' not in repr(settings)
    assert 'w'*40 not in repr(settings)


def test_upsert_sql_is_optimistic():
    sql = str(value_upsert({'normalized_value': 2}, 7).compile(dialect=postgresql.dialect()))
    assert 'ON CONFLICT (variety_id, characteristic_id) DO UPDATE' in sql
    assert 'WHERE kms.variety_character_values.version =' in sql
    assert 'RETURNING' in sql


def test_variety_upsert_sql():
    sql = str(variety_upsert({'canonical_name': 'x', 'metadata': {}}).compile(dialect=postgresql.dialect()))
    assert 'ON CONFLICT (canonical_name) DO UPDATE' in sql
    assert 'metadata || excluded.metadata' in sql
