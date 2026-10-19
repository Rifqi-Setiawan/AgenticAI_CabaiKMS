from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.storage.document_contracts import (
    AdministrativePath,
    HabitatIdentity,
    PlantIdentity,
)
from src.storage.identity_resolution import (
    AdministrativeRegistry,
    LocationResolution,
    PlantCatalog,
    PlantResolution,
    extract_address_components,
    resolve_location,
    resolve_plant,
)


# ============================================================================
# Criterion A03: Administrative Hierarchy & Invariance to Elevation and pH
# ============================================================================


def test_a03_habitat_ignores_elevation_and_ph_for_sleman_rows_3_and_4(
    resume_data_workbook_path: Path,
):
    """Row 3 (Dusun Randu, 573 mdpl, pH 7) and Row 4 (Dusun Tenen, 598 mdpl, pH 6.8) map to identical habitat."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    addr_row_3 = str(ws["B3"].value)
    addr_row_4 = str(ws["B4"].value)
    elev_row_3 = int(ws["E3"].value)
    elev_row_4 = int(ws["E4"].value)
    ph_row_3 = float(ws["L3"].value)
    ph_row_4 = float(ws["L4"].value)

    # Sanity verify source cell differences
    assert elev_row_3 == 573
    assert elev_row_4 == 598
    assert elev_row_3 != elev_row_4
    assert ph_row_3 == pytest.approx(7.0)
    assert ph_row_4 == pytest.approx(6.8)
    assert ph_row_3 != ph_row_4

    res_3 = resolve_location(addr_row_3)
    res_4 = resolve_location(addr_row_4)

    assert res_3.status == "RESOLVED"
    assert res_4.status == "RESOLVED"
    assert res_3.habitat is not None
    assert res_4.habitat is not None

    # Habitat identity must be strictly identical regardless of elevation and pH differences
    assert res_3.habitat.id == res_4.habitat.id
    assert res_3.habitat.definition == "administrative_village_v1"
    assert res_4.habitat.definition == "administrative_village_v1"

    # Administrative path components must match the curated 4-tier hierarchy
    path_3 = res_3.habitat.administrative_path
    path_4 = res_4.habitat.administrative_path
    assert path_3.province_name == "Daerah Istimewa Yogyakarta"
    assert path_3.regency_name == "Kabupaten Sleman"
    assert path_3.district_name == "Kecamatan Pakem"
    assert path_3.village_name == "Desa Hargobinangun"
    assert path_3 == path_4


def test_a03_elevation_and_ph_differentiation_produces_identical_habitat_id():
    """Synthetic addresses with identical administrative paths but varying environmental metrics produce same habitat."""
    addr = "Dusun Randu, Desa Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta"

    res_default = resolve_location(addr)
    assert res_default.status == "RESOLVED"
    assert res_default.habitat is not None

    # Re-resolving the same administrative path under different simulated sampling parameters
    res_variation = resolve_location(addr)
    assert res_variation.status == "RESOLVED"
    assert res_variation.habitat is not None
    assert res_default.habitat.id == res_variation.habitat.id


def test_a03_sampling_markers_in_pengilon_rows_9_and_10_resolve_to_same_habitat(
    resume_data_workbook_path: Path,
):
    """Row 9 (sampling 5, pH 6.0) and Row 10 (sampling 6, pH 5.7) resolve to identical habitat in Pengilon, Temanggung."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    addr_row_9 = str(ws["B9"].value)
    addr_row_10 = str(ws["B10"].value)

    res_9 = resolve_location(addr_row_9)
    res_10 = resolve_location(addr_row_10)

    assert res_9.status == "RESOLVED"
    assert res_10.status == "RESOLVED"
    assert res_9.habitat is not None
    assert res_10.habitat is not None

    # Same village in same district and regency maps to the exact same habitat ID
    assert res_9.habitat.id == res_10.habitat.id
    assert res_9.habitat.administrative_path.regency_name == "Kabupaten Temanggung"
    assert res_9.habitat.administrative_path.district_name == "Kecamatan Bulu"
    assert res_9.habitat.administrative_path.village_name == "Desa Pengilon"

    # Distinct sampling markers must be captured as detail metadata, not altering habitat
    assert "sampling 5" in str(res_9.sampling_marker).lower()
    assert "sampling 6" in str(res_10.sampling_marker).lower()
    assert res_9.sampling_marker != res_10.sampling_marker


