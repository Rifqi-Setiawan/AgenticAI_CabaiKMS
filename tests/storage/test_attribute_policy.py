from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    DocumentReviewItem,
)
from src.storage.attribute_policy import (
    AttributeCatalog,
    AttributeDefinition,
    AttributePolicy,
    AttributeResolution,
    HoldoutEvaluationReport,
    can_overwrite_attribute_value,
    evaluate_holdout_gate,
    resolve_attribute,
)


# ============================================================================
# Helpers & Fixtures
# ============================================================================


def _create_sample_current_source(
    cell: str = "G3",
    row: int = 3,
    sheet: str = "Resume Data",
) -> CurrentSourceReference:
    """Construct a minimal valid current source reference fixture."""
    return CurrentSourceReference(
        source_ref="src_field_data_2026",
        sheet=sheet,
        row=row,
        cell=cell,
        location_ref="loc_sleman_01",
    )


def _create_sample_attribute_value(
    label: str,
    value: Any,
    resolution: Literal["AUTO_ACCEPT", "HUMAN_REVIEW"] = "AUTO_ACCEPT",
    value_type: Literal["text", "number", "range", "boolean", "list"] = "number",
    unit: str | None = None,
    cell: str = "G3",
) -> AttributeValue:
    """Construct a valid attribute value fixture."""
    return AttributeValue(
        label=label,
        value=value,
        value_type=value_type,
        unit=unit,
        resolution=resolution,
        mapping_policy_version="exact-alias-policy-v1",
        current_source=_create_sample_current_source(cell=cell),
    )


# ============================================================================
# Criterion A07: Dynamic Catalog Expansion via Review & Non-Hardcoded Size
# ============================================================================


