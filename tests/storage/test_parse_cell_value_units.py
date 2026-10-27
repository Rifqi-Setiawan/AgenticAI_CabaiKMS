"""Unit tests for L1: parse_cell_value unit validation restoration (T-01..T-08).

Tests:
T-01: '5 kg', number, cm -> invalid, category VALUE_INVALID
T-02: '12 xyz', number, without expected unit -> invalid, category VALUE_INVALID
T-03: '20 cm', number, cm -> valid, value 20.0, unit 'cm'
T-04: '7 foo', number, cm -> invalid, category VALUE_INVALID
T-05: Parametric table of 5 audit cases matching d48002a baseline behavior
T-06: 'hijau', number -> type 'text', valid, unit None (D1 retained)
T-07: (planner) existing 80 cm + incoming '85.0 kg' -> one UNIT_MISMATCH review item, old value intact, complete payload
T-08: (planner) without existing attribute + '85.0 kg' -> VALUE_INVALID, no attribute written
"""

from __future__ import annotations

import pytest

from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_planner import DocumentPlanner, parse_cell_value
from src.storage.identity_resolution import AdministrativeRegistry


def test_t01_incompatible_unit_returns_value_invalid():
    """T-01: '5 kg' with expected unit 'cm' must be invalid with review_category VALUE_INVALID."""
    res = parse_cell_value("5 kg", expected_type="number", unit="cm")
    assert res.is_valid is False
    assert res.review_category == "VALUE_INVALID"
    assert "unit" in res.error.lower()


def test_t02_unrecognized_unit_without_expected_unit_returns_value_invalid():
    """T-02: '12 xyz' with expected_type 'number' and no expected unit must be invalid."""
    res = parse_cell_value("12 xyz", expected_type="number", unit=None)
    assert res.is_valid is False
    assert res.review_category == "VALUE_INVALID"
    assert "unit" in res.error.lower()


def test_t03_matching_unit_returns_valid_number():
    """T-03: '20 cm' with expected unit 'cm' must be valid with value 20.0 and unit 'cm'."""
    res = parse_cell_value("20 cm", expected_type="number", unit="cm")
    assert res.is_valid is True
    assert res.value == 20.0
    assert res.unit == "cm"


def test_t04_mismatched_unknown_unit_returns_value_invalid():
    """T-04: '7 foo' with expected unit 'cm' must be invalid with review_category VALUE_INVALID."""
    res = parse_cell_value("7 foo", expected_type="number", unit="cm")
    assert res.is_valid is False
    assert res.review_category == "VALUE_INVALID"
    assert "unit" in res.error.lower()


@pytest.mark.parametrize(
    "raw_input,expected_type,expected_unit,is_valid,expected_val,val_type,cat",
    [
        ("5 kg", "number", "cm", False, 5.0, "number", "VALUE_INVALID"),
        ("12 xyz", "number", None, False, 12.0, "number", "VALUE_INVALID"),
        ("20 cm", "number", "cm", True, 20.0, "number", None),
        ("7 foo", "number", "cm", False, 7.0, "number", "VALUE_INVALID"),
        ("hijau", "number", "cm", True, "hijau", "text", None),
    ],
)
def test_t05_parametric_five_audit_cases(
    raw_input, expected_type, expected_unit, is_valid, expected_val, val_type, cat
):
    """T-05: Parametric evaluation of the 5 audit cases matching original baseline specification."""
    res = parse_cell_value(raw_input, expected_type=expected_type, unit=expected_unit)
    assert res.is_valid is is_valid
    assert res.value == expected_val
    assert res.value_type == val_type
    if cat is not None:
        assert res.review_category == cat
    if is_valid and val_type == "text":
        assert res.unit is None


def test_t06_text_value_in_numeric_column_retains_text_type():
    """T-06: 'hijau' in a numeric column is preserved as valid text with unit None (Decision D1)."""
    res = parse_cell_value("hijau", expected_type="number", unit="cm")
    assert res.is_valid is True
    assert res.value == "hijau"
    assert res.value_type == "text"
    assert res.unit is None


def test_t07_planner_unit_mismatch_with_existing_attribute():
    """T-07: When cell has unit mismatch AND attribute already exists in document, create UNIT_MISMATCH."""
    planner = DocumentPlanner()
    ar = AdministrativeRegistry()
    plant = PlantIdentity(id="plant_cabai_rawit", label="Cabai rawit", identity_level="species")
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    assert habitat is not None
    doc_key = f"{plant.id}:{habitat.id}"

    exist_attr = AttributeValue(
        label="tinggi tanaman",
        value=80.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="survey_prior.xlsx",
            sheet="Resume Data",
            row=1,
            cell="B2",
            location_ref="loc_001",
        ),
    )

    base_doc = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[
            SamplingLocationDetail(
                location_ref="loc_001",
                raw_address="Dusun Karang, Desa Hargobinangun, Sleman",
                hamlet="Dusun Karang",
                sampling_marker="marker 1",
            )
        ],
        attributes={"attr_tinggi_tanaman": exist_attr},
        media_refs=[],
        updated_by_run="run_prev",
    )

    records = [
        {
            "_row": 2,
            "_sheet": "Resume Data",
            "Varietas": "Cabai Rawit",
            "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
            "tinggi tanaman": "85.0 kg",
        }
    ]

    draft = planner.plan_records(
        records,
        current_documents={doc_key: base_doc},
        run_id="run_t07",
    )

    # Document attribute must be preserved as 80.0 cm
    planned_doc = draft.documents[doc_key]
    assert planned_doc.attributes["attr_tinggi_tanaman"].value == 80.0
    assert planned_doc.attributes["attr_tinggi_tanaman"].unit == "cm"

    # Exactly one review item of category UNIT_MISMATCH
    unit_reviews = [r for r in draft.reviews if r.category == "UNIT_MISMATCH"]
    assert len(unit_reviews) == 1
    rev = unit_reviews[0]
    assert rev.source_label == "tinggi tanaman"
    assert rev.target_document_key == doc_key
    assert rev.payload.get("attribute_id") == "attr_tinggi_tanaman"
    assert rev.payload.get("old_value") == 80.0
    assert rev.payload.get("old_unit") == "cm"
    assert rev.payload.get("new_unit") == "kg"
    assert rev.raw_values == [80.0, 85.0]


def test_t08_planner_unit_mismatch_without_existing_attribute():
    """T-08: When cell has invalid unit and attribute does NOT exist, classify as VALUE_INVALID and do not write attribute."""
    planner = DocumentPlanner()
    ar = AdministrativeRegistry()
    plant = PlantIdentity(id="plant_cabai_rawit", label="Cabai rawit", identity_level="species")
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    assert habitat is not None
    doc_key = f"{plant.id}:{habitat.id}"

    records = [
        {
            "_row": 2,
            "_sheet": "Resume Data",
            "Varietas": "Cabai Rawit",
            "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
            "tinggi tanaman": "85.0 kg",
        }
    ]

    draft = planner.plan_records(records, run_id="run_t08")
    planned_doc = draft.documents[doc_key]

    # Attribute must NOT be written
    assert "attr_tinggi_tanaman" not in planned_doc.attributes

    # Exactly one review item of category VALUE_INVALID
    val_reviews = [r for r in draft.reviews if r.category == "VALUE_INVALID"]
    assert len(val_reviews) == 1
    assert val_reviews[0].source_label == "tinggi tanaman"