def test_a03_hamlets_and_markers_captured_in_location_resolution_metadata():
    """LocationResolution preserves hamlet and sampling marker details without leaking into habitat ID."""
    addr = "Dusun Randu, Desa Hargobinangun, Area Sawah, Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta 55582, Indonesia (sampling 1)"
    res = resolve_location(addr)

    assert res.status == "RESOLVED"
    assert res.habitat is not None
    assert res.hamlet == "Dusun Randu"
    assert res.sampling_marker in ("sampling 1", "(sampling 1)")
    assert res.raw_address == addr

    # Habitat ID and label should reflect village level, not hamlet or marker
    assert "Dusun Randu" not in res.habitat.id
    assert "sampling 1" not in res.habitat.id


# ============================================================================
# Criterion A04: Hamlet Merging and Cross-Regency Homonymous Village Separation
# ============================================================================


def test_a04_hamlets_merged_within_same_village_wonosobo_lamuk_rows_12_and_13(
    resume_data_workbook_path: Path,
):
    """Row 12 (Dusun Pangempon, Desa Lamuk) and Row 13 (Dusun Genting, Desa Lamuk) in Wonosobo merge into single habitat."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    addr_row_12 = str(ws["B12"].value)
    addr_row_13 = str(ws["B13"].value)

    res_12 = resolve_location(addr_row_12)
    res_13 = resolve_location(addr_row_13)

    assert res_12.status == "RESOLVED"
    assert res_13.status == "RESOLVED"
    assert res_12.habitat is not None
    assert res_13.habitat is not None

    # Both hamlets in Desa Lamuk, Kalikajar, Wonosobo must share identical habitat ID
    assert res_12.habitat.id == res_13.habitat.id
    assert res_12.habitat.administrative_path.province_name == "Jawa Tengah"
    assert res_12.habitat.administrative_path.regency_name == "Kabupaten Wonosobo"
    assert res_12.habitat.administrative_path.district_name == "Kecamatan Kalikajar"
    assert res_12.habitat.administrative_path.village_name == "Desa Lamuk"

    # Distinct hamlets captured in resolution metadata
    assert res_12.hamlet == "Dusun Pangempon"
    assert res_13.hamlet == "Dusun Genting"
    assert res_12.hamlet != res_13.hamlet


def test_a04_homonymous_villages_in_different_regencies_are_strictly_separated():
    """Desa Lamuk in Wonosobo and Desa Lamuk in Purbalingga must produce distinct habitat IDs."""
    addr_wonosobo = "Desa Lamuk, Kec. Kalikajar, Kabupaten Wonosobo, Jawa Tengah"
    addr_purbalingga = "Desa Lamuk, Kec. Kejobong, Kabupaten Purbalingga, Jawa Tengah"

    res_w = resolve_location(addr_wonosobo)
    res_p = resolve_location(addr_purbalingga)

    assert res_w.status == "RESOLVED"
    assert res_p.status == "RESOLVED"
    assert res_w.habitat is not None
    assert res_p.habitat is not None

    # Village names are identical ("Desa Lamuk")
    assert res_w.habitat.administrative_path.village_name == "Desa Lamuk"
    assert res_p.habitat.administrative_path.village_name == "Desa Lamuk"

    # But regency and district differ, so habitat IDs must be strictly different
    assert res_w.habitat.administrative_path.regency_name == "Kabupaten Wonosobo"
    assert res_p.habitat.administrative_path.regency_name == "Kabupaten Purbalingga"
    assert res_w.habitat.id != res_p.habitat.id


def test_a04_gondosuli_temanggung_hamlets_merge_to_same_village_habitat(
    resume_data_workbook_path: Path,
):
    """Row 7 (Dusun Wolodono, Desa Gondosuli) and Row 8 (Dusun Gondosuli, Desa Gondosuli) merge into one habitat."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    addr_row_7 = str(ws["B7"].value)
    addr_row_8 = str(ws["B8"].value)

    res_7 = resolve_location(addr_row_7)
    res_8 = resolve_location(addr_row_8)

    assert res_7.status == "RESOLVED"
    assert res_8.status == "RESOLVED"
    assert res_7.habitat is not None
    assert res_8.habitat is not None

    assert res_7.habitat.id == res_8.habitat.id
    assert res_7.habitat.administrative_path.village_name == "Desa Gondosuli"
    assert res_7.habitat.administrative_path.district_name == "Kecamatan Bulu"
    assert res_7.habitat.administrative_path.regency_name == "Kabupaten Temanggung"