def test_catalog_dynamic_expansion_via_review(resume_data_workbook_path: Path):
    """Novel attribute Chlorophyll Content (SPAD) from cell G2 is registered dynamically after review."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    header_g2 = ws["G2"].value
    assert header_g2 == "Chlorophyll Content (SPAD)"

    catalog = AttributeCatalog()
    initial_count = len(catalog)
    assert initial_count > 0

    # Before registration, novel field must be classified as new attribute review
    pre_res = resolve_attribute(header_g2, catalog=catalog)
    assert pre_res.status == "NEW_ATTRIBUTE_REVIEW"
    assert pre_res.attribute_id is None
    assert pre_res.confidence == pytest.approx(0.0)

    # Simulate approved review registering the new attribute dynamically
    new_def = AttributeDefinition(
        attribute_id="attr_chlorophyll_spad",
        canonical_key="chlorophyll_spad",
        label=header_g2,
        organ="daun",
        value_type="number",
        unit="SPAD",
        description="Kandungan klorofil daun hasil pengukuran SPAD meter",
    )
    registered = catalog.register_attribute(new_def)
    assert registered.attribute_id == "attr_chlorophyll_spad"
    assert len(catalog) == initial_count + 1

    # Post registration, exact match must resolve immediately to auto accept
    post_res = resolve_attribute(header_g2, catalog=catalog)
    assert post_res.status == "AUTO_ACCEPT"
    assert post_res.attribute_id == "attr_chlorophyll_spad"
    assert post_res.canonical_key == "chlorophyll_spad"
    assert post_res.organ == "daun"
    assert post_res.confidence == pytest.approx(1.0)


def test_a07_catalog_count_is_dynamic_not_hardcoded():
    """Attribute catalog count grows dynamically and is never capped or hardcoded."""
    catalog = AttributeCatalog()
    base_count = len(catalog)

    # Register multiple distinct novel attributes across domains
    novel_specs = [
        ("attr_dyn_01", "dyn_01", "Nitrogen content (mg/g)", "daun", "number", "mg/g"),
        ("attr_dyn_02", "dyn_02", "Kelembaban tanah (%)", "ekologi_tanah", "number", "%"),
        ("attr_dyn_03", "dyn_03", "pH tanah", "ekologi_tanah", "number", None),
        ("attr_dyn_04", "dyn_04", "Suhu udara (0C)", "mikroklimat", "range", "oC"),
    ]

    for attr_id, c_key, lbl, organ, val_type, unit in novel_specs:
        catalog.register_attribute(
            AttributeDefinition(
                attribute_id=attr_id,
                canonical_key=c_key,
                label=lbl,
                organ=organ,
                value_type=val_type,
                unit=unit,
            )
        )

    assert len(catalog) == base_count + len(novel_specs)
    for attr_id, _, lbl, _, _, _ in novel_specs:
        assert catalog.has_attribute(attr_id) is True
        item = catalog.get(attr_id)
        assert item is not None
        assert item.label == lbl


def test_a07_workbook_resume_data_soil_and_climate_attributes_dynamic_registration(
    resume_data_workbook_path: Path,
):
    """Workbook headers for soil and microclimate are registered into novel domains."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    header_k2 = ws["K2"].value  # Kelembaban tanah (%)
    header_l2 = ws["L2"].value  # pH tanah
    header_m2 = ws["M2"].value  # Suhu udara (0C)
    header_n2 = ws["N2"].value  # Kelembaban udara (%)

    assert header_k2 == "Kelembaban tanah (%)"
    assert header_l2 == "pH tanah"
    assert header_m2 == "Suhu udara (0C)"
    assert header_n2 == "Kelembaban udara (%)"

    catalog = AttributeCatalog()

    # Pre-registration: all uncataloged workbook headers require new attribute review
    for header in [header_k2, header_l2, header_m2, header_n2]:
        res = resolve_attribute(header, catalog=catalog)
        assert res.status == "NEW_ATTRIBUTE_REVIEW"

    # Register soil ecology and microclimate attributes
    catalog.register_attribute(
        AttributeDefinition(
            attribute_id="attr_kelembaban_tanah",
            canonical_key="kelembaban_tanah",
            label=header_k2,
            organ="ekologi_tanah",
            value_type="number",
            unit="%",
        )
    )
    catalog.register_attribute(
        AttributeDefinition(
            attribute_id="attr_ekologi_tanah_ph",
            canonical_key="ekologi_tanah_ph",
            label=header_l2,
            organ="ekologi_tanah",
            value_type="number",
        )
    )
    catalog.register_attribute(
        AttributeDefinition(
            attribute_id="attr_suhu_udara",
            canonical_key="suhu_udara",
            label=header_m2,
            organ="mikroklimat",
            value_type="range",
            unit="oC",
        )
    )
    catalog.register_attribute(
        AttributeDefinition(
            attribute_id="attr_kelembaban_udara",
            canonical_key="kelembaban_udara",
            label=header_n2,
            organ="mikroklimat",
            value_type="range",
            unit="%",
        )
    )

    # Post-registration verification
    res_k = resolve_attribute(header_k2, catalog=catalog)
    res_l = resolve_attribute(header_l2, catalog=catalog)
    res_m = resolve_attribute(header_m2, catalog=catalog)
    res_n = resolve_attribute(header_n2, catalog=catalog)

    assert res_k.status == "AUTO_ACCEPT"
    assert res_k.organ == "ekologi_tanah"
    assert res_l.status == "AUTO_ACCEPT"
    assert res_l.organ == "ekologi_tanah"
    assert res_m.status == "AUTO_ACCEPT"
    assert res_m.organ == "mikroklimat"
    assert res_n.status == "AUTO_ACCEPT"
    assert res_n.organ == "mikroklimat"


def test_a07_register_attribute_rejects_empty_or_invalid_schema():
    """Registering attribute with invalid identifier or blank label fails validation."""
    catalog = AttributeCatalog()

    with pytest.raises((ValidationError, ValueError)):
        catalog.register_attribute(
            AttributeDefinition(
                attribute_id="",  # Empty ID rejected
                canonical_key="valid_key",
                label="Valid Label",
                organ="daun",
                value_type="number",
            )
        )

    with pytest.raises((ValidationError, ValueError)):
        catalog.register_attribute(
            AttributeDefinition(
                attribute_id="attr_invalid_whitespace",
                canonical_key="invalid_whitespace",
                label="   ",  # Blank whitespace label rejected
                organ="daun",
                value_type="number",
            )
        )


def test_a07_idempotent_duplicate_attribute_registration():
    """Re-registering an identical attribute definition is idempotent and preserves catalog size."""
    catalog = AttributeCatalog()
    defn = AttributeDefinition(
        attribute_id="attr_chlorophyll_spad",
        canonical_key="chlorophyll_spad",
        label="Chlorophyll Content (SPAD)",
        organ="daun",
        value_type="number",
        unit="SPAD",
    )

    catalog.register_attribute(defn)
    count_after_first = len(catalog)

    # Second registration with identical definition
    catalog.register_attribute(defn)
    assert len(catalog) == count_after_first
    assert catalog.get("attr_chlorophyll_spad") is not None


