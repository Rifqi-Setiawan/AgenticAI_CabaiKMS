from __future__ import annotations

import pytest

from src.agents.schema_matching.anchor import AnchorCandidate, detect_anchor

pytestmark = pytest.mark.indexing  # needs network on first run (HF model download)

# Real headers/sample values from data/samples/data_input.xlsx — see
# docs/PROFILING.md §2 for where these come from.
ROW_ORIENTED_CANDIDATES_WITH_ANCHOR = [
    AnchorCandidate("No", ["1", "2", "3"]),
    AnchorCandidate(
        "Lokasi Sampling",
        ["Dusun Randu, Desa Hargobinangun, Area Sawah", "Dusun Tenen, Desa Hargobinangun"],
    ),
    AnchorCandidate("Data Koordinat S", ["110.415748", "110.419183"]),
    AnchorCandidate("Data Koordinat E", ["-7.634808", "-7.630332"]),
    AnchorCandidate("Ketinggian Lahan Sampling (mdpl)", ["573", "598", "758"]),
    AnchorCandidate(
        "Jenis Cabai", ["Cabai rawit (Capsicum frutescens L)", "cabai besar (Capsicum annum L)"]
    ),
    AnchorCandidate("Chlorophyll Content (SPAD)", ["28.15", "29.07"]),
    AnchorCandidate("Kelembaban tanah (%)", ["58", "58", "100"]),
    AnchorCandidate("pH tanah", ["7", "6.8", "6.2"]),
    AnchorCandidate("Suhu udara (0C)", ["28.3 - 30.5", "28.7 - 31.1"]),
]

# Same file's columns, minus the one actual anchor — simulates a
# row-oriented sheet that genuinely has no variety-identity column.
ROW_ORIENTED_CANDIDATES_WITHOUT_ANCHOR = [
    c for c in ROW_ORIENTED_CANDIDATES_WITH_ANCHOR if c.column_name != "Jenis Cabai"
]

# Column headers from data/samples/sample_transposed_sintetis.xlsx.
TRANSPOSED_HEADERS = [
    AnchorCandidate("Varietas Sintetis A"),
    AnchorCandidate("Varietas Sintetis B"),
    AnchorCandidate("Varietas Sintetis C"),
]

# Real headers + sample values from data/samples/data_input_sintetis_1.xlsx —
# a regression fixture: an earlier version of detect_anchor picked
# "Bentuk Buah Cabai" here instead of "Jenis Cabai" once sample values were
# blended into the embedded text, because several of "Jenis Cabai"'s own
# real varietas names (e.g. "Cabai rawit NTB", "Cabai landung") contain the
# same word ("Cabai") the concept phrases and "Bentuk Buah Cabai"'s header
# do — a lexical-overlap confound that's exactly the point of scoring on
# header text alone. See docs/CHECKPOINTS.md / the module docstring.
ROW_ORIENTED_CANDIDATES_SINTETIS_1 = [
    AnchorCandidate("No", [str(i) for i in range(1, 11)]),
    AnchorCandidate("Lokasi Sampling", [f"Lahan Percobaan {i}, Indonesia" for i in range(1, 11)]),
    AnchorCandidate("Ketinggian Lahan Sampling (mdpl)", ["534", "573", "772", "501", "572"]),
    AnchorCandidate(
        "Jenis Cabai",
        [
            "Gendot", "Kopay", "Katokkon", "Cabai merah keriting Jotanbar",
            "Cabai merah keriting akar", "Cabai rawit NTB", "Cabai landung",
            "Cabai tanjung", "Domba", "Cabai H",
        ],
    ),
    AnchorCandidate("Bentuk Habitus Tnm", ["perdu", "terna", "terna", "terna"]),
    AnchorCandidate("Tinggi Tnm (cm)", ["˃ 100 cm; 20 cm", "60 - 89 cm", "60 - 155 cm"]),
    AnchorCandidate("Masa Umur", ["bertahunan/perennial", "semusim", "semi bertahunan"]),
    AnchorCandidate("Tekstur Permukaan Daun", ["kasap", "halus", "halus", "halus"]),
    AnchorCandidate("Warna Daun (Code)", ["green group 139 B", "green group 137 A"]),
    AnchorCandidate("Pnjng Daun", ["11 - 12 cm ", "8,7 - 14,5 cm", "10 -14,5 cm"]),
    AnchorCandidate(
        "Bentuk Buah Cabai",
        [
            "kapsul", "kapsul dengan kulit buah mulus", "kapsul dengan kulit buah beralur",
            "memanjang ramping", "memanjang ramping", "kapsul pendek",
            "kapsul gemuk dengan kulit buah halus", "kapsul gemuk dengan kulit buah halus",
            "kapsul pendek ",
        ],
    ),
    AnchorCandidate(
        "Warna Buah Saat Muda",
        [
            "hijau - hijau dengan bercak ungu", "grreen group 139 A", "green group 140 B",
            "green group 143 A", "green group 143 B",
        ],
    ),
]