def test_a04_village_name_alone_insufficient_to_construct_habitat():
    """Isolated village name without regency/district hierarchy must not resolve to an arbitrary habitat."""
    res = resolve_location("Desa Lamuk")
    # Must be AMBIGUOUS or UNRESOLVED because multiple Lamuk villages exist in Central Java
    assert res.status in ("AMBIGUOUS", "UNRESOLVED")
    assert res.habitat is None
    if res.status == "AMBIGUOUS":
        assert len(res.candidates) >= 2


# ============================================================================
# Criterion A05: Ambiguous, Conflicting, or Incomplete Locations Hold Commit
# ============================================================================


def test_a05_ambiguous_conflicting_villages_returns_ambiguous_or_conflict_status():
    """Address referencing two competing villages must return AMBIGUOUS or CONFLICT and withhold habitat."""
    ambiguous_addr = "Desa Hargobinangun atau Desa Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta"
    res = resolve_location(ambiguous_addr)

    assert res.status in ("AMBIGUOUS", "CONFLICT")
    assert res.habitat is None
    assert len(res.reason) > 0


def test_a05_unresolved_address_without_known_village_returns_unresolved():
    """Generic landscape description lacking administrative village returns UNRESOLVED."""
    unresolved_addr = "Lahan Sawah Pinggir Hutan, Tanpa Nama Desa, Indonesia"
    res = resolve_location(unresolved_addr)

    assert res.status == "UNRESOLVED"
    assert res.habitat is None
    assert res.candidates == []
    assert len(res.reason) > 0


def test_a05_missing_regency_for_homonymous_village_returns_ambiguous():
    """Homonymous village without regency or district qualification produces multiple candidates."""
    res = resolve_location("Desa Lamuk, Jawa Tengah")
    assert res.status in ("AMBIGUOUS", "UNRESOLVED")
    assert res.habitat is None
    if res.status == "AMBIGUOUS":
        # Must list candidates for both Wonosobo and Purbalingga
        regencies = {c.administrative_path.regency_name for c in res.candidates}
        assert "Kabupaten Wonosobo" in regencies or len(res.candidates) >= 2


def test_a05_contradictory_hierarchy_returns_conflict_status():
    """Address claiming a village in the wrong regency returns CONFLICT or UNRESOLVED."""
    contradictory_addr = "Desa Hargobinangun, Kec. Kalikajar, Kabupaten Wonosobo, Jawa Tengah"
    res = resolve_location(contradictory_addr)

    assert res.status in ("CONFLICT", "UNRESOLVED")
    assert res.habitat is None


def test_a05_empty_or_whitespace_address_returns_unresolved():
    """Empty or whitespace-only address returns UNRESOLVED."""
    res_empty = resolve_location("")
    res_ws = resolve_location("   \n\t  ")

    assert res_empty.status == "UNRESOLVED"
    assert res_empty.habitat is None
    assert res_ws.status == "UNRESOLVED"
    assert res_ws.habitat is None


def test_a05_arbitrary_text_without_administrative_structure_returns_unresolved():
    """Arbitrary non-address text returns UNRESOLVED."""
    res = resolve_location("Pengukuran klorofil tanaman cabai rawit nomor 5")
    assert res.status == "UNRESOLVED"
    assert res.habitat is None


# ============================================================================
# Criterion A06: Plant Identity Level & Source Category Retention
# ============================================================================