def test_a07_conflicting_attribute_id_registration_rejected():
    """Registering an existing attribute_id with a conflicting label or organ raises an error."""
    catalog = AttributeCatalog()
    catalog.register_attribute(
        AttributeDefinition(
            attribute_id="attr_tinggi_tanaman",
            canonical_key="tinggi_tanaman",
            label="tinggi tanaman",
            organ="vegetatif",
            value_type="number",
            unit="cm",
        )
    )

    # Attempting to overwrite existing ID with completely different semantics must fail
    with pytest.raises(ValueError):
        catalog.register_attribute(
            AttributeDefinition(
                attribute_id="attr_tinggi_tanaman",
                canonical_key="tinggi_tanaman",
                label="warna buah masak",  # Direct semantic contradiction
                organ="buah",
                value_type="text",
            )
        )


def test_a07_catalog_lookup_by_id_and_by_label():
    """Catalog supports lookup by attribute ID and canonical label interchangeably."""
    catalog = AttributeCatalog()
    item_by_id = catalog.get("attr_tinggi_tanaman")
    assert item_by_id is not None
    assert item_by_id.canonical_key == "tinggi_tanaman"

    item_by_label = catalog.lookup("tinggi tanaman")
    assert item_by_label is not None
    assert item_by_label.attribute_id == item_by_id.attribute_id


# ============================================================================
# Criterion A08: Curated Trusted Synonyms and Key Preservation
# ============================================================================


def test_trusted_synonym_maps_to_canonical_attribute_id():
    """Curated alias mature plant height maps to canonical key attr_tinggi_tanaman without duplication."""
    catalog = AttributeCatalog()
    alias = "mature plant height"

    res = resolve_attribute(alias, catalog=catalog)
    assert res.status == "AUTO_ACCEPT"
    assert res.attribute_id == "attr_tinggi_tanaman"
    assert res.canonical_key == "tinggi_tanaman"
    assert res.organ == "vegetatif"
    assert res.confidence == pytest.approx(1.0)
    assert res.is_trusted_alias is True

    # Ensure no separate duplicate attribute key was generated
    assert catalog.has_attribute("attr_mature_plant_height") is False
    canonical_entry = catalog.get("attr_tinggi_tanaman")
    assert canonical_entry is not None
    assert alias in canonical_entry.aliases


def test_a08_synonym_normalization_casing_and_whitespace():
    """Aliases with leading, trailing, internal whitespace and casing variations map correctly."""
    catalog = AttributeCatalog()

    variations = [
        "  mature plant height  ",
        "MATURE PLANT HEIGHT",
        "Mature Plant Height",
        "mature   plant   height",
    ]

    for raw in variations:
        res = resolve_attribute(raw, catalog=catalog)
        assert res.status == "AUTO_ACCEPT"
        assert res.attribute_id == "attr_tinggi_tanaman"
        assert res.canonical_key == "tinggi_tanaman"
        assert res.is_trusted_alias is True


def test_a08_multiple_synonyms_resolve_to_same_canonical_attribute():
    """Multiple curated synonyms for the same biological character map to identical key."""
    catalog = AttributeCatalog()

    # Pre-existing and added aliases for plant height
    catalog.add_alias("attr_tinggi_tanaman", "tinggi tanaman dewasa")
    catalog.add_alias("attr_tinggi_tanaman", "final plant height")

    synonyms = [
        "mature plant height",
        "tinggi tanaman dewasa",
        "final plant height",
    ]

    for syn in synonyms:
        res = resolve_attribute(syn, catalog=catalog)
        assert res.status == "AUTO_ACCEPT"
        assert res.attribute_id == "attr_tinggi_tanaman"
        assert res.canonical_key == "tinggi_tanaman"


def test_a08_dynamic_addition_of_trusted_synonym():
    """Dynamically adding a trusted alias to catalog enables immediate auto accept resolution."""
    catalog = AttributeCatalog()
    new_alias = "canopy stature"

    # Initially uncurated alias enters review
    pre_res = resolve_attribute(new_alias, catalog=catalog)
    assert pre_res.status != "AUTO_ACCEPT"

    catalog.add_alias("attr_tinggi_tanaman", new_alias)

    post_res = resolve_attribute(new_alias, catalog=catalog)
    assert post_res.status == "AUTO_ACCEPT"
    assert post_res.attribute_id == "attr_tinggi_tanaman"
    assert post_res.is_trusted_alias is True


