from types import SimpleNamespace

import pandas as pd
import pytest

from src.integrations.adapter import build_draft, catalog_from_schema, typed_value
from src.storage.contracts import CharacteristicInput
from src.storage.errors import InvalidState


def fixture_objects():
    row = SimpleNamespace(canonical_key='panjang_buah', label='Panjang buah', domain='buah')
    schema = SimpleNamespace(rows=[row], template_hash='b'*64, schema_version='v1')
    evidence = dict(run_id='run1', source_file_sha256='a'*64, variety='Katokkon', canonical_key='panjang_buah',
                    raw_value='5,5', mapping_confidence=0.8, acceptance_status='AUTO_ACCEPT', canonical_write=True)
    result = SimpleNamespace(run_id='run1', template_hash='b'*64, schema_version='v1', evaluation_config_fingerprint='eval',
        canonical_df=pd.DataFrame([[1, 'Panjang buah', '5.5']], columns=['Nomor','Karakter','Katokkon']),
        provenance_records=[evidence], vision_rows=[],
        mapping_df=pd.DataFrame([{'source_file_sha256': 'a'*64, 'acceptance_status': 'AUTO_ACCEPT'}]))
    return result, schema


def test_adapter_keeps_original_raw_and_sha():
    result, schema = fixture_objects()
    draft = build_draft(result, result, schema, [], source_filename='original.xlsx', source_scope='lab', context={})
    assert draft.values[0].raw_source_value == ['5,5']
    assert draft.file_sha256 == 'a'*64
    assert draft.values[0].normalized_value == '5.5'
    assert draft.values[0].value_type == 'text'  # no numeric inference without curated metadata


def test_adapter_typed_override():
    result, schema = fixture_objects()
    draft = build_draft(result, result, schema, [], source_filename='original.xlsx', source_scope='lab', context={},
                        overrides={'panjang_buah': {'data_type': 'number', 'standard_unit': 'cm'}})
    assert draft.values[0].normalized_value == 5.5


def test_adapter_refuses_untraced_values():
    result, schema = fixture_objects()
    result.provenance_records = []
    with pytest.raises(InvalidState, match='provenance'):
        build_draft(result, result, schema, [], source_filename='x.xlsx', source_scope='lab', context={})


def test_domains_are_not_invented():
    schema = SimpleNamespace(rows=[SimpleNamespace(canonical_key='lokasi', label='Lokasi', domain='lokasi'),
                                  SimpleNamespace(canonical_key='batang', label='Batang', domain='vegetatif')])
    catalog = catalog_from_schema(schema)
    assert catalog[0].organ_domain is None and catalog[0].data_type == 'location'
    assert catalog[1].organ_domain == 'batang'


@pytest.mark.parametrize('value,expected', [('1-2 cm', {'min': 1.0, 'max': 2.0}), ('-2--1 cm', {'min': -2.0, 'max': -1.0}), ('0', 0.0)])
def test_numeric_parser(value, expected):
    characteristic = CharacteristicInput(canonical_key='x', label_id='X', source_domain='buah', data_type='number', standard_unit='cm')
    assert typed_value(value, characteristic)[0] == expected