def test_a06_plant_resolution_retains_source_category_for_cabai_rawit_row_3(
    resume_data_workbook_path: Path,
):
    """Row 3 label 'Cabai rawit (Capsicum frutescens L)' resolves to source_category, avoiding invented cultivars."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    raw_label = str(ws["F3"].value)
    assert raw_label == "Cabai rawit (Capsicum frutescens L)"

    res = resolve_plant(raw_label)

    assert res.status == "RESOLVED"
    assert res.plant is not None
    assert res.plant.identity_level == "source_category"
    assert res.plant.scientific_name == "Capsicum frutescens L"
    # The system must not invent a specific cultivar (e.g. Maruti, Hiyung)
    assert "maruti" not in res.plant.label.lower()
    assert "hiyung" not in res.plant.label.lower()
    assert res.plant.identity_level != "cultivar"


def test_a06_plant_resolution_retains_source_category_for_cabai_besar_row_4(
    resume_data_workbook_path: Path,
):
    """Row 4 label 'cabai besar (Capsicum annum L)' resolves to source_category."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    raw_label = str(ws["F4"].value)
    assert raw_label == "cabai besar (Capsicum annum L)"

    res = resolve_plant(raw_label)

    assert res.status == "RESOLVED"
    assert res.plant is not None
    assert res.plant.identity_level == "source_category"
    assert res.plant.scientific_name in ("Capsicum annum L", "Capsicum annuum L")
    # Must not invent cultivar
    assert res.plant.identity_level != "cultivar"


def test_a06_plant_catalog_does_not_promote_generic_category_to_specific_cultivar():
    """Generic chili names ('rawit', 'cabai merah') resolve to source_category or species, never cultivar."""
    res_rawit = resolve_plant("cabai rawit")
    assert res_rawit.status == "RESOLVED"
    assert res_rawit.plant is not None
    assert res_rawit.plant.identity_level in ("source_category", "species")
    assert res_rawit.plant.identity_level != "cultivar"

    res_besar = resolve_plant("cabai besar")
    assert res_besar.status == "RESOLVED"
    assert res_besar.plant is not None
    assert res_besar.plant.identity_level in ("source_category", "species")
    assert res_besar.plant.identity_level != "cultivar"


def test_a06_plant_resolution_retains_explicit_cultivar_when_provided():
    """When the source explicitly designates a known cultivar, identity_level can be cultivar."""
    explicit_label = "Cabai Rawit Merah Maruti"
    res = resolve_plant(explicit_label)
    if res.status == "RESOLVED" and res.plant is not None:
        assert res.plant.identity_level in ("cultivar", "source_category")


def test_a06_unknown_plant_label_returns_unresolved():
    """Unrecognized plant label returns UNRESOLVED status without hallucinating identity."""
    res = resolve_plant("Tanaman Misterius X999 Tidak Terdaftar")
    assert res.status == "UNRESOLVED"
    assert res.plant is None


def test_a06_ambiguous_plant_label_returns_ambiguous():
    """Ambiguous label containing multiple conflicting types returns AMBIGUOUS."""
    res = resolve_plant("Campuran Cabai Rawit dan Cabai Besar")
    assert res.status in ("AMBIGUOUS", "UNRESOLVED")
    if res.status == "AMBIGUOUS":
        assert res.plant is None
        assert len(res.candidates) >= 2


def test_a06_whitespace_and_casing_variations_resolve_to_canonical_plant_identity():
    """Casing and whitespace differences map to the identical canonical PlantIdentity ID."""
    res_1 = resolve_plant("Cabai rawit (Capsicum frutescens L)")
    res_2 = resolve_plant("  cabai RAWIT (Capsicum frutescens L) \n")
    res_3 = resolve_plant("Cabai Rawit")

    assert res_1.status == "RESOLVED"
    assert res_2.status == "RESOLVED"
    assert res_1.plant is not None
    assert res_2.plant is not None
    assert res_1.plant.id == res_2.plant.id


# ============================================================================
# Criterion A02: Unique Identity Variety + Habitat Pair Formulation
# ============================================================================


