from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.storage.document_contracts import (
    AdministrativePath,
    AttributeValue,
    CommitReceipt,
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    MediaReference,
    PhotoContextSignal,
    PhotoMismatchDecision,
    PlantIdentity,
    SamplingLocationDetail,
    VisionClassificationResult,
    validate_document,
)


# ============================================================================
# Criterion A02: Unique Identity Variety + Habitat Pair
# ============================================================================


def test_a02_knowledge_document_requires_both_variety_and_habitat(
    valid_knowledge_document_dict: dict[str, Any],
):
    """Knowledge document requires both valid plant variety and habitat identity."""
    doc = KnowledgeDocument.model_validate(valid_knowledge_document_dict)
    assert doc.variety.id == "plant_rawit_frutescens_001"
    assert doc.habitat.id == "hab_sleman_hargobinangun_001"

    # Reject document when variety is missing
    missing_variety = copy.deepcopy(valid_knowledge_document_dict)
    del missing_variety["variety"]
    with pytest.raises(ValidationError):
        KnowledgeDocument.model_validate(missing_variety)

    # Reject document when habitat is missing
    missing_habitat = copy.deepcopy(valid_knowledge_document_dict)
    del missing_habitat["habitat"]
    with pytest.raises(ValidationError):
        KnowledgeDocument.model_validate(missing_habitat)


def test_a02_document_draft_differentiates_same_variety_in_distinct_habitats(
    valid_knowledge_document_dict: dict[str, Any],
    valid_document_draft_dict: dict[str, Any],
):
    """Draft documents map distinguishes identical varieties located in different habitats."""
    doc1_payload = copy.deepcopy(valid_knowledge_document_dict)
    doc1_key = f"{doc1_payload['variety']['id']}:{doc1_payload['habitat']['id']}"

    # Create second document with identical variety but distinct habitat (Lamuk)
    doc2_payload = copy.deepcopy(valid_knowledge_document_dict)
    doc2_payload["habitat"]["id"] = "hab_wonosobo_lamuk_001"
    doc2_payload["habitat"]["label"] = "Desa Lamuk, Kecamatan Kalikajar, Kabupaten Wonosobo, Jawa Tengah"
    doc2_payload["habitat"]["administrative_path"]["regency_name"] = "Kabupaten Wonosobo"
    doc2_payload["habitat"]["administrative_path"]["district_name"] = "Kecamatan Kalikajar"
    doc2_payload["habitat"]["administrative_path"]["village_name"] = "Desa Lamuk"
    doc2_key = f"{doc2_payload['variety']['id']}:{doc2_payload['habitat']['id']}"

    draft_payload = copy.deepcopy(valid_document_draft_dict)
    draft_payload["documents"] = {
        doc1_key: doc1_payload,
        doc2_key: doc2_payload,
    }
    draft_payload["base_versions"] = {
        doc1_key: 1,
        doc2_key: 1,
    }

    draft = DocumentDraft.model_validate(draft_payload)
    assert len(draft.documents) == 2
    assert doc1_key in draft.documents
    assert doc2_key in draft.documents
    assert draft.documents[doc1_key].habitat.id != draft.documents[doc2_key].habitat.id


def test_a02_document_draft_rejects_key_mismatch_with_payload_identity(
    valid_document_draft_dict: dict[str, Any],
):
    """Draft rejects documents dictionary entries where key does not match variety_id:habitat_id."""
    invalid_draft_payload = copy.deepcopy(valid_document_draft_dict)
    # Tamper with the map key to cause mismatch against the inner document identity
    tampered_documents = {
        "mismatched_key_alias": invalid_draft_payload["documents"][list(invalid_draft_payload["documents"].keys())[0]]
    }
    invalid_draft_payload["documents"] = tampered_documents
    with pytest.raises(ValidationError):
        DocumentDraft.model_validate(invalid_draft_payload)


# ============================================================================
# Criterion A06: Plant Identity Level & Source Category Retention
# ============================================================================


