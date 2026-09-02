from __future__ import annotations

import openpyxl
import pytest
from pydantic import ValidationError

from src.schema.canonical import DEFAULT_TEMPLATE_PATH, CanonicalSchema
from src.schema.contracts import (
    ImageMetadata,
    SchemaMapping,
    VisionResult,
    clear_default_schema_cache,
    valid_row_ids,
)
from src.schema.state import GlobalState


def _reference_n() -> int:
    """N computed independently, straight off the xlsx — the test's oracle,
    so this file never hardcodes 60 either."""
    wb = openpyxl.load_workbook(DEFAULT_TEMPLATE_PATH, data_only=True, read_only=True)
    ws = wb["Sheet1"]
    n = sum(1 for row in ws.iter_rows(min_row=2, values_only=True) if row[0] is not None)
    wb.close()
    return n


@pytest.fixture(scope="module")
def schema() -> CanonicalSchema:
    return CanonicalSchema.from_template()


@pytest.fixture(autouse=True)
def _reset_contracts_cache():
    clear_default_schema_cache()
    yield
    clear_default_schema_cache()


class TestCanonicalSchema:
    def test_loads_correct_row_count(self, schema: CanonicalSchema):
        n = _reference_n()
        assert len(schema.rows) == n
        assert schema.rows[0].id == "r_1"
        assert schema.rows[-1].id == f"r_{n}"

    def test_row_ids_are_sequential_and_unique(self, schema: CanonicalSchema):
        expected = {f"r_{i}" for i in range(1, len(schema.rows) + 1)}
        assert schema.row_ids == expected

    def test_no_row_lacks_a_domain(self, schema: CanonicalSchema):
        # Fase 0 fully mapped every current row — this guards against a
        # future row silently landing as "unassigned" without anyone noticing.
        assert schema.unassigned_labels == []

    def test_domains_derived_not_hardcoded(self, schema: CanonicalSchema):
        assert schema.domains == {
            "vegetatif",
            "daun",
            "bunga",
            "buah",
            "biji",
            "lokasi",
        }

    def test_lokasi_and_image_rows_land_where_expected(self, schema: CanonicalSchema):
        assert schema.row_by_label("Lokasi").domain == "lokasi"
        assert schema.row_by_label("Gambar Daun").domain == "daun"
        assert schema.row_by_label("Gambar Batang").domain == "vegetatif"
        assert schema.row_by_label("Gambar Buah").domain == "buah"
        assert schema.row_by_label("Gambar Bunga").domain == "bunga"

    def test_serialization_nonempty_for_every_row(self, schema: CanonicalSchema):
        for row in schema.rows:
            text = row.serialize()
            assert text.strip()
            assert row.label in text
            assert row.domain in text

    def test_contoh_nilai_pulled_from_template_filled_cells(self, schema: CanonicalSchema):
        habitus = schema.row_by_label("habitus")
        assert habitus is not None
        assert "perdu" in habitus.contoh_nilai

    def test_row_by_label_strips_whitespace_variants(self, schema: CanonicalSchema):
        # "bentuk ujung daun" has trailing whitespace in the raw template cell;
        # the loader must have trimmed it already.
        assert schema.row_by_label("bentuk ujung daun") is not None

    def test_v_and_d_start_empty(self, schema: CanonicalSchema):
        fresh = CanonicalSchema.from_template()
        assert fresh.varietas == []
        assert fresh.cells == {}

    def test_add_varietas_and_set_cell(self, schema: CanonicalSchema):
        fresh = CanonicalSchema.from_template()
        fresh.add_varietas("Varietas Uji")
        fresh.set_cell("r_1", "Varietas Uji", "perdu")
        assert fresh.get_cell("r_1", "Varietas Uji") == "perdu"

    def test_set_cell_rejects_unknown_row_or_varietas(self, schema: CanonicalSchema):
        fresh = CanonicalSchema.from_template()
        fresh.add_varietas("Varietas Uji")
        with pytest.raises(KeyError):
            fresh.set_cell("r_9999", "Varietas Uji", "x")
        with pytest.raises(KeyError):
            fresh.set_cell("r_1", "Varietas Tak Terdaftar", "x")

    def test_has_not_drifted_against_its_own_source(self, schema: CanonicalSchema):
        assert schema.has_drifted() is False


class TestContracts:
    def test_valid_row_ids_includes_null_and_all_rows(self, schema: CanonicalSchema):
        ids = valid_row_ids()
        assert "NULL" in ids
        assert "r_1" in ids
        assert len(ids) == len(schema.rows) + 1

    def test_schema_mapping_accepts_real_row_and_derives_domain(self):
        mapping = SchemaMapping(
            source_attribute="Tinggi Tanaman (cm)",
            source_context="header row of a transposed sheet",
            source_format="transposed",
            target_canonical_row="r_2",  # "tinggi tanaman"
            confidence=0.92,
            reasoning="direct label match",
            normalization_required=True,
        )
        assert mapping.target_domain == "vegetatif"

    def test_schema_mapping_null_row_has_no_domain(self):
        mapping = SchemaMapping(
            source_attribute="Nama Kolektor",
            source_format="row-oriented",
            target_canonical_row="NULL",
            confidence=0.99,
            reasoning="not part of the canonical schema",
            normalization_required=False,
        )
        assert mapping.target_domain is None

    def test_schema_mapping_rejects_unknown_row_id(self):
        with pytest.raises(ValidationError):
            SchemaMapping(
                source_attribute="???",
                source_format="row-oriented",
                target_canonical_row="r_9999",
                confidence=0.5,
                reasoning="bogus",
                normalization_required=False,
            )

    def test_schema_mapping_rejects_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            SchemaMapping(
                source_attribute="x",
                source_format="row-oriented",
                target_canonical_row="r_1",
                confidence=1.5,
                reasoning="x",
                normalization_required=False,
            )

    def test_vision_result_validates(self):
        result = VisionResult(
            classification_status="KNOWN",
            matched_variety="Gendot",
            identified_part="DAUN",
            confidence=0.87,
            visual_evidence="serrated leaf margin, opposite phyllotaxy",
        )
        assert result.identified_part == "DAUN"

    def test_image_metadata_validates_without_relative_path(self):
        meta = ImageMetadata(
            file_id="1a2b3c",
            filename="IMG_0001.jpg",
            mime_type="image/jpeg",
            size=204_800,
            created_time="2026-06-01T10:00:00Z",
        )
        assert meta.filename == "IMG_0001.jpg"
        assert not hasattr(meta, "relative_path")


class TestGlobalState:
    def test_partial_state_is_valid_typed_dict_usage(self):
        state: GlobalState = {"drive_url": "https://drive.google.com/x", "error_trace": []}
        assert state["drive_url"].startswith("https://")

    def test_state_can_carry_contracts_output(self):
        mapping = SchemaMapping(
            source_attribute="Tinggi Tanaman (cm)",
            source_format="transposed",
            target_canonical_row="r_2",
            confidence=0.9,
            reasoning="direct match",
            normalization_required=True,
        )
        state: GlobalState = {"schema_mapping": [mapping]}
        assert state["schema_mapping"][0].target_domain == "vegetatif"