class TestDetectAnchor:
    def test_english_variety_header_in_flat_table(self):
        result = detect_anchor([
            AnchorCandidate("Sample_ID"), AnchorCandidate("Variety"),
            AnchorCandidate("Growth habit"), AnchorCandidate("Plant Height (cm)"),
        ], source_format="row-oriented")
        assert result.status == "found"
        assert result.column_name == "Variety"

    def test_row_oriented_finds_the_real_anchor_column(self):
        result = detect_anchor(
            ROW_ORIENTED_CANDIDATES_WITH_ANCHOR, source_format="row-oriented"
        )
        assert result.status == "found"
        assert result.column_name == "Jenis Cabai"
        assert result.similarity is not None and result.similarity > 0.5

    def test_row_oriented_escalates_when_no_column_resembles_varietas(self):
        result = detect_anchor(
            ROW_ORIENTED_CANDIDATES_WITHOUT_ANCHOR, source_format="row-oriented"
        )
        assert result.status == "escalate"
        assert result.column_name is None

    def test_row_oriented_escalates_on_no_candidates_at_all(self):
        result = detect_anchor([], source_format="row-oriented")
        assert result.status == "escalate"
        assert result.column_name is None

    def test_transposed_never_requires_an_anchor(self):
        result = detect_anchor(TRANSPOSED_HEADERS, source_format="transposed")
        assert result.status == "not_required"
        assert result.column_name is None

    def test_transposed_is_not_required_even_with_no_candidates(self):
        result = detect_anchor([], source_format="transposed")
        assert result.status == "not_required"

    def test_highest_similarity_wins_when_multiple_clear_a_low_threshold(self):
        # With a low enough threshold several columns clear it — the
        # returned one must be whichever actually scored highest, not
        # just "the first one that passed."
        result = detect_anchor(
            ROW_ORIENTED_CANDIDATES_WITH_ANCHOR, source_format="row-oriented", threshold=0.1
        )
        assert result.status == "found"
        assert result.column_name == "Jenis Cabai"

    def test_threshold_can_force_escalation_even_with_a_real_anchor_present(self):
        result = detect_anchor(
            ROW_ORIENTED_CANDIDATES_WITH_ANCHOR, source_format="row-oriented", threshold=0.95
        )
        assert result.status == "escalate"

    def test_does_not_pick_bentuk_buah_cabai_over_jenis_cabai(self):
        """Regression test for a real bug: "Bentuk Buah Cabai" (fruit
        shape) used to outscore the actual identity column "Jenis Cabai"
        once sample values were blended into the embedded text, since
        several real varietas names literally contain the word "Cabai" —
        the same lexical overlap the concept phrases and "Bentuk Buah
        Cabai"'s own header share. Must resolve to "Jenis Cabai"."""
        result = detect_anchor(ROW_ORIENTED_CANDIDATES_SINTETIS_1, source_format="row-oriented")
        assert result.status == "found"
        assert result.column_name == "Jenis Cabai"