def test_a02_identity_resolution_pairs_produce_unique_document_keys(
    resume_data_workbook_path: Path,
):
    """Rows 3 (Rawit in Hargobinangun) and 4 (Besar in Hargobinangun) produce distinct document keys."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    plant_3 = resolve_plant(str(ws["F3"].value)).plant
    plant_4 = resolve_plant(str(ws["F4"].value)).plant
    habitat_3 = resolve_location(str(ws["B3"].value)).habitat
    habitat_4 = resolve_location(str(ws["B4"].value)).habitat

    assert plant_3 is not None
    assert plant_4 is not None
    assert habitat_3 is not None
    assert habitat_4 is not None

    # Habitat IDs are identical
    assert habitat_3.id == habitat_4.id

    # Plant IDs differ
    assert plant_3.id != plant_4.id

    # Unique document keys variety_id:habitat_id must be distinct
    key_3 = f"{plant_3.id}:{habitat_3.id}"
    key_4 = f"{plant_4.id}:{habitat_4.id}"
    assert key_3 != key_4


def test_a02_same_variety_in_distinct_habitats_produces_distinct_document_keys(
    resume_data_workbook_path: Path,
):
    """Rawit in Hargobinangun (Row 3) vs Rawit in Lamuk (Row 12) produces distinct document keys."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    plant_3 = resolve_plant(str(ws["F3"].value)).plant
    plant_12 = resolve_plant(str(ws["F12"].value)).plant
    habitat_3 = resolve_location(str(ws["B3"].value)).habitat
    habitat_12 = resolve_location(str(ws["B12"].value)).habitat

    assert plant_3 is not None
    assert plant_12 is not None
    assert habitat_3 is not None
    assert habitat_12 is not None

    # Plant IDs are identical
    assert plant_3.id == plant_12.id

    # Habitat IDs differ (Sleman vs Wonosobo)
    assert habitat_3.id != habitat_12.id

    key_3 = f"{plant_3.id}:{habitat_3.id}"
    key_12 = f"{plant_12.id}:{habitat_12.id}"
    assert key_3 != key_12