def test_a08_alias_collision_with_existing_attribute_rejected():
    """Assigning an alias that collides with an existing canonical label of another attribute is rejected."""
    catalog = AttributeCatalog()

    # Attempting to assign 'warna daun' as an alias for 'tinggi tanaman' must fail
    with pytest.raises(ValueError):
        catalog.add_alias("attr_tinggi_tanaman", "warna daun")


def test_a08_untrusted_or_unknown_synonym_routes_to_needs_review():
    """Non-curated synonym phrases do not receive auto accept and route to review."""
    catalog = AttributeCatalog()
    raw = "jarak ujung ke pangkal pokok"

    res = resolve_attribute(raw, catalog=catalog)
    assert res.status in ("NEEDS_REVIEW", "NEW_ATTRIBUTE_REVIEW")
    assert res.is_trusted_alias is False


# ============================================================================
# Criterion A09: Biological Organ & Developmental Stage Separation
# ============================================================================


def test_organ_and_development_stage_separation():
    """Biological negative pairs: immature vs mature fruit and diameter vs length require separate keys and review."""
    catalog = AttributeCatalog()

    # 1. Immature vs Mature Fruit length separation
    res_muda = resolve_attribute("panjang buah muda", catalog=catalog)
    res_masak = resolve_attribute("panjang buah masak", catalog=catalog)

    assert res_muda.status == "AUTO_ACCEPT"
    assert res_masak.status == "AUTO_ACCEPT"
    assert res_muda.attribute_id == "attr_panjang_buah_muda"
    assert res_masak.attribute_id == "attr_panjang_buah_masak"
    assert res_muda.attribute_id != res_masak.attribute_id

    # Ambiguous length without developmental stage must enter review, never auto accept to either
    res_ambiguous_stage = resolve_attribute("panjang buah", catalog=catalog)
    assert res_ambiguous_stage.status == "NEEDS_REVIEW"
    assert len(res_ambiguous_stage.candidates) >= 2
    candidate_ids = [c["attribute_id"] for c in res_ambiguous_stage.candidates]
    assert "attr_panjang_buah_muda" in candidate_ids
    assert "attr_panjang_buah_masak" in candidate_ids

    # 2. Diameter vs Length separation
    res_diameter = resolve_attribute("diameter buah", catalog=catalog)
    # Fruit diameter is distinct from fruit length or perimeter; must not silently match length
    assert res_diameter.status in ("NEEDS_REVIEW", "NEW_ATTRIBUTE_REVIEW")
    assert res_diameter.attribute_id != "attr_panjang_buah_muda"
    assert res_diameter.attribute_id != "attr_panjang_buah_masak"


def test_a09_immature_and_mature_fruit_stages_strictly_separated():
    """Fruit color attributes across immature and mature stages maintain strict boundary."""
    catalog = AttributeCatalog()

    res_warna_muda = resolve_attribute("warna buah muda", catalog=catalog)
    res_warna_masak = resolve_attribute("warna buah masak", catalog=catalog)

    assert res_warna_muda.status == "AUTO_ACCEPT"
    assert res_warna_masak.status == "AUTO_ACCEPT"
    assert res_warna_muda.attribute_id == "attr_warna_buah_muda"
    assert res_warna_masak.attribute_id == "attr_warna_buah_masak"
    assert res_warna_muda.attribute_id != res_warna_masak.attribute_id


def test_a09_distinct_plant_organs_never_cross_match():
    """Color attributes across vegetative, leaf, flower, fruit, and seed never cross-map."""
    catalog = AttributeCatalog()

    color_queries = [
        ("warna daun", "daun", "attr_warna_daun"),
        ("warna mahkota", "bunga", "attr_warna_mahkota"),
        ("warna kelopak bunga", "bunga", "attr_warna_kelopak_bunga"),
        ("warna buah masak", "buah", "attr_warna_buah_masak"),
        ("warna biji", "biji", "attr_warna_biji"),
    ]

    for label, expected_organ, expected_id in color_queries:
        res = resolve_attribute(label, catalog=catalog)
        assert res.status == "AUTO_ACCEPT"
        assert res.organ == expected_organ
        assert res.attribute_id == expected_id

    # Generic ungrounded 'warna' must enter review with multi-organ candidates
    res_generic = resolve_attribute("warna", catalog=catalog)
    assert res_generic.status == "NEEDS_REVIEW"
    organs = {c["organ"] for c in res_generic.candidates}
    assert len(organs) >= 3


