"""Integritas dataset berpasangan PVT (spreadsheet P01/P02 + gold atribut + kunci sel + gold foto).

Dibangun oleh data_evaluasi/skrip/buat_dataset_pvt.py. Tes ini tidak memanggil LLM atau embedding.
"""
import csv
import hashlib
from pathlib import Path

import pytest

from src.agents.schema_matching.source_parsing import load_row_oriented_columns, load_transposed_rows
from src.schema.canonical import CanonicalSchema
from src.schema.gold_mapping import build_mapping_item_identities, load_gold_annotations

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "data_evaluasi"
GOLD = EV / "gold" / "gold_P01_P02_pvt.csv"
KEYS = EV / "gold" / "kunci_sel" / "kunci_sel_pvt.csv"
FOTO = EV / "gambar" / "manifest" / "gold_foto_pvt_317.csv"
INPUTS = {
    "P01": (EV / "inputs" / "P01_pvt_hasil_pemuliaan_24.xlsx", "Deskripsi Varietas", "row-oriented"),
    "P02": (EV / "inputs" / "P02_pvt_varietas_lokal_10.xlsx", "transposed", "transposed"),
}
VISION_PARTS = {"DAUN", "BATANG", "BUAH", "BUNGA"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _attrs(dataset_id: str):
    path, sheet, fmt = INPUTS[dataset_id]
    if fmt == "transposed":
        attrs, names = load_transposed_rows(path, sheet)
        return attrs, list(names)
    attrs = load_row_oriented_columns(path, sheet, header_rows=1)
    anchor = next(a for a in attrs if a.attribute_name.casefold() == "varietas cabai")
    return attrs, [v.strip() for v in anchor.row_values if v]


@pytest.fixture(scope="module")
def schema():
    return CanonicalSchema.from_template()


def test_gold_loads_strictly_against_canonical_schema(schema, tmp_path):
    # Loader ketat hanya menerima sumber human_independent/adjudicated/legacy_unverified dengan annotator_id terisi.
    # Struktur, status, kunci kanonik, dan identitas butir divalidasi lewat salinan berlabel legacy_unverified;
    # berkas asli tidak diubah.
    rows = _rows(GOLD)
    copy = tmp_path / "gold.csv"
    with open(copy, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({**r, "annotation_source": "legacy_unverified", "annotator_id": "uji"})
    gold = load_gold_annotations(copy, schema=schema)
    assert len(gold.annotations) == len(rows)


@pytest.mark.parametrize("dataset_id", sorted(INPUTS))
def test_gold_ids_match_current_workbook(dataset_id):
    path, sheet, fmt = INPUTS[dataset_id]
    rows = [r for r in _rows(GOLD) if r["dataset_id"] == dataset_id]
    assert {r["source_file_sha256"] for r in rows} == {_sha(path)}
    attrs, _ = _attrs(dataset_id)
    idents = build_mapping_item_identities(
        source_file_sha256=_sha(path), source_sheet=sheet, source_format=fmt,
        source_items=[(None, a.display_name) for a in attrs],
    )
    # Setiap atribut hasil parser punya tepat satu butir gold dengan ID yang sama.
    assert sorted(i.mapping_item_id for i in idents) == sorted(r["mapping_item_id"] for r in rows)


def test_gold_source_marks_p01_verified_and_p02_unverified():
    sources = {(r["dataset_id"], r["annotation_source"]) for r in _rows(GOLD)}
    assert sources == {("P01", "terverifikasi_v1"), ("P02", "belum_diverifikasi_v1")}
    assert all(not r["annotator_id"] for r in _rows(GOLD))


def test_cell_keys_reference_known_varieties_and_one_to_one_gold():
    one = {(r["dataset_id"], r["source_attribute_display"], r["gold_canonical_keys"])
           for r in _rows(GOLD) if r["gold_status"] == "ONE_TO_ONE"}
    varieties = {ds: set(_attrs(ds)[1]) for ds in INPUTS}
    keys = _rows(KEYS)
    assert keys
    for k in keys:
        assert k["varietas"] in varieties[k["dataset"]]
        assert (k["dataset"], k["atribut_sumber"], k["canonical_key"]) in one
        assert k["nilai_sumber"].strip()


def test_photo_manifest_files_exist_and_labels_are_variety_level():
    rows = _rows(FOTO)
    assert len(rows) == 317
    all_varieties = set(_attrs("P01")[1]) | set(_attrs("P02")[1])
    p01 = set(_attrs("P01")[1])
    for r in rows:
        path = ROOT / r["berkas"]
        assert _sha(path) == r["file_sha256"], r["berkas"]
        assert r["true_variety"] in all_varieties
        assert r["label_kind_skenario_P01"] == ("KNOWN" if r["true_variety"] in p01 else "OTHER")
        assert r["part_dinilai"] == ("Y" if r["true_part"] in VISION_PARTS else "N")
    assert len({r["true_variety"] for r in rows}) == 34
