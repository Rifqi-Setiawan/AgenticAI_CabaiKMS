"""Bangun dataset berpasangan PVT: spreadsheet input + gold atribut + kunci sel + gold foto, untuk 34 varietas
cabai terdaftar dari Berita Resmi PVT Kementan (sumber yang sama dengan 317 foto pvt_kementan_34_varietas).

Keluaran (relatif ke data_evaluasi/):
  inputs/P01_pvt_hasil_pemuliaan_24.xlsx   row-oriented, sheet "Deskripsi Varietas", 24 varietas hasil pemuliaan
  inputs/P02_pvt_varietas_lokal_10.xlsx    transposed, sheet "transposed" (baris "Karakter"), 10 varietas lokal
  gold/gold_P01_P02_pvt.csv                gold pemetaan atribut (belum diverifikasi)
  gold/kunci_sel/kunci_sel_pvt.csv          kunci nilai per sel (atribut ONE_TO_ONE), format kunci_sel_semua.csv
  gambar/manifest/gold_foto_pvt_317.csv     gold varietas per foto (label resmi dokumen) + skenario registri

Jalankan dari akar repo:  python -I data_evaluasi/skrip/buat_dataset_pvt.py
Membutuhkan pdftotext (poppler-utils) dan dependensi proyek (parser src/ dipakai untuk mapping_item_id).
"""
from __future__ import annotations

import csv
import hashlib
import sys
from collections import Counter, OrderedDict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[2]
SKRIP = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SKRIP))

import annotations_pvt as AP  # noqa: E402
import pvt_ekstrak as PE  # noqa: E402
from src.agents.schema_matching.source_parsing import load_row_oriented_columns, load_transposed_rows  # noqa: E402
from src.schema.gold_mapping import build_mapping_item_identities  # noqa: E402
from src.schema.provenance import source_file_sha256  # noqa: E402

EV = ROOT / "data_evaluasi"
PVT = ROOT / "dataset_eksperimen" / "2_input_foto" / "pvt_kementan_34_varietas"
PDF_DIR = PVT / "sumber_pdf"
OUT_P01 = EV / "inputs" / "P01_pvt_hasil_pemuliaan_24.xlsx"
OUT_P02 = EV / "inputs" / "P02_pvt_varietas_lokal_10.xlsx"
OUT_GOLD = EV / "gold" / "gold_P01_P02_pvt.csv"
OUT_KEY = EV / "gold" / "kunci_sel" / "kunci_sel_pvt.csv"
OUT_FOTO = EV / "gambar" / "manifest" / "gold_foto_pvt_317.csv"

ANNOTATOR = ""
SOURCE = "belum_diverifikasi_v1"
HDR = PatternFill("solid", fgColor="1F4E78")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_docs() -> list[dict]:
    urls = {}
    with open(PVT / "daftar_berita_resmi_cabai.tsv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            urls[r["berkas"]] = r["url"]
    docs = []
    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        d = PE.parse_pdf(pdf)
        d["sha256"] = sha256(pdf)
        d["url"] = urls.get(pdf.name, "")
        docs.append(d)
    return docs


def merge_case_variants(docs: list[dict]) -> list[tuple[str, str]]:
    """Satukan label yang hanya beda huruf besar/kecil/spasi (parser proyek menganggapnya duplikat).

    Bentuk yang dipakai = kemunculan pertama. Mengembalikan daftar (label asli, label dipakai) yang diubah.
    """
    first, changed = {}, []
    for d in docs:
        new = []
        for lab, val in d["attrs"]:
            key = " ".join(lab.casefold().split())
            use = first.setdefault(key, lab)
            if use != lab:
                changed.append((d["meta"]["varietas"], lab, use))
            new.append((use, val))
        assert len({lab for lab, _ in new}) == len(new), f"label ganda setelah penyatuan: {d['pdf']}"
        d["attrs"] = new
    return changed


def ordered_labels(docs: list[dict]) -> list[str]:
    seen = OrderedDict()
    for d in docs:
        for lab, _ in d["attrs"]:
            seen.setdefault(lab, None)
    return list(seen)


def identity_cols(d: dict, lokal: bool) -> list[tuple[str, str]]:
    m = d["meta"]
    cols = [("Nama Umum", m.get("nama_umum", "")), ("Spesies", m.get("spesies", ""))]
    if lokal and m.get("sebaran_geografis"):
        cols.append(("Sebaran Geografis", m["sebaran_geografis"]))
    return cols


def style_header(ws, row=1):
    for c in ws[row]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HDR
        c.alignment = Alignment(wrap_text=True, vertical="top")


FIXED_TS = "2026-11-05T00:00:00Z"


def save_deterministic(wb, path: Path):
    """Simpan workbook dengan tanggal metadata dan timestamp zip tetap, agar SHA-256 (dan mapping_item_id)
    sama setiap kali skrip dijalankan ulang."""
    import io
    import re
    import zipfile
    buf = io.BytesIO()
    wb.save(buf)
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:)", rb"\g<1>" +
                              FIXED_TS.encode() + rb"\g<3>", data)
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 11, 5, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(zi, data)
    path.write_bytes(out.getvalue())


