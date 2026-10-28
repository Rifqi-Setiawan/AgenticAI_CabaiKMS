"""Unit tests for L2: Attribute overwrite matrix & block reasons (T-09..T-12).

Tests:
T-09: Parametric matrix:
     existing{AUTO,HUMAN} x incoming{AUTO,HUMAN} x type{same,diff} x
     unit{same,compatible,incompatible,none} x label{same,diff}.
     Only AUTO/AUTO + same type + same/compatible/none unit + compatible label is True.
T-10: existing HUMAN + incoming AUTO -> False, reason code EXISTING_HUMAN_PROTECTED.
T-11: Legacy test test_nilai_human_review_tidak_diturunkan_oleh_auto_accept in test_attribute_overwrite.py remains unchanged and passes.
T-12: (planner) existing HUMAN + incoming AUTO -> OVERWRITE_BLOCKED review item with reason_code EXISTING_HUMAN_PROTECTED, old value intact.
"""

from __future__ import annotations

import itertools
import pytest

from src.storage.attribute_policy import AttributePolicy
from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_planner import DocumentPlanner
from src.storage.identity_resolution import AdministrativeRegistry


def _make_attr(
    label: str = "tinggi tanaman",
    value: any = 80.0,
    value_type: str = "number",
    unit: str | None = "cm",
    resolution: str = "AUTO_ACCEPT",
) -> AttributeValue:
    return AttributeValue(
        label=label,
        value=value,
        value_type=value_type,  # type: ignore[arg-type]
        unit=unit,
        resolution=resolution,  # type: ignore[arg-type]
        mapping_policy_version="exact-alias-policy-v1",
        current_source=CurrentSourceReference(
            source_ref="test_src.xlsx",
            sheet="Resume Data",
            row=2,
            cell="B2",
            location_ref="loc_001",
        ),
    )


# Generate test cases for T-09
_MATRIX_COMBOS = list(
    itertools.product(
        ["AUTO_ACCEPT", "HUMAN_REVIEW"],  # existing resolution
        ["AUTO_ACCEPT", "HUMAN_REVIEW"],  # incoming resolution
        [True, False],                    # same type
        ["same", "compatible", "incompatible", "none"],  # unit relation
        [True, False],                    # same/compatible label
    )
)


@pytest.mark.parametrize(
    "ex_res,inc_res,same_type,unit_rel,same_label",
    _MATRIX_COMBOS,
)
def test_t09_parametric_overwrite_matrix(
    ex_res: str,
    inc_res: str,
    same_type: bool,
    unit_rel: str,
    same_label: bool,
):
    """T-09: Parametric evaluation of can_overwrite and overwrite_block_reason."""
    policy = AttributePolicy()

    # Determine units
    if unit_rel == "same":
        ex_unit, inc_unit = "cm", "cm"
    elif unit_rel == "compatible":
        ex_unit, inc_unit = "cm", "mm"
    elif unit_rel == "incompatible":
        ex_unit, inc_unit = "cm", "kg"
    else:  # none
        ex_unit, inc_unit = None, None

    ex_type = "number"
    inc_type = "number" if same_type else "text"
    ex_label = "tinggi tanaman"
    inc_label = "tinggi tanaman" if same_label else "warna daun"

    exist = _make_attr(
        label=ex_label,
        value=80.0,
        value_type=ex_type,
        unit=ex_unit,
        resolution=ex_res,
    )
    incoming = _make_attr(
        label=inc_label,
        value=85.0 if inc_type == "number" else "delapan lima",
        value_type=inc_type,
        unit=inc_unit,
        resolution=inc_res,
    )

    reason = policy.overwrite_block_reason(exist, incoming)
    can_ow = policy.can_overwrite(exist, incoming)

    expected_allowed = (
        inc_res == "AUTO_ACCEPT"
        and ex_res == "AUTO_ACCEPT"
        and same_type
        and unit_rel in ("same", "compatible", "none")
        and same_label
    )

    assert can_ow is expected_allowed
    if expected_allowed:
        assert reason is None
    else:
        assert reason is not None
        # Verify reason priority code
        if inc_res != "AUTO_ACCEPT":
            assert reason == "INCOMING_NOT_AUTO_ACCEPT"
        elif ex_res != "AUTO_ACCEPT":
            assert reason == "EXISTING_HUMAN_PROTECTED"
        elif not same_type:
            assert reason == "TYPE_MISMATCH"
        elif unit_rel == "incompatible":
            assert reason == "UNIT_INCOMPATIBLE"
        elif not same_label:
            assert reason == "LABEL_INCOMPATIBLE"


def test_t10_existing_human_protected_from_auto_accept():
    """T-10: existing HUMAN_REVIEW + incoming AUTO_ACCEPT must return False with EXISTING_HUMAN_PROTECTED."""
    policy = AttributePolicy()
    exist = _make_attr(label="tinggi tanaman", value=80.0, resolution="HUMAN_REVIEW", unit="cm")
    incoming = _make_attr(label="tinggi tanaman", value=85.0, resolution="AUTO_ACCEPT", unit="cm")

    assert policy.can_overwrite(exist, incoming) is False
    assert policy.overwrite_block_reason(exist, incoming) == "EXISTING_HUMAN_PROTECTED"


def test_t11_legacy_test_4_still_passes():
    """T-11: Verify test_nilai_human_review_tidak_diturunkan_oleh_auto_accept passes."""
    from tests.storage.test_attribute_overwrite import (
        test_nilai_human_review_tidak_diturunkan_oleh_auto_accept,
    )
    test_nilai_human_review_tidak_diturunkan_oleh_auto_accept()


def test_t12_planner_existing_human_incoming_auto_creates_review_and_preserves_old():
    """T-12: (planner) existing HUMAN + incoming AUTO creates OVERWRITE_BLOCKED with reason_code EXISTING_HUMAN_PROTECTED."""
    policy = AttributePolicy()
    planner = DocumentPlanner(policy=policy)
    ar = AdministrativeRegistry()
    plant = PlantIdentity(id="plant_cabai_rawit", label="Cabai rawit", identity_level="species")
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    assert habitat is not None
    doc_key = f"{plant.id}:{habitat.id}"

    exist_attr = _make_attr(
        label="tinggi tanaman",
        value=80.0,
        value_type="number",
        unit="cm",
        resolution="HUMAN_REVIEW",
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
            "tinggi tanaman": "85.0 cm",
        }
    ]

    draft = planner.plan_records(
        records,
        current_documents={doc_key: base_doc},
        run_id="run_t12",
    )

    # Document attribute must be preserved as original 80.0 cm with HUMAN_REVIEW resolution
    planned_doc = draft.documents[doc_key]
    assert planned_doc.attributes["attr_tinggi_tanaman"].value == 80.0
    assert planned_doc.attributes["attr_tinggi_tanaman"].resolution == "HUMAN_REVIEW"

    # Exactly one review item of category OVERWRITE_BLOCKED
    ow_reviews = [r for r in draft.reviews if r.category == "OVERWRITE_BLOCKED"]
    assert len(ow_reviews) == 1
    rev = ow_reviews[0]
    assert rev.source_label == "tinggi tanaman"
    assert rev.target_document_key == doc_key
    assert rev.payload.get("reason_code") == "EXISTING_HUMAN_PROTECTED"
    assert rev.payload.get("old_value") == 80.0
    assert rev.payload.get("new_value") == 85.0
    assert "EXISTING_HUMAN_PROTECTED" in rev.notes