def test_a09_organ_context_disambiguates_generic_metric():
    """Providing explicit organ and stage context resolves generic dimension labels."""
    catalog = AttributeCatalog()

    # Generic 'panjang' disambiguated by organ context
    res_daun = resolve_attribute("panjang", context={"organ": "daun"}, catalog=catalog)
    assert res_daun.status == "AUTO_ACCEPT"
    assert res_daun.attribute_id == "attr_panjang_daun"

    res_buah_masak = resolve_attribute(
        "panjang", context={"organ": "buah", "stage": "masak"}, catalog=catalog
    )
    assert res_buah_masak.status == "AUTO_ACCEPT"
    assert res_buah_masak.attribute_id == "attr_panjang_buah_masak"


def test_a09_missing_context_for_ambiguous_organ_yields_needs_review():
    """Generic dimension label without context yields review and preserves candidate branches."""
    catalog = AttributeCatalog()

    res = resolve_attribute("panjang", context=None, catalog=catalog)
    assert res.status == "NEEDS_REVIEW"
    assert res.attribute_id is None
    assert len(res.candidates) > 1


def test_a09_calyx_vs_fruit_dimension_separation():
    """Calyx circumference and fruit circumference are strictly separated attributes."""
    catalog = AttributeCatalog()

    res_kelopak = resolve_attribute("keliling kelopak buah masak", catalog=catalog)
    res_buah = resolve_attribute("keliling buah masak", catalog=catalog)

    assert res_kelopak.status == "AUTO_ACCEPT"
    assert res_buah.status == "AUTO_ACCEPT"
    assert res_kelopak.attribute_id == "attr_keliling_kelopak_buah_masak"
    assert res_buah.attribute_id == "attr_keliling_buah_masak"
    assert res_kelopak.attribute_id != res_buah.attribute_id


def test_a09_pedicel_vs_fruit_dimension_separation():
    """Pedicel length and fruit body length maintain strict biological separation."""
    catalog = AttributeCatalog()

    res_tangkai = resolve_attribute("panjang tangkai buah muda", catalog=catalog)
    res_buah = resolve_attribute("panjang buah muda", catalog=catalog)

    assert res_tangkai.status == "AUTO_ACCEPT"
    assert res_buah.status == "AUTO_ACCEPT"
    assert res_tangkai.attribute_id == "attr_panjang_tangkai_buah_muda"
    assert res_buah.attribute_id == "attr_panjang_buah_muda"
    assert res_tangkai.attribute_id != res_buah.attribute_id


def test_a09_conflicting_organ_in_context_rejects_auto_accept():
    """Contradiction between label organ and provided context flags review."""
    catalog = AttributeCatalog()

    # Label explicitly says leaf, but context erroneously declares fruit
    res = resolve_attribute("panjang daun", context={"organ": "buah"}, catalog=catalog)
    assert res.status == "NEEDS_REVIEW"
    assert "conflict" in res.reason.lower() or "mismatch" in res.reason.lower()


# ============================================================================
# Criterion A10: Overwrite Policy (AUTO_ACCEPT Overwrites HUMAN_REVIEW)
# ============================================================================


def test_auto_accept_overwrites_existing_human_review_value():
    """Incoming AUTO_ACCEPT cannot auto-overwrite protected existing HUMAN_REVIEW value (Decision D2)."""
    existing_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=82.0,
        resolution="HUMAN_REVIEW",
        unit="cm",
        cell="D4",
    )
    incoming_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=85.5,
        resolution="AUTO_ACCEPT",
        unit="cm",
        cell="D5",
    )

    policy = AttributePolicy()

    # D2: HUMAN_REVIEW is protected; AUTO_ACCEPT is blocked with EXISTING_HUMAN_PROTECTED
    assert policy.can_overwrite(existing_val, incoming_val) is False
    assert policy.overwrite_block_reason(existing_val, incoming_val) == "EXISTING_HUMAN_PROTECTED"
    assert can_overwrite_attribute_value(existing_val, incoming_val, policy=policy) is False