def write_sumber(wb, docs):
    ws = wb.create_sheet("sumber")
    ws.append(["Varietas", "Nama umum", "Spesies", "Jalur", "No. Publikasi", "No. Pendaftaran", "Tanggal Pendaftaran",
               "Berkas PDF", "SHA-256 PDF", "URL", "Tata letak deskripsi", "Catatan"])
    for d in docs:
        m = d["meta"]
        ws.append([m["varietas"], m.get("nama_umum"), m.get("spesies"), m["jalur"], m.get("no_publikasi"),
                   m.get("no_pendaftaran"), m.get("tanggal_pendaftaran"), d["pdf"], d["sha256"], d["url"], d["layout"],
                   "Label dan nilai disalin apa adanya dari lapisan teks PDF (pdftotext -layout). Nama orang "
                   "(pemohon, pemulia, pendeskripsi) tidak disalin. Label yang hanya beda huruf besar/kecil "
                   "disatukan ke bentuk yang muncul pertama (parser proyek menganggapnya duplikat)."])
    style_header(ws)
    ws.append([])
    ws.append(["Sumber: Berita Resmi PVT, Pusat PVTPP Kementerian Pertanian RI, "
               "https://ppvtpp.setjen.pertanian.go.id/publikasi/berita-resmi-pvt (diunduh 3 Nov 2026). "
               "Cantumkan No. Publikasi bila dipublikasikan. Dibuat oleh data_evaluasi/skrip/buat_dataset_pvt.py."])


def build_p01(docs: list[dict]):
    labels = ordered_labels(docs)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Deskripsi Varietas"
    head = ["Varietas Cabai", "Nama Umum", "Spesies"] + labels
    ws.append(head)
    for d in docs:
        vals = dict(d["attrs"])
        ws.append([d["meta"]["varietas"]] + [v for _, v in identity_cols(d, False)] + [vals.get(lab) for lab in labels])
    style_header(ws)
    ws.freeze_panes = "B2"
    write_sumber(wb, docs)
    save_deterministic(wb, OUT_P01)


def build_p02(docs: list[dict]):
    labels = ["Nama Umum", "Spesies", "Sebaran Geografis"] + ordered_labels(docs)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "transposed"
    ws.append(["Karakter"] + [d["meta"]["varietas"] for d in docs])
    per_doc = [dict(identity_cols(d, True) + d["attrs"]) for d in docs]
    for lab in labels:
        ws.append([lab] + [vals.get(lab) for vals in per_doc])
    style_header(ws)
    ws.freeze_panes = "B2"
    write_sumber(wb, docs)
    save_deterministic(wb, OUT_P02)


COLS = ["annotation_version", "annotation_source", "mapping_item_id", "mapping_identity_kind", "mapping_identity_value",
        "mapping_identity_issue", "dataset_id", "source_file_name", "source_file_sha256", "source_sheet", "source_format",
        "source_attribute_display", "source_attribute", "source_context", "contoh_nilai_sumber", "gold_status",
        "gold_canonical_keys", "ambiguous_candidate_canonical_keys", "annotator_id", "annotation_round", "notes",
        "confidence_usulan", "perlu_adjudikasi", "rule_source"]


def gold_rows(dataset_id: str, path: Path, sheet: str, fmt: str):
    attrs = load_transposed_rows(path, sheet)[0] if fmt == "transposed" else \
        load_row_oriented_columns(path, sheet, header_rows=1)
    sha = source_file_sha256(path)
    idents = build_mapping_item_identities(source_file_sha256=sha, source_sheet=sheet, source_format=fmt,
                                           source_items=[(None, a.display_name) for a in attrs])
    rows, missing = [], []
    for a, i in zip(attrs, idents):
        rule = AP.annotate(a.display_name)
        if rule is None:
            missing.append(a.display_name)
            continue
        status, keys, amb, note, conf, src = rule
        rows.append(OrderedDict(
            annotation_version="schema-mapping-gold-v1", annotation_source=SOURCE, mapping_item_id=i.mapping_item_id,
            mapping_identity_kind=getattr(i.identity_kind, "value", str(i.identity_kind)),
            mapping_identity_value=i.identity_value, mapping_identity_issue=i.issue_code or "", dataset_id=dataset_id,
            source_file_name=path.name, source_file_sha256=sha, source_sheet=sheet, source_format=fmt,
            source_attribute_display=a.display_name, source_attribute=a.attribute_name,
            source_context=a.structural_context or "",
            contoh_nilai_sumber=" || ".join(str(v)[:60] for v in a.sample_values[:3]),
            gold_status=status, gold_canonical_keys=keys, ambiguous_candidate_canonical_keys=amb,
            annotator_id=ANNOTATOR, annotation_round=1, notes=note, confidence_usulan=conf,
            perlu_adjudikasi="N" if conf == "H" else "Y", rule_source=src))
    if missing:
        raise SystemExit(f"{dataset_id}: label tanpa aturan anotasi: {missing}")
    ids = [r["mapping_item_id"] for r in rows]
    assert len(ids) == len(set(ids)), f"mapping_item_id ganda pada {dataset_id}"
    return rows