def test_a06_plant_identity_level_source_category_retention():
    """Plant identity retains source-level categorization without fabricating cultivars."""
    plant = PlantIdentity(
        id="plant_rawit_frutescens",
        label="Cabai rawit (Capsicum frutescens L)",
        identity_level="source_category",
        scientific_name="Capsicum frutescens L",
    )
    assert plant.identity_level == "source_category"
    assert plant.label == "Cabai rawit (Capsicum frutescens L)"
    assert plant.scientific_name == "Capsicum frutescens L"


@pytest.mark.parametrize("level", ["source_category", "species", "cultivar"])
def test_a06_plant_identity_accepts_valid_identity_levels(level: str):
    """Plant identity accepts permitted taxonomic resolution levels."""
    plant = PlantIdentity(
        id=f"plant_{level}",
        label="Cabai Merah",
        identity_level=level,  # type: ignore[arg-type]
    )
    assert plant.identity_level == level


def test_a06_plant_identity_rejects_unsupported_identity_level():
    """Plant identity rejects arbitrary or fabricated identity levels."""
    with pytest.raises(ValidationError):
        PlantIdentity(
            id="plant_invalid",
            label="Cabai Hijau",
            identity_level="fabricated_cultivar",  # type: ignore[arg-type]
        )


def test_a06_plant_identity_field_constraints():
    """Plant identity enforces length constraints on identifiers and labels."""
    with pytest.raises(ValidationError):
        PlantIdentity(
            id="",  # Empty id rejected
            label="Cabai",
            identity_level="species",
        )
    with pytest.raises(ValidationError):
        PlantIdentity(
            id="plant_valid_id",
            label="",  # Empty label rejected
            identity_level="species",
        )


# ============================================================================
# Criterion A14: Latest-Only Knowledge Document Structure
# ============================================================================


def test_a14_knowledge_document_strictly_latest_only_rejects_historical_arrays(
    valid_knowledge_document_dict: dict[str, Any],
):
    """Knowledge document forbids previous_value, observations, or history collections."""
    for prohibited_key in ("previous_value", "observations", "history", "previous_values"):
        payload = copy.deepcopy(valid_knowledge_document_dict)
        payload[prohibited_key] = [{"value": 12.5}]
        with pytest.raises(ValidationError):
            KnowledgeDocument.model_validate(payload)


def test_a14_attribute_value_contains_single_current_source_no_history(
    valid_attribute_value_dict: dict[str, Any],
):
    """Attribute value contains only one current source reference and forbids historical fields."""
    attr = AttributeValue.model_validate(valid_attribute_value_dict)
    assert isinstance(attr.current_source, CurrentSourceReference)
    assert attr.current_source.sheet == "Resume Data"
    assert attr.current_source.row == 3
    assert attr.current_source.cell == "G3"

    # Reject historical fields inside AttributeValue
    for prohibited_key in ("previous_value", "observations", "history", "observation_list"):
        payload = copy.deepcopy(valid_attribute_value_dict)
        payload[prohibited_key] = "historical_trace"
        with pytest.raises(ValidationError):
            AttributeValue.model_validate(payload)


def test_a14_sampling_location_stores_metadata_without_embedded_measurements(
    valid_sampling_location_dict: dict[str, Any],
):
    """Sampling location details store geographical context without embedded measurement values."""
    loc = SamplingLocationDetail.model_validate(valid_sampling_location_dict)
    assert loc.location_ref == "loc_sleman_01"
    assert loc.hamlet == "Dusun Randu"
    assert loc.sampling_marker == "sampling 1"
    assert loc.coordinates == {"lat": -7.6321, "lon": 110.4215}

    # Location contract forbids measurement attributes injected into location records
    payload = copy.deepcopy(valid_sampling_location_dict)
    payload["measurements"] = {"ph": 7.0}
    with pytest.raises(ValidationError):
        SamplingLocationDetail.model_validate(payload)


# ============================================================================
# Criterion A15: Data Shapes (Blank No-op, 0/False Valid, Ranges Stored Unaveraged)
# ============================================================================