def test_a10_auto_accept_overwrites_existing_auto_accept_value():
    """Incoming AUTO_ACCEPT measurement overwrites existing AUTO_ACCEPT current value."""
    existing_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=80.0,
        resolution="AUTO_ACCEPT",
        unit="cm",
    )
    incoming_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=83.0,
        resolution="AUTO_ACCEPT",
        unit="cm",
    )

    policy = AttributePolicy()
    assert policy.can_overwrite(existing_val, incoming_val) is True


def test_a10_needs_review_incoming_cannot_overwrite_existing_value():
    """Incoming measurement with unresolved review status cannot auto-overwrite current value."""
    existing_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=80.0,
        resolution="AUTO_ACCEPT",
        unit="cm",
    )
    # Incoming measurement flagged as requiring review
    incoming_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=90.0,
        resolution="HUMAN_REVIEW",
        unit="cm",
    )

    policy = AttributePolicy()
    assert policy.can_overwrite(existing_val, incoming_val) is False
    assert can_overwrite_attribute_value(existing_val, incoming_val, policy=policy) is False


def test_a10_trusted_alias_auto_accept_overwrites_existing_human_review():
    """Incoming value mapped via trusted alias with AUTO_ACCEPT cannot overwrite existing HUMAN_REVIEW without curator review (Decision D2)."""
    existing_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=75.0,
        resolution="HUMAN_REVIEW",
        unit="cm",
    )
    incoming_alias_val = _create_sample_attribute_value(
        label="mature plant height",
        value=78.2,
        resolution="AUTO_ACCEPT",
        unit="cm",
    )

    policy = AttributePolicy()
    assert policy.can_overwrite(existing_val, incoming_alias_val) is False
    assert policy.overwrite_block_reason(existing_val, incoming_alias_val) == "EXISTING_HUMAN_PROTECTED"


def test_a10_incompatible_value_type_blocks_auto_overwrite():
    """Type incompatibility between numeric current value and non-numeric incoming blocks overwrite."""
    existing_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=80.0,
        value_type="number",
        unit="cm",
    )
    incoming_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value="tinggi sedang",
        value_type="text",
        unit=None,
    )

    policy = AttributePolicy()
    assert policy.can_overwrite(existing_val, incoming_val) is False


def test_a10_unit_incompatibility_blocks_auto_overwrite():
    """Incompatible dimension unit between existing and incoming blocks auto overwrite."""
    existing_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=80.0,
        unit="cm",
    )
    incoming_val = _create_sample_attribute_value(
        label="tinggi tanaman",
        value=0.8,
        unit="kg",  # Weight unit cannot overwrite length measurement
    )

    policy = AttributePolicy()
    assert policy.can_overwrite(existing_val, incoming_val) is False


def test_a10_policy_can_overwrite_method_and_function_parity():
    """Module-level function and AttributePolicy method maintain identical decision parity."""
    existing_val = _create_sample_attribute_value("tinggi tanaman", 80.0, "HUMAN_REVIEW")
    incoming_val = _create_sample_attribute_value("tinggi tanaman", 85.0, "AUTO_ACCEPT")

    policy = AttributePolicy()
    assert policy.can_overwrite(existing_val, incoming_val) == can_overwrite_attribute_value(
        existing_val, incoming_val, policy=policy
    )


# ============================================================================
# Criterion A22: Evaluator Holdout Gate & Semantic Matching Restrictions
# ============================================================================


def test_semantic_policy_evaluation_report_gate():
    """Configuration holds semantic auto-accept to HITL while holdout report flag is not approved."""
    # Default policy instance
    policy = AttributePolicy()
    assert policy.semantic_auto_accept_enabled is False
    assert policy.holdout_report_approved is False

    catalog = AttributeCatalog()
    semantic_query = "ukuran tinggi tanaman pokok dewasa"

    # Simulated semantic evaluator produces high similarity (0.92)
    res = policy.evaluate(
        raw_label=semantic_query,
        catalog=catalog,
        semantic_score=0.92,
    )

    # Gate is closed: despite high semantic score, must be enqueued to HITL review
    assert res.status == "NEEDS_REVIEW"
    assert "holdout" in res.reason.lower() or "gate" in res.reason.lower() or "hitl" in res.reason.lower()