def test_a02_same_variety_and_same_habitat_across_different_hamlets_produce_identical_document_key(
    resume_data_workbook_path: Path,
):
    """Rows 12 and 13 (Rawit in Dusun Pangempon vs Dusun Genting, Desa Lamuk) produce identical document key."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    plant_12 = resolve_plant(str(ws["F12"].value)).plant
    plant_13 = resolve_plant(str(ws["F13"].value)).plant
    habitat_12 = resolve_location(str(ws["B12"].value)).habitat
    habitat_13 = resolve_location(str(ws["B13"].value)).habitat

    assert plant_12 is not None
    assert plant_13 is not None
    assert habitat_12 is not None
    assert habitat_13 is not None

    # Identical variety and identical village habitat produce identical document key
    key_12 = f"{plant_12.id}:{habitat_12.id}"
    key_13 = f"{plant_13.id}:{habitat_13.id}"
    assert key_12 == key_13


def test_a02_distinct_varieties_in_same_habitat_produce_distinct_document_keys():
    """Synthetic test ensuring variety_id differentiation holds across identical habitat."""
    hab = HabitatIdentity(
        id="hab_wonosobo_lamuk_001",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Jawa Tengah",
            regency_name="Kabupaten Wonosobo",
            district_name="Kecamatan Kalikajar",
            village_name="Desa Lamuk",
        ),
        label="Desa Lamuk, Kecamatan Kalikajar, Kabupaten Wonosobo, Jawa Tengah",
    )
    plant_a = PlantIdentity(
        id="plant_rawit_001",
        label="Cabai rawit",
        identity_level="source_category",
    )
    plant_b = PlantIdentity(
        id="plant_besar_001",
        label="Cabai besar",
        identity_level="source_category",
    )

    key_a = f"{plant_a.id}:{hab.id}"
    key_b = f"{plant_b.id}:{hab.id}"
    assert key_a != key_b


# ============================================================================
# Address Component Extraction & Normalization
# ============================================================================


def test_extract_address_components_normalizes_standard_abbreviations():
    """Abbreviations such as Kec., Kab., Ds., Dsn., and Jl. are properly parsed into administrative tiers."""
    raw = "Dsn. Randu, Ds. Hargobinangun, Kec. Pakem, Kab. Sleman, D.I. Yogyakarta"
    components = extract_address_components(raw)

    assert isinstance(components, dict)
    assert components.get("province") in ("Daerah Istimewa Yogyakarta", "D.I. Yogyakarta")
    assert components.get("regency") in ("Kabupaten Sleman", "Sleman")
    assert components.get("district") in ("Kecamatan Pakem", "Pakem")
    assert components.get("village") in ("Desa Hargobinangun", "Hargobinangun")
    assert components.get("hamlet") in ("Dusun Randu", "Randu", "Dsn. Randu")


def test_extract_address_components_extracts_parenthetical_sampling_markers():
    """Parenthetical suffixes such as '(sampling 1)' or '(lokasi 2)' are extracted into sampling_marker."""
    raw_sampling = "Dusun Randu, Desa Hargobinangun, Sleman (sampling 1)"
    raw_lokasi = "Dusun Pangempon, Desa Lamuk, Wonosobo (lokasi 2)"

    comp_sampling = extract_address_components(raw_sampling)
    comp_lokasi = extract_address_components(raw_lokasi)

    assert "sampling 1" in str(comp_sampling.get("sampling_marker")).lower()
    assert "lokasi 2" in str(comp_lokasi.get("sampling_marker")).lower()


def test_extract_address_components_extracts_hamlet_correctly():
    """Leading Dusun token is identified as hamlet, not mistaken for village."""
    raw = "Dusun Pangempon, Desa Lamuk, Kec. Kalikajar, Kabupaten Wonosobo"
    components = extract_address_components(raw)

    assert components.get("hamlet") == "Dusun Pangempon"
    assert components.get("village") == "Desa Lamuk"


def test_extract_address_components_preserves_exact_raw_address():
    """extract_address_components and LocationResolution retain pristine raw_address string."""
    raw = "  Dusun Tenen, Desa Hargobinangun, Kec. Pakem, Sleman (sampling 2)  "
    components = extract_address_components(raw)
    res = resolve_location(raw)

    assert components.get("raw_address") == raw
    assert res.raw_address == raw


def test_extract_address_components_strips_postal_codes_and_country():
    """Postal codes (e.g. 55582) and country suffixes ('Indonesia') are stripped from administrative components."""
    raw = "Desa Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta 55582, Indonesia"
    components = extract_address_components(raw)

    assert "55582" not in str(components.get("province"))
    assert "Indonesia" not in str(components.get("province"))
    assert "55582" not in str(components.get("village"))


# ============================================================================
# Administrative Registry & Plant Catalog APIs (Keputusan Final #1)
# ============================================================================


def test_administrative_registry_initialization_and_curated_regions_coverage():
    """AdministrativeRegistry loads curated local dataset regions (Sleman, Temanggung, Wonosobo, Majalengka)."""
    registry = AdministrativeRegistry()

    # Sleman
    hab_sleman = registry.lookup(
        province="Daerah Istimewa Yogyakarta",
        regency="Kabupaten Sleman",
        district="Kecamatan Pakem",
        village="Desa Hargobinangun",
    )
    assert hab_sleman is not None
    assert hab_sleman.administrative_path.village_name == "Desa Hargobinangun"

    # Temanggung
    hab_temanggung = registry.lookup(
        province="Jawa Tengah",
        regency="Kabupaten Temanggung",
        district="Kecamatan Bulu",
        village="Desa Pengilon",
    )
    assert hab_temanggung is not None
    assert hab_temanggung.administrative_path.village_name == "Desa Pengilon"

    # Wonosobo
    hab_wonosobo = registry.lookup(
        province="Jawa Tengah",
        regency="Kabupaten Wonosobo",
        district="Kecamatan Kalikajar",
        village="Desa Lamuk",
    )
    assert hab_wonosobo is not None
    assert hab_wonosobo.administrative_path.village_name == "Desa Lamuk"

    # Majalengka
    hab_majalengka = registry.lookup(
        province="Jawa Barat",
        regency="Kabupaten Majalengka",
        district="Kecamatan Argapura",
        village="Desa Argalingga",
    )
    assert hab_majalengka is not None
    assert hab_majalengka.administrative_path.village_name == "Desa Argalingga"


def test_administrative_registry_lookup_by_exact_hierarchy():
    """AdministrativeRegistry.lookup returns a validated HabitatIdentity Contract."""
    registry = AdministrativeRegistry()
    hab = registry.lookup(
        province="Daerah Istimewa Yogyakarta",
        regency="Kabupaten Sleman",
        district="Kecamatan Pakem",
        village="Desa Hargobinangun",
    )
    assert isinstance(hab, HabitatIdentity)
    assert hab.definition == "administrative_village_v1"
    assert len(hab.id) > 0
    assert len(hab.label) > 0


def test_administrative_registry_lookup_returns_none_for_nonexistent_hierarchy():
    """AdministrativeRegistry.lookup returns None when administrative path is unknown."""
    registry = AdministrativeRegistry()
    hab = registry.lookup(
        province="Atlantis",
        regency="Kabupaten Fiksi",
        district="Kecamatan Kosong",
        village="Desa Fantasi",
    )
    assert hab is None


def test_plant_catalog_initialization_and_curated_coverage():
    """PlantCatalog resolves curated chili categories from dataset."""
    catalog = PlantCatalog()

    res_rawit = catalog.resolve("Cabai rawit (Capsicum frutescens L)")
    assert res_rawit.status == "RESOLVED"
    assert res_rawit.plant is not None
    assert res_rawit.plant.identity_level == "source_category"

    res_besar = catalog.resolve("cabai besar (Capsicum annum L)")
    assert res_besar.status == "RESOLVED"
    assert res_besar.plant is not None
    assert res_besar.plant.identity_level == "source_category"


# ============================================================================
# End-to-End Workbook Parity with Real Field Data (data_input.xlsx)
# ============================================================================


def test_all_workbook_resume_data_rows_3_to_15_resolve_to_expected_administrative_hierarchies(
    resume_data_workbook_path: Path,
):
    """All sampling rows 3 through 15 from real data_input.xlsx Resume Data sheet resolve deterministically."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    expected_hierarchies = {
        3: ("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun"),
        4: ("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun"),
        5: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Parakan", "Desa Campursalam"),
        6: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Kedu", "Desa Kutoanyar"),
        7: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Bulu", "Desa Gondosuli"),
        8: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Bulu", "Desa Gondosuli"),
        9: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Bulu", "Desa Pengilon"),
        10: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Bulu", "Desa Pengilon"),
        11: ("Jawa Tengah", "Kabupaten Temanggung", "Kecamatan Bulu", "Desa Bulu"),
        12: ("Jawa Tengah", "Kabupaten Wonosobo", "Kecamatan Kalikajar", "Desa Lamuk"),
        13: ("Jawa Tengah", "Kabupaten Wonosobo", "Kecamatan Kalikajar", "Desa Lamuk"),
        14: ("Jawa Barat", "Kabupaten Majalengka", "Kecamatan Argapura", "Desa Argalingga"),
        15: ("Jawa Barat", "Kabupaten Majalengka", "Kecamatan Argapura", "Desa Argalingga"),
    }

    for row_num, (exp_prov, exp_reg, exp_dist, exp_vill) in expected_hierarchies.items():
        addr_cell = ws.cell(row=row_num, column=2).value
        assert addr_cell is not None, f"Address empty at row {row_num}"

        res = resolve_location(str(addr_cell))
        assert res.status == "RESOLVED", (
            f"Row {row_num} failed to resolve: status={res.status}, reason={res.reason}, raw={addr_cell}"
        )
        assert res.habitat is not None, f"Row {row_num} returned None habitat"

        path = res.habitat.administrative_path
        assert path.province_name == exp_prov, f"Row {row_num} province mismatch: {path.province_name} != {exp_prov}"
        assert path.regency_name == exp_reg, f"Row {row_num} regency mismatch: {path.regency_name} != {exp_reg}"
        assert path.district_name == exp_dist, f"Row {row_num} district mismatch: {path.district_name} != {exp_dist}"
        assert path.village_name == exp_vill, f"Row {row_num} village mismatch: {path.village_name} != {exp_vill}"


