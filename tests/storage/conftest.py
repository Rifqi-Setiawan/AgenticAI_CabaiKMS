from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def resume_data_workbook_path(project_root: Path) -> Path:
    return project_root / "data" / "samples" / "data_input.xlsx"


@pytest.fixture
def valid_administrative_path_dict() -> dict[str, Any]:
    return {
        "province_id": "prop_34",
        "regency_id": "kab_3404",
        "district_id": "kec_3404070",
        "village_id": "desa_3404070001",
        "province_name": "Daerah Istimewa Yogyakarta",
        "regency_name": "Kabupaten Sleman",
        "district_name": "Kecamatan Pakem",
        "village_name": "Desa Hargobinangun",
    }


@pytest.fixture
def valid_habitat_identity_dict(valid_administrative_path_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "hab_sleman_hargobinangun_001",
        "definition": "administrative_village_v1",
        "administrative_path": valid_administrative_path_dict,
        "label": "Desa Hargobinangun, Kecamatan Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta",
    }


@pytest.fixture
def valid_plant_identity_dict() -> dict[str, Any]:
    return {
        "id": "plant_rawit_frutescens_001",
        "label": "Cabai rawit (Capsicum frutescens L)",
        "identity_level": "source_category",
        "scientific_name": "Capsicum frutescens L",
    }


@pytest.fixture
def valid_sampling_location_dict() -> dict[str, Any]:
    return {
        "location_ref": "loc_sleman_01",
        "raw_address": "Dusun Randu, Desa Hargobinangun, Area Sawah, Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta 55582, Indonesia (sampling 1)",
        "hamlet": "Dusun Randu",
        "sampling_marker": "sampling 1",
        "coordinates": {"lat": -7.6321, "lon": 110.4215},
    }


@pytest.fixture
def valid_current_source_dict() -> dict[str, Any]:
    return {
        "source_ref": "src_field_data_input_2026",
        "sheet": "Resume Data",
        "row": 3,
        "cell": "G3",
        "location_ref": "loc_sleman_01",
    }


@pytest.fixture
def valid_attribute_value_dict(valid_current_source_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": "Chlorophyll Content (SPAD)",
        "value": 49.02,
        "value_type": "number",
        "unit": "SPAD",
        "resolution": "AUTO_ACCEPT",
        "mapping_policy_version": "exact-alias-policy-v1",
        "current_source": valid_current_source_dict,
    }


@pytest.fixture
def valid_media_reference_dict() -> dict[str, Any]:
    return {
        "asset_id": "a" * 64,
        "organ_part": "daun",
        "caption": "Foto daun cabai rawit lapangan",
        "source_filename": "cabai_rawit_daun_01.jpg",
        "provenance_run_id": "run_20260923_001",
        "assigned_via": "AUTO_ACCEPT",
        "resolution_status": "linked",
    }


@pytest.fixture
def valid_knowledge_document_dict(
    valid_plant_identity_dict: dict[str, Any],
    valid_habitat_identity_dict: dict[str, Any],
    valid_sampling_location_dict: dict[str, Any],
    valid_attribute_value_dict: dict[str, Any],
    valid_media_reference_dict: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "kms-document-v1",
        "variety": valid_plant_identity_dict,
        "habitat": valid_habitat_identity_dict,
        "sampling_locations": [valid_sampling_location_dict],
        "attributes": {
            "attr_chlorophyll_spad": valid_attribute_value_dict,
        },
        "media_refs": [valid_media_reference_dict],
        "updated_by_run": "run_20260923_001",
    }


@pytest.fixture
def valid_document_draft_dict(
    valid_knowledge_document_dict: dict[str, Any],
) -> dict[str, Any]:
    doc_key = f"{valid_knowledge_document_dict['variety']['id']}:{valid_knowledge_document_dict['habitat']['id']}"
    return {
        "run_id": "run_test_001",
        "source_filename": "data_input.xlsx",
        "file_sha256": "f" * 64,
        "source_uri": "file:///srv/media/sources/data_input.xlsx",
        "source_scope": "field_survey_2026",
        "schema_version": "kms-document-v1",
        "template_hash": "e" * 64,
        "config_fingerprint": "cfg_fingerprint_001",
        "revision": 1,
        "documents": {
            doc_key: valid_knowledge_document_dict,
        },
        "reviews": [],
        "base_versions": {
            doc_key: 1,
        },
        "metadata": {
            "survey_year": 2026,
        },
    }