def test_a15_attribute_value_numeric_zero_is_valid(
    valid_attribute_value_dict: dict[str, Any],
):
    """Numeric zero is a valid measurement value and not discarded as empty or falsy."""
    payload = copy.deepcopy(valid_attribute_value_dict)
    payload["value_type"] = "number"
    payload["value"] = 0
    attr_int = AttributeValue.model_validate(payload)
    assert attr_int.value == 0
    assert attr_int.value_type == "number"

    payload["value"] = 0.0
    attr_float = AttributeValue.model_validate(payload)
    assert attr_float.value == 0.0


def test_a15_attribute_value_boolean_false_is_valid(
    valid_attribute_value_dict: dict[str, Any],
):
    """Boolean False is a valid attribute value and not discarded as falsy."""
    payload = copy.deepcopy(valid_attribute_value_dict)
    payload["value_type"] = "boolean"
    payload["value"] = False
    attr_bool = AttributeValue.model_validate(payload)
    assert attr_bool.value is False
    assert attr_bool.value_type == "boolean"


def test_a15_attribute_value_range_requires_min_max_dict(
    valid_attribute_value_dict: dict[str, Any],
):
    """Range values must be stored as structured min/max objects without automatic averaging."""
    payload = copy.deepcopy(valid_attribute_value_dict)
    payload["value_type"] = "range"
    payload["value"] = {"min": 28.3, "max": 30.5}
    payload["unit"] = "oC"
    attr_range = AttributeValue.model_validate(payload)
    assert attr_range.value == {"min": 28.3, "max": 30.5}
    assert attr_range.value["min"] <= attr_range.value["max"]


def test_a15_attribute_value_range_rejects_inverted_or_single_number(
    valid_attribute_value_dict: dict[str, Any],
):
    """Range value shape rejects inverted min/max bounds and scalar averaged values."""
    payload = copy.deepcopy(valid_attribute_value_dict)
    payload["value_type"] = "range"

    # Inverted range (min > max) must be rejected
    payload["value"] = {"min": 30.5, "max": 28.3}
    with pytest.raises(ValidationError):
        AttributeValue.model_validate(payload)

    # Scalar average passed for range type must be rejected
    payload["value"] = 29.4
    with pytest.raises(ValidationError):
        AttributeValue.model_validate(payload)

    # Raw string range passed for structured range type must be rejected
    payload["value"] = "28.3 - 30.5"
    with pytest.raises(ValidationError):
        AttributeValue.model_validate(payload)


def test_a15_attribute_value_rejects_nan_and_infinite_numbers(
    valid_attribute_value_dict: dict[str, Any],
):
    """Attribute values reject NaN and infinity values for number and range types."""
    payload = copy.deepcopy(valid_attribute_value_dict)
    payload["value_type"] = "number"

    for invalid_num in (math.nan, float("inf"), float("-inf")):
        payload["value"] = invalid_num
        with pytest.raises(ValidationError):
            AttributeValue.model_validate(payload)


def test_a15_attribute_value_list_and_text_validation(
    valid_attribute_value_dict: dict[str, Any],
):
    """Attribute value validates non-empty list and non-empty text strings."""
    payload = copy.deepcopy(valid_attribute_value_dict)

    # List validation
    payload["value_type"] = "list"
    payload["value"] = ["merah", "hijau", "kuning"]
    attr_list = AttributeValue.model_validate(payload)
    assert attr_list.value == ["merah", "hijau", "kuning"]

    # Empty list rejected
    payload["value"] = []
    with pytest.raises(ValidationError):
        AttributeValue.model_validate(payload)

    # Empty text string rejected
    payload["value_type"] = "text"
    payload["value"] = "   "
    with pytest.raises(ValidationError):
        AttributeValue.model_validate(payload)


# ============================================================================
# Criterion A23: Multi-Signal Photo Context Signal & Vision Result
# ============================================================================