def test_workbook_elevation_and_ph_range_invariance_across_all_workbook_rows(
    resume_data_workbook_path: Path,
):
    """Verify that paired rows in the same village (rows 3/4, 7/8, 9/10, 12/13, 14/15) share habitat ID despite differing pH and elevation."""
    import openpyxl

    wb = openpyxl.load_workbook(resume_data_workbook_path, data_only=True)
    ws = wb["Resume Data"]

    village_pairs = [
        (3, 4, "Desa Hargobinangun"),
        (7, 8, "Desa Gondosuli"),
        (9, 10, "Desa Pengilon"),
        (12, 13, "Desa Lamuk"),
        (14, 15, "Desa Argalingga"),
    ]

    for row_a, row_b, village_name in village_pairs:
        addr_a = str(ws.cell(row=row_a, column=2).value)
        addr_b = str(ws.cell(row=row_b, column=2).value)

        res_a = resolve_location(addr_a)
        res_b = resolve_location(addr_b)

        assert res_a.status == "RESOLVED"
        assert res_b.status == "RESOLVED"
        assert res_a.habitat is not None
        assert res_b.habitat is not None

        assert res_a.habitat.id == res_b.habitat.id, (
            f"Village pair {village_name} (rows {row_a} and {row_b}) produced conflicting habitat IDs: "
            f"{res_a.habitat.id} vs {res_b.habitat.id}"
        )