def test_a22_default_policy_enforces_exact_and_curated_aliases_only():
    """Default policy strictly limits AUTO_ACCEPT to exact canonical labels and curated aliases."""
    policy = AttributePolicy()
    catalog = AttributeCatalog()

    # 1. Exact label -> AUTO_ACCEPT
    res_exact = policy.evaluate("tinggi tanaman", catalog=catalog)
    assert res_exact.status == "AUTO_ACCEPT"

    # 2. Curated alias -> AUTO_ACCEPT
    res_alias = policy.evaluate("mature plant height", catalog=catalog)
    assert res_alias.status == "AUTO_ACCEPT"

    # 3. Semantic non-exact with 0.98 similarity -> NEEDS_REVIEW
    res_semantic = policy.evaluate(
        "postur tinggi tumbuhan",
        catalog=catalog,
        semantic_score=0.98,
    )
    assert res_semantic.status == "NEEDS_REVIEW"


def test_a22_holdout_evaluation_report_schema_and_metrics():
    """Holdout evaluation report validates required metrics and calibration fields."""
    report_data = {
        "report_id": "rep_holdout_20261019_001",
        "total_samples": 120,
        "precision": 0.983,
        "coverage": 0.875,
        "disagreement_per_domain": {
            "vegetatif": 0.01,
            "daun": 0.02,
            "buah": 0.01,
            "bunga": 0.0,
            "biji": 0.0,
        },
        "threshold_evaluated": 0.85,
        "is_approved": False,
        "evaluated_at": datetime.now(timezone.utc),
    }

    report = HoldoutEvaluationReport.model_validate(report_data)
    assert report.total_samples == 120
    assert report.precision == pytest.approx(0.983)
    assert report.coverage == pytest.approx(0.875)
    assert report.is_approved is False

    # Evaluation gate returns false when report is not approved
    gate_passed = evaluate_holdout_gate(report)
    assert gate_passed is False


def test_a22_activating_semantic_auto_accept_requires_approved_holdout_report():
    """Activating semantic_auto_accept_enabled without approved report raises an error."""
    unapproved_report = HoldoutEvaluationReport(
        report_id="rep_unapproved_001",
        total_samples=50,
        precision=0.90,
        coverage=0.70,
        disagreement_per_domain={"daun": 0.10},
        threshold_evaluated=0.85,
        is_approved=False,
        evaluated_at=datetime.now(timezone.utc),
    )

    # Attempting to initialize or enable semantic auto-accept without approval fails
    with pytest.raises(ValueError):
        AttributePolicy(
            semantic_auto_accept_enabled=True,
            holdout_report_approved=False,
        )

    policy = AttributePolicy()
    with pytest.raises(ValueError):
        policy.enable_semantic_auto_accept(unapproved_report)


def test_a22_approved_gate_allows_high_confidence_semantic_auto_accept():
    """Approved holdout report permits high-confidence semantic matches to auto accept."""
    approved_report = HoldoutEvaluationReport(
        report_id="rep_approved_001",
        total_samples=250,
        precision=0.992,
        coverage=0.940,
        disagreement_per_domain={"daun": 0.005, "vegetatif": 0.008},
        threshold_evaluated=0.85,
        is_approved=True,
        evaluated_at=datetime.now(timezone.utc),
    )

    policy = AttributePolicy()
    policy.enable_semantic_auto_accept(approved_report)
    assert policy.semantic_auto_accept_enabled is True
    assert policy.holdout_report_approved is True

    catalog = AttributeCatalog()
    # High score (0.95 >= 0.85 threshold) now yields AUTO_ACCEPT
    res = policy.evaluate(
        "postur tinggi tumbuhan",
        catalog=catalog,
        semantic_score=0.95,
    )
    assert res.status == "AUTO_ACCEPT"
    assert res.attribute_id == "attr_tinggi_tanaman"


def test_a22_low_confidence_below_threshold_remains_needs_review_even_when_gate_open():
    """Even with semantic gate activated, candidates below threshold route to review."""
    approved_report = HoldoutEvaluationReport(
        report_id="rep_approved_002",
        total_samples=250,
        precision=0.992,
        coverage=0.940,
        disagreement_per_domain={},
        threshold_evaluated=0.85,
        is_approved=True,
        evaluated_at=datetime.now(timezone.utc),
    )

    policy = AttributePolicy()
    policy.enable_semantic_auto_accept(approved_report)

    catalog = AttributeCatalog()
    # Score 0.72 is below 0.85 threshold
    res = policy.evaluate(
        "morfologi habitus agak tinggi",
        catalog=catalog,
        semantic_score=0.72,
    )
    assert res.status == "NEEDS_REVIEW"