def test_a23_photo_context_signal_fields_and_extracted_parts():
    """PhotoContextSignal captures file metadata, caption, extracted parts, and hint tokens."""
    signal = PhotoContextSignal(
        filename="cabai_rawit_daun_01.jpg",
        caption="Pengambilan sampel permukaan daun Dusun Randu",
        extracted_part="DAUN",
        suggested_variety_hint="Cabai rawit",
        raw_tokens=["cabai", "rawit", "daun", "01"],
    )
    assert signal.filename == "cabai_rawit_daun_01.jpg"
    assert signal.extracted_part == "DAUN"
    assert signal.suggested_variety_hint == "Cabai rawit"
    assert len(signal.raw_tokens) == 4


def test_a23_vision_classification_result_three_signals_and_options():
    """VisionClassificationResult models visual evidence, candidate options, and consistency."""
    result = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai rawit (Capsicum frutescens L)",
        identified_part="DAUN",
        visual_confidence=0.92,
        text_confidence=0.88,
        confidence=0.90,
        visual_evidence="Bentuk daun ovate dengan permukaan mengkilap khas Capsicum frutescens L",
        options_evaluated=[
            "Cabai rawit (Capsicum frutescens L)",
            "cabai besar (Capsicum annum L)",
        ],
        signals_consistent=True,
    )
    assert result.classification_status == "KNOWN"
    assert result.identified_part == "DAUN"
    assert result.visual_confidence >= 0.85
    assert result.signals_consistent is True
    assert len(result.options_evaluated) == 2


