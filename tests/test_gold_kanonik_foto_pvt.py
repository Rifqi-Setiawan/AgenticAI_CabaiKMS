"""Aturan gold kanonik foto PVT (D21): foto -> sel Gambar x varietas dan tindakan fusi yang benar."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "gold_kanonik_foto_pvt", ROOT / "data_evaluasi" / "skrip" / "gold_kanonik_foto_pvt.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

PETA = {"DAUN": "Gambar Daun", "BATANG": "Gambar Batang", "BUAH": "Gambar Buah", "BUNGA": "Gambar Bunga"}


def test_image_rows_exist_in_loaded_template():
    assert g.baris_gambar() == PETA


def test_known_with_image_row_is_auto_link_to_cell():
    d = g.turunkan("BUAH", ["BUAH", "DAUN"], "KNOWN", "Turima 1", PETA)
    assert d["expected_fusion"] == "AUTO_LINK"
    assert d["expected_canonical_row"] == "Gambar Buah"
    assert d["canonical_rows_boleh"] == "Gambar Buah|Gambar Daun"
    assert d["expected_column"] == "Turima 1"
    assert d["fusion_boleh"] == "AUTO_LINK"


def test_known_without_image_row_expects_review():
    d = g.turunkan("HABITUS", ["HABITUS"], "KNOWN", "DH 3", PETA)
    assert d["expected_fusion"] == "REVIEW"
    assert d["fusion_boleh"] == "REVIEW_UNCERTAIN|REVIEW_MISMATCH"
    assert d["expected_canonical_row"] == "" and d["expected_column"] == ""
    assert d["dinilai_kanonik"] == "Y"


def test_known_without_row_but_allowed_part_also_accepts_auto_link():
    d = g.turunkan("HABITUS", ["HABITUS", "BATANG"], "KNOWN", "DH 3", PETA)
    assert d["expected_fusion"] == "REVIEW"
    assert d["fusion_boleh"].split("|") == ["REVIEW_UNCERTAIN", "REVIEW_MISMATCH", "AUTO_LINK"]
    assert d["canonical_rows_boleh"] == "Gambar Batang"
    assert d["expected_column"] == "DH 3"


def test_other_is_candidate_and_never_written_to_a_cell():
    d = g.turunkan("DAUN", ["DAUN"], "OTHER", "Jabung", PETA)
    assert d["expected_fusion"] == "CANDIDATE"
    assert d["expected_column"] == "" and d["expected_canonical_row"] == ""


def test_other_without_image_row_expects_review():
    d = g.turunkan("BIJI", ["BIJI"], "OTHER", "Jabung", PETA)
    assert d["expected_fusion"] == "REVIEW"
    assert "CANDIDATE" not in d["fusion_boleh"]


def test_unusable_photo_is_not_scored():
    d = g.turunkan("BUAH", ["BUAH"], "KNOWN", "Indina", PETA, foto_layak="N")
    assert d["dinilai_kanonik"] == "N" and d["expected_fusion"] == ""


def test_part_parsing_normalises_and_rejects_unknown_codes():
    assert g.urai_bagian(" daun | Batang ;daun") == ["DAUN", "BATANG"]
    assert g.urai_bagian("tidak jelas") == ["TIDAK_JELAS"]
    with pytest.raises(ValueError):
        g.urai_bagian("AKAR")
    with pytest.raises(ValueError):
        g.turunkan("BUAH", ["BUAH"], "UNCERTAIN", "Indina", PETA)


@pytest.mark.skipif(not g.LEMBAR.exists(), reason="lembar anotasi belum dibuat")
def test_sheet_derives_gold_for_all_317_photos():
    hasil = g.turunkan_gold()
    assert len(hasil) == 317
    for h in hasil:
        if h["dinilai_kanonik"] == "N":
            continue
        if h["expected_fusion"] == "AUTO_LINK":
            assert h["label_kind_skenario_P01"] == "KNOWN"
            assert h["expected_column"] == h["true_variety"]
            assert h["expected_canonical_row"] == PETA[h["bagian_utama"]]
        if h["label_kind_skenario_P01"] == "OTHER":
            assert h["expected_column"] == ""