def validate_keys(rows):
    import yaml
    valid = {r["canonical_key"] for r in yaml.safe_load(open(ROOT / "src/schema/row_keys.yaml"))["rows"]}
    for r in rows:
        for k in (r["gold_canonical_keys"] + "|" + r["ambiguous_candidate_canonical_keys"]).split("|"):
            if k and k not in valid:
                raise SystemExit(f"kunci kanonik tidak dikenal: {k} ({r['source_attribute_display']})")


def cell_keys(dataset_id, docs, rows, lokal):
    one = {r["source_attribute_display"]: r["gold_canonical_keys"] for r in rows if r["gold_status"] == "ONE_TO_ONE"}
    out = []
    for d in docs:
        for lab, val in identity_cols(d, lokal) + d["attrs"]:
            if lab in one:
                out.append([dataset_id, one[lab], d["meta"]["varietas"], lab, val])
    return out


def foto_manifest(docs_by_variety, registry_p01):
    import anotasi_bagian_pvt as AB
    parts = AB.load()
    out = []
    with open(PVT / "daftar_foto.csv", encoding="utf-8") as fh:
        for idx, r in enumerate(csv.DictReader(fh)):
            d = docs_by_variety[r["varietas"]]
            known = r["varietas"] in registry_p01
            berkas = r["berkas"].removeprefix("foto/")  # di repo foto langsung di bawah folder varietas
            assert sha256(PVT / berkas) == r["sha256"], f"SHA-256 tidak cocok: {berkas}"
            part, kartu, conf = parts[idx]
            out.append(OrderedDict(
                filename=Path(berkas).name, berkas=f"dataset_eksperimen/2_input_foto/pvt_kementan_34_varietas/{berkas}",
                true_variety=r["varietas"], nama_umum=r["nama_umum"], spesies=r["spesies"], jalur=r["jalur"],
                label_kind_skenario_P01=("KNOWN" if known else "OTHER"),
                in_registry_skenario_P01=("Y" if known else "N"),
                true_part=part, part_dinilai=("Y" if part in {"DAUN", "BATANG", "BUAH", "BUNGA"} else "N"),
                keyakinan_part=conf, ada_kartu_nama=kartu, lebar=r["lebar"], tinggi=r["tinggi"],
                file_sha256=r["sha256"], sumber_pdf=r["sumber_pdf"], no_publikasi=d["meta"].get("no_publikasi", ""),
                source_url=d["url"],
                annotation_source_variety="label_dokumen_resmi_pvt",
                annotation_source_part="terverifikasi_v1",
                catatan=AB.CATATAN.get(idx, "")))
    return out


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([r[c] for c in header] if isinstance(r, dict) else r)


def main():
    docs = load_docs()
    pem = [d for d in docs if d["meta"]["jalur"] == "hasil_pemuliaan"]
    lok = [d for d in docs if d["meta"]["jalur"] == "lokal"]
    for name, group in (("P01", pem), ("P02", lok)):
        for var, old, new in merge_case_variants(group):
            print(f"{name} label disatukan: {var}: {old!r} -> {new!r}")
    build_p01(pem)
    build_p02(lok)
    g1 = gold_rows("P01", OUT_P01, "Deskripsi Varietas", "row-oriented")
    g2 = gold_rows("P02", OUT_P02, "transposed", "transposed")
    validate_keys(g1 + g2)
    write_csv(OUT_GOLD, COLS, g1 + g2)
    write_csv(OUT_KEY, ["dataset", "canonical_key", "varietas", "atribut_sumber", "nilai_sumber"],
              cell_keys("P01", pem, g1, False) + cell_keys("P02", lok, g2, True))
    by_var = {d["meta"]["varietas"]: d for d in docs}
    foto = foto_manifest(by_var, {d["meta"]["varietas"] for d in pem})
    write_csv(OUT_FOTO, list(foto[0].keys()), foto)
    for name, g in (("P01", g1), ("P02", g2)):
        st = Counter(r["gold_status"] for r in g)
        print(name, len(g), "butir", dict(st), "perlu adjudikasi:", sum(r["perlu_adjudikasi"] == "Y" for r in g),
              "aturan baru:", sum(r["rule_source"] == "pvt_baru" for r in g))
    print("foto:", len(foto), Counter(r["label_kind_skenario_P01"] for r in foto))
    for p in (OUT_P01, OUT_P02):
        print(p.name, source_file_sha256(p))


if __name__ == "__main__":
    main()