@pytest.mark.parametrize("bad_conf", [-0.1, 1.05, 2.0])
def test_a23_vision_classification_confidence_bounds_enforced(bad_conf: float):
    """Vision confidence scores must stay strictly within [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        VisionClassificationResult(
            classification_status="KNOWN",
            matched_variety="Cabai rawit",
            identified_part="DAUN",
            visual_confidence=bad_conf,
            text_confidence=0.5,
            confidence=0.5,
            visual_evidence="Valid evidence text",
        )


# ============================================================================
# Criterion A24: Photo Variety Mismatch Review Item (Fail-Closed)
# ============================================================================


def test_a24_document_review_item_supports_photo_variety_mismatch():
    """DocumentReviewItem supports PHOTO_VARIETY_MISMATCH category with null target key for unassigned photos."""
    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_001",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="cabai_merah_argalingga_01.jpg",
        source_context="Citra buah terdeteksi NO_MATCH terhadap opsi Excel run aktif",
        raw_values=["asset_sha256_7b3a9f0001"],
        candidate_resolutions=[
            {"action": "ASSIGN_EXISTING", "label": "Tetapkan ke varietas run aktif"},
            {"action": "CREATE_NEW_DOCUMENT", "label": "Buatkan dokumen baru"},
            {"action": "DISCARD", "label": "Tolak citra secara non-destruktif"},
        ],
        status="pending",
    )
    assert review_item.category == "PHOTO_VARIETY_MISMATCH"
    assert review_item.status == "pending"
    assert review_item.target_document_key is None


# ============================================================================
# Criterion A25: Photo Review Action ASSIGN_EXISTING
# ============================================================================


def test_a25_photo_mismatch_decision_assign_existing():
    """ASSIGN_EXISTING action validates target variety and habitat selection."""
    decision = PhotoMismatchDecision(
        action="ASSIGN_EXISTING",
        selected_variety_id="plant_rawit_frutescens_001",
        selected_variety_label="Cabai rawit (Capsicum frutescens L)",
        target_habitat_id="hab_sleman_hargobinangun_001",
        notes="Ditetapkan kurator ke varietas terdaftar pada run aktif",
    )
    assert decision.action == "ASSIGN_EXISTING"
    assert decision.selected_variety_id == "plant_rawit_frutescens_001"
    assert decision.target_habitat_id == "hab_sleman_hargobinangun_001"


def test_a25_media_reference_hitl_linking_contract():
    """MediaReference records provenance and assignment mode when linked via review."""
    media = MediaReference(
        asset_id="b" * 64,
        organ_part="buah",
        caption="Buah cabai rawit merah masak",
        source_filename="cabai_buah_01.jpg",
        provenance_run_id="run_20260923_002",
        assigned_via="HITL_REVIEW",
        resolution_status="linked",
    )
    assert media.assigned_via == "HITL_REVIEW"
    assert media.resolution_status == "linked"
    assert media.organ_part == "buah"


# ============================================================================
# Criterion A26: Photo Review Action CREATE_NEW_DOCUMENT
# ============================================================================


def test_a26_photo_mismatch_decision_create_new_document():
    """CREATE_NEW_DOCUMENT action validates new variety name, identity level, and habitat."""
    decision = PhotoMismatchDecision(
        action="CREATE_NEW_DOCUMENT",
        new_variety_name="Cabai Keriting Lokal",
        identity_level="cultivar",
        target_habitat_id="hab_sleman_hargobinangun_001",
        notes="Varietas baru ditemukan pada foto lapangan",
    )
    assert decision.action == "CREATE_NEW_DOCUMENT"
    assert decision.new_variety_name == "Cabai Keriting Lokal"
    assert decision.identity_level == "cultivar"


# ============================================================================
# Criterion A27: Photo Review Action DISCARD Non-Destructive
# ============================================================================


def test_a27_photo_mismatch_decision_discard_non_destructive():
    """DISCARD action preserves discard reason and rejection notes without physical purge."""
    decision = PhotoMismatchDecision(
        action="DISCARD",
        discard_reason="Foto buram / Bukan objek tanaman cabai",
        notes="Foto tidak memenuhi standar identifikasi morfologi",
    )
    assert decision.action == "DISCARD"
    assert decision.discard_reason == "Foto buram / Bukan objek tanaman cabai"


def test_a27_media_reference_supports_discarded_resolution_status():
    """MediaReference supports discarded resolution status for non-destructive retention."""
    media = MediaReference(
        asset_id="c" * 64,
        organ_part="daun",
        source_filename="foto_blur_tanah.jpg",
        provenance_run_id="run_20260923_003",
        assigned_via="HITL_REVIEW",
        resolution_status="discarded",
    )
    assert media.resolution_status == "discarded"


# ============================================================================
# General / Additional Contract Validation & Commit Receipt
# ============================================================================


def test_validate_document_function_success_and_model_dump_roundtrip(
    valid_knowledge_document_dict: dict[str, Any],
):
    """validate_document returns validated KnowledgeDocument instance matching input structure."""
    doc = validate_document(valid_knowledge_document_dict)
    assert isinstance(doc, KnowledgeDocument)
    assert doc.schema_version == "kms-document-v1"
    assert doc.variety.id == "plant_rawit_frutescens_001"
    assert doc.habitat.id == "hab_sleman_hargobinangun_001"
    assert "attr_chlorophyll_spad" in doc.attributes

    # Idempotent re-validation
    doc_again = validate_document(doc)
    assert doc_again.variety.id == doc.variety.id


def test_validate_document_rejects_missing_required_sections(
    valid_knowledge_document_dict: dict[str, Any],
):
    """validate_document raises ValidationError when required top-level keys are absent."""
    for required_key in ("variety", "habitat", "attributes"):
        payload = copy.deepcopy(valid_knowledge_document_dict)
        del payload[required_key]
        with pytest.raises(ValidationError):
            validate_document(payload)


def test_validate_document_rejects_unsupported_schema_version(
    valid_knowledge_document_dict: dict[str, Any],
):
    """validate_document rejects unsupported schema versions."""
    payload = copy.deepcopy(valid_knowledge_document_dict)
    payload["schema_version"] = "kms-document-v999"
    with pytest.raises(ValidationError):
        validate_document(payload)


def test_commit_receipt_contract_metrics():
    """CommitReceipt validates execution counters, timestamps, and replay state."""
    receipt = CommitReceipt(
        run_id="run_commit_001",
        revision=1,
        documents_created=2,
        documents_updated=0,
        documents_unchanged=0,
        reviews_resolved=3,
        attributes_committed=14,
        media_linked=2,
        media_discarded=1,
        replayed=False,
        committed_at=datetime.now(timezone.utc),
    )
    assert receipt.documents_created == 2
    assert receipt.reviews_resolved == 3
    assert receipt.media_linked == 2
    assert receipt.media_discarded == 1
    assert receipt.replayed is False


def test_habitat_identity_and_administrative_path_contract(
    valid_habitat_identity_dict: dict[str, Any],
):
    """HabitatIdentity models four-tier administrative hierarchy strictly."""
    habitat = HabitatIdentity.model_validate(valid_habitat_identity_dict)
    assert habitat.definition == "administrative_village_v1"
    assert habitat.administrative_path.province_name == "Daerah Istimewa Yogyakarta"
    assert habitat.administrative_path.regency_name == "Kabupaten Sleman"
    assert habitat.administrative_path.district_name == "Kecamatan Pakem"
    assert habitat.administrative_path.village_name == "Desa Hargobinangun"


# ============================================================================
# Real Workbook Fixture Cell Parity Verification
# ============================================================================


def test_workbook_fixture_cell_parity_with_specification(
    resume_data_workbook_path: Path,
):
    """Verify that sample workbook data_input.xlsx Resume Data cells strictly match TECH_PLAN."""
    import openpyxl

    assert resume_data_workbook_path.exists(), f"Workbook not found at {resume_data_workbook_path}"
    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    assert "Resume Data" in wb.sheetnames, "Resume Data sheet missing from workbook"
    ws = wb["Resume Data"]

    # Verify administrative sampling addresses
    assert "Dusun Randu, Desa Hargobinangun" in str(ws["B3"].value)
    assert "Dusun Tenen, Desa Hargobinangun" in str(ws["B4"].value)
    assert "Desa Pengilon, Kecamatan Bulu, Kab. Temanggung" in str(ws["B9"].value)
    assert "Desa Pengilon, Kecamatan Bulu, Kab. Temanggung" in str(ws["B10"].value)
    assert "Dusun Pangempon, Desa Lamuk, Kec. Kalikajar, Kabupaten Wonosobo" in str(ws["B12"].value)
    assert "Dusun Genting, Desa Lamuk, Kec. Kalikajar, Kabupaten Wonosobo" in str(ws["B13"].value)
    assert "Desa Argalingga, Kec. Argapura, Kabupaten Majalengka" in str(ws["B14"].value)
    assert "Desa Argalingga, Kec. Argapura, Kabupaten Majalengka" in str(ws["B15"].value)

    # Verify variety source categories
    assert ws["F3"].value == "Cabai rawit (Capsicum frutescens L)"
    assert ws["F4"].value == "cabai besar (Capsicum annum L)"
    assert ws["F12"].value == "Cabai rawit (Capsicum frutescens L)"
    assert ws["F13"].value == "Cabai rawit (Capsicum frutescens L)"
    assert ws["F14"].value == "cabai besar (Capsicum annum L)"
    assert ws["F15"].value == "cabai besar (Capsicum annum L)"

    # Verify intra-run numeric values for chlorophyll conflict fixtures
    assert float(ws["G12"].value) == pytest.approx(49.02)
    assert float(ws["G13"].value) == pytest.approx(46.541666666666664)
    assert float(ws["G14"].value) == pytest.approx(47.09)
    assert float(ws["G15"].value) == pytest.approx(45.620000000000005)

    # Verify elevation and pH
    assert int(ws["E3"].value) == 573
    assert int(ws["E4"].value) == 598
    assert float(ws["L3"].value) == pytest.approx(7.0)
    assert float(ws["L4"].value) == pytest.approx(6.8)

    # Verify dynamic ecology attributes and string ranges
    assert ws["K2"].value == "Kelembaban tanah (%)"
    assert ws["K3"].value == 58
    assert ws["L2"].value == "pH tanah"
    assert ws["M2"].value == "Suhu udara (0C)"
    assert ws["M3"].value == "28.3 - 30.5"
    assert ws["N2"].value == "Kelembaban udara (%)"
    assert ws["N3"].value == "72 - 67"
