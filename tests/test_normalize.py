from __future__ import annotations

import pytest

from src.agents.schema_matching.normalize import normalize, normalize_with_trace
from src.schema.canonical import CanonicalRow

# Rows built to mirror real messy values catalogued in docs/PROFILING.md
# §1.2/§2.3 — this file's contoh_nilai match the actual canonical template
# cells those values came from, including the template's own unresolved
# messiness (e.g. row 37's "5 1," and row 50's "5  - " are real cell
# contents, not invented edge cases).
ROW_HABITUS = CanonicalRow(id="r_1", canonical_key="habitus", label="habitus", domain="vegetatif", contoh_nilai=("perdu", "terna"))
ROW_TINGGI = CanonicalRow(
    id="r_2", canonical_key="tinggi_tanaman", label="tinggi tanaman", domain="vegetatif", contoh_nilai=("˃ 100 cm; 20 cm",)
)
ROW_PANJANG_DAUN = CanonicalRow(
    id="r_8", canonical_key="panjang_daun", label="panjang daun", domain="daun", contoh_nilai=("11 - 12 cm", "8,7 - 14,5 cm")
)
ROW_WARNA_DAUN = CanonicalRow(
    id="r_7", canonical_key="warna_daun", label="warna daun", domain="daun", contoh_nilai=("green group 139 B", "green group 137 A")
)
ROW_PANJANG_BUAH_MUDA = CanonicalRow(
    id="r_37", canonical_key="panjang_buah_muda", label="panjang buah muda", domain="buah", contoh_nilai=("5 1,", "8,2 - 11 cm")
)
ROW_LOKASI = CanonicalRow(id="r_56", canonical_key="lokasi", label="Lokasi", domain="lokasi", contoh_nilai=())
ROW_KELILING_BUAH_MASAK = CanonicalRow(
    id="r_50", canonical_key="keliling_buah_masak", label="keliling buah masak", domain="buah", contoh_nilai=("5  - ", "3,2 - 5,3 cm")
)
ROW_JUMLAH_MAHKOTA = CanonicalRow(
    id="r_22", canonical_key="jumlah_mahkota_bunga", label="jumlah mahkota bunga", domain="bunga", contoh_nilai=("7", "5 -'6")
)


# (raw_value, target_row, expected_value, expect_note)
NORMALIZATION_TABLE = [
    ("8,7 - 14,5 cm", ROW_PANJANG_DAUN, "8.7--14.5 cm", False),
    ("60 - 89 cm", ROW_PANJANG_DAUN, "60--89 cm", False),  # the spec's own example, verbatim
    (
        "green group 137 B; gren group 137 A",
        ROW_WARNA_DAUN,
        "green group 137 B; gren group 137 A",  # typo preserved — never "corrected"
        False,
    ),
    ("green group  143 A", ROW_WARNA_DAUN, "green group 143 A", False),
    ("˃ 100 cm; 20 cm", ROW_TINGGI, "˃ 100 cm; 20 cm", False),  # not a dash-range, left alone
    # negative coordinates (real data/samples/data_input.xlsx longitude
    # values) are clean numbers, not ambiguous — found via the Fase 3
    # checkpoint run, where these were false-positively flagged before
    # _CLEAN_NUMBER_RE allowed a leading "-".
    ("-7.634808", ROW_LOKASI, "-7.634808", False),
    ("-7.28905", ROW_LOKASI, "-7.28905", False),
    ("Terna", ROW_HABITUS, "terna", False),  # snapped to canonical vocabulary casing
    ("-", ROW_HABITUS, None, False),
    ("NA", ROW_HABITUS, None, False),
    ("na", ROW_HABITUS, None, False),
    ("", ROW_HABITUS, None, False),
    (" ", ROW_PANJANG_BUAH_MUDA, None, False),
    (None, ROW_HABITUS, None, False),
    (5, ROW_JUMLAH_MAHKOTA, "5", False),
    ("5 1,", ROW_PANJANG_BUAH_MUDA, "5 1,", True),  # garbled, preserved, flagged
    ("5  - ", ROW_KELILING_BUAH_MASAK, "5 -", True),
    ("5 -'6", ROW_JUMLAH_MAHKOTA, "5 -'6", True),
]


class TestNormalizationTable:
    @pytest.mark.parametrize("raw,row,expected_value,expect_note", NORMALIZATION_TABLE)
    def test_expected_normalized_form(self, raw, row, expected_value, expect_note):
        result = normalize(raw, row)
        assert result.value == expected_value
        if expect_note:
            assert result.note is not None
        else:
            assert result.note is None


class TestChangedFlag:
    def test_none_input_is_not_changed(self):
        assert normalize(None, ROW_HABITUS).changed is False

    def test_already_clean_value_is_not_changed(self):
        assert normalize("terna", ROW_HABITUS).changed is False

    def test_empty_token_conversion_counts_as_changed(self):
        assert normalize("-", ROW_HABITUS).changed is True

    def test_whitespace_collapse_counts_as_changed(self):
        assert normalize("green group  143 A", ROW_WARNA_DAUN).changed is True


class TestConservativeness:
    def test_typo_in_color_code_is_never_corrected(self):
        result = normalize("gren group 137 A", ROW_WARNA_DAUN)
        assert result.value == "gren group 137 A"

    def test_unrecognized_categorical_value_is_left_as_is(self):
        result = normalize("bentuk baru yang belum pernah tercatat", ROW_HABITUS)
        assert result.value == "bentuk baru yang belum pernah tercatat"
        assert result.note is None  # no digits -> not flagged as ambiguous either

    def test_garbled_numeric_value_is_never_guess_completed(self):
        result = normalize("5  - ", ROW_KELILING_BUAH_MASAK)
        # must NOT have invented a second number to complete the range
        assert "--" not in result.value
        assert result.value == "5 -"


class TestVocabularySnap:
    def test_numeric_shaped_example_is_never_used_as_a_vocabulary_target(self):
        """ROW_PANJANG_BUAH_MUDA.contoh_nilai contains the template's own
        unresolved "5 1," — that must never be treated as a validated
        vocabulary word an incoming raw value can be "confirmed" against."""
        result = normalize("5 1,", ROW_PANJANG_BUAH_MUDA)
        assert result.note is not None

    def test_case_insensitive_snap_to_canonical_casing(self):
        assert normalize("PERDU", ROW_HABITUS).value == "perdu"

    def test_no_match_leaves_value_untouched(self):
        result = normalize("epifit", ROW_HABITUS)
        assert result.value == "epifit"


class TestNormalizeWithTrace:
    def test_note_becomes_an_error_trace_patch(self):
        state = {"error_trace": ["existing"]}
        result, patch = normalize_with_trace("5 1,", ROW_PANJANG_BUAH_MUDA, state)
        assert result.note is not None
        assert patch["error_trace"] == ["existing", result.note]

    def test_no_note_means_no_patch(self):
        state = {"error_trace": []}
        result, patch = normalize_with_trace("terna", ROW_HABITUS, state)
        assert result.note is None
        assert patch == {}

    def test_does_not_mutate_original_state(self):
        state = {"error_trace": ["existing"]}
        normalize_with_trace("5 1,", ROW_PANJANG_BUAH_MUDA, state)
        assert state["error_trace"] == ["existing"]