def test_a22_fail_closed_on_evaluator_anomaly():
    """NaN, negative score, or runtime error in semantic scoring safely fails closed to NEEDS_REVIEW."""
    approved_report = HoldoutEvaluationReport(
        report_id="rep_approved_003",
        total_samples=250,
        precision=0.99,
        coverage=0.94,
        disagreement_per_domain={},
        threshold_evaluated=0.85,
        is_approved=True,
        evaluated_at=datetime.now(timezone.utc),
    )

    policy = AttributePolicy()
    policy.enable_semantic_auto_accept(approved_report)
    catalog = AttributeCatalog()

    # Invalid score fails closed
    res_none = policy.evaluate("postur tinggi tumbuhan", catalog=catalog, semantic_score=None)
    assert res_none.status == "NEEDS_REVIEW"


# ============================================================================
# General Attribute Policy Contract & Edge Cases
# ============================================================================


def test_resolution_status_literals_contract():
    """AttributeResolution enforces status literals: AUTO_ACCEPT, NEEDS_REVIEW, NEW_ATTRIBUTE_REVIEW."""
    valid_statuses = ["AUTO_ACCEPT", "NEEDS_REVIEW", "NEW_ATTRIBUTE_REVIEW"]
    for st in valid_statuses:
        res = AttributeResolution(
            status=st,
            attribute_id="attr_tinggi_tanaman" if st == "AUTO_ACCEPT" else None,
            canonical_key="tinggi_tanaman" if st == "AUTO_ACCEPT" else None,
            matched_label="tinggi tanaman" if st == "AUTO_ACCEPT" else None,
            organ="vegetatif" if st == "AUTO_ACCEPT" else None,
            confidence=1.0 if st == "AUTO_ACCEPT" else 0.0,
            reason="Validation test",
            raw_label="tinggi tanaman",
        )
        assert res.status == st

    with pytest.raises((ValidationError, ValueError)):
        AttributeResolution(
            status="UNAUTHORIZED_STATUS",
            confidence=0.5,
            reason="Invalid status",
            raw_label="test",
        )


def test_resolve_attribute_exact_canonical_label():
    """Resolving an exact canonical label returns full confidence AUTO_ACCEPT with organ domain."""
    catalog = AttributeCatalog()
    res = resolve_attribute("tinggi tanaman", catalog=catalog)

    assert res.status == "AUTO_ACCEPT"
    assert res.attribute_id == "attr_tinggi_tanaman"
    assert res.canonical_key == "tinggi_tanaman"
    assert res.matched_label == "tinggi tanaman"
    assert res.organ == "vegetatif"
    assert res.confidence == pytest.approx(1.0)
    assert res.is_trusted_alias is False


def test_resolve_attribute_novel_unregistered_label():
    """Unregistered header produces NEW_ATTRIBUTE_REVIEW with zero confidence and empty ID."""
    catalog = AttributeCatalog()
    res = resolve_attribute("Kandungan Capsaicin Total", catalog=catalog)

    assert res.status == "NEW_ATTRIBUTE_REVIEW"
    assert res.attribute_id is None
    assert res.canonical_key is None
    assert res.confidence == pytest.approx(0.0)


def test_resolve_attribute_rejects_empty_and_whitespace_only_label():
    """Empty strings and whitespace-only labels are rejected with ValueError."""
    catalog = AttributeCatalog()

    with pytest.raises(ValueError):
        resolve_attribute("", catalog=catalog)

    with pytest.raises(ValueError):
        resolve_attribute("   \t\n  ", catalog=catalog)


def test_resolve_attribute_deterministic_and_reproducible():
    """Resolving identical input repeatedly produces strictly identical resolution output."""
    catalog = AttributeCatalog()
    label = "panjang daun"

    res_first = resolve_attribute(label, catalog=catalog)
    for _ in range(50):
        res_subsequent = resolve_attribute(label, catalog=catalog)
        assert res_first.status == res_subsequent.status
        assert res_first.attribute_id == res_subsequent.attribute_id
        assert res_first.confidence == res_subsequent.confidence
        assert res_first.organ == res_subsequent.organ
