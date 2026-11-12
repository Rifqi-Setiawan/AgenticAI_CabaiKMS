"""Gold kanonik 317 foto PVT: foto -> sel kanonik (baris Gambar x kolom varietas) dan tindakan fusi yang benar.

Keputusan peneliti 5 Nov 2026 (D21, docs/DESIGN_DECISIONS.md):
  (1) Bagian tanpa baris Gambar di template (HABITUS, BIJI, TIDAK_JELAS) tetap dinilai; jawaban benar = REVIEW_*.
  (2) Satu foto boleh punya lebih dari satu bagian yang benar (bagian_utama + bagian_boleh).
  (3) Penilaian per foto.
  (4) Gold tidak bergantung pada kartu nama; ada_kartu_nama hanya dipakai untuk memisahkan skor.
Skenario registri: P01 (24 varietas) menjadi varietas run; 10 varietas P02 tidak terdaftar (OTHER).

Dua langkah (jalankan dari akar repo):
  python data_evaluasi/skrip/gold_kanonik_foto_pvt.py --buat-lembar   # lembar anotasi xlsx, terisi usulan awal
  python data_evaluasi/skrip/gold_kanonik_foto_pvt.py --turunkan      # baca lembar -> gold_kanonik_foto_pvt.csv
--buat-lembar menolak menimpa lembar yang sudah ada (bisa berisi hasil verifikasi peneliti).
Peneliti hanya memverifikasi bagian, kartu, dan kelayakan foto; sel dan tindakan diturunkan otomatis oleh aturan di
bawah, supaya gold konsisten dengan keputusan D21.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.tabular_update import IMAGE_ROW_LABELS  # noqa: E402
from src.schema.canonical import CanonicalSchema  # noqa: E402

MANIFEST = ROOT / "data_evaluasi" / "gambar" / "manifest"
SUMBER = MANIFEST / "gold_foto_pvt_317.csv"
LEMBAR = MANIFEST / "lembar_gold_kanonik_foto_pvt.xlsx"
KELUARAN = MANIFEST / "gold_kanonik_foto_pvt.csv"

BAGIAN_SEMUA = ("DAUN", "BATANG", "BUAH", "BUNGA", "HABITUS", "BIJI", "TIDAK_JELAS")
REVIEW = ("REVIEW_UNCERTAIN", "REVIEW_MISMATCH")
KOLOM_LEMBAR = [
    "no", "foto", "filename", "true_variety", "label_kind_skenario_P01", "prioritas",
    "ai_bagian", "ai_keyakinan", "ai_kartu", "ai_catatan",
    "bagian_utama", "bagian_boleh_tambahan", "ada_kartu_nama", "foto_layak", "diperiksa", "catatan_peneliti",
]
KOLOM_GOLD = [
    "filename", "berkas", "true_variety", "label_kind_skenario_P01", "in_registry_skenario_P01",
    "bagian_utama", "bagian_boleh", "ada_kartu_nama", "foto_layak", "dinilai_kanonik",
    "expected_canonical_row", "canonical_rows_boleh", "expected_column",
    "expected_fusion", "fusion_boleh", "aturan", "annotation_source_part", "file_sha256", "no_publikasi",
]


def baris_gambar(schema: CanonicalSchema | None = None) -> dict[str, str]:
    """Bagian -> label baris Gambar, dicek terhadap template yang dimuat (cocok per label, bukan nomor baris)."""
    schema = schema or CanonicalSchema.from_template()
    out = {}
    for bagian, label in IMAGE_ROW_LABELS.items():
        if schema.row_by_label(label) is None:
            raise ValueError(f"Baris '{label}' untuk bagian {bagian} tidak ada di template kanonik")
        out[bagian] = label
    return out


def urai_bagian(teks: str) -> list[str]:
    """'DAUN | batang' -> ['DAUN', 'BATANG']; urutan dipertahankan, tanpa duplikat."""
    hasil = []
    for t in (teks or "").replace(",", "|").replace(";", "|").split("|"):
        t = t.strip().upper().replace(" ", "_")
        if not t:
            continue
        if t not in BAGIAN_SEMUA:
            raise ValueError(f"Kode bagian tidak dikenal: {t!r} (pilihan: {', '.join(BAGIAN_SEMUA)})")
        if t not in hasil:
            hasil.append(t)
    return hasil


def turunkan(bagian_utama: str, bagian_boleh: list[str], label_kind: str, true_variety: str,
             peta: dict[str, str], foto_layak: str = "Y") -> dict[str, str]:
    """Aturan D21. bagian_boleh sudah memuat bagian_utama."""
    if label_kind not in ("KNOWN", "OTHER"):
        raise ValueError(f"label_kind tidak dikenal: {label_kind!r}")
    if bagian_utama not in BAGIAN_SEMUA:
        raise ValueError(f"bagian_utama tidak dikenal: {bagian_utama!r}")
    if foto_layak != "Y":
        return {"dinilai_kanonik": "N", "expected_canonical_row": "", "canonical_rows_boleh": "",
                "expected_column": "", "expected_fusion": "", "fusion_boleh": "",
                "aturan": "foto tidak layak menurut peneliti; tidak dinilai"}
    rows_boleh = [peta[b] for b in bagian_boleh if b in peta]
    punya_baris = bagian_utama in peta
    if label_kind == "KNOWN":
        if punya_baris:
            return {"dinilai_kanonik": "Y", "expected_canonical_row": peta[bagian_utama],
                    "canonical_rows_boleh": "|".join(rows_boleh), "expected_column": true_variety,
                    "expected_fusion": "AUTO_LINK", "fusion_boleh": "AUTO_LINK",
                    "aturan": "KNOWN + bagian berbaris Gambar -> AUTO_LINK ke sel Gambar x varietas"}
        boleh = list(REVIEW) + (["AUTO_LINK"] if rows_boleh else [])
        return {"dinilai_kanonik": "Y", "expected_canonical_row": "", "canonical_rows_boleh": "|".join(rows_boleh),
                "expected_column": true_variety if rows_boleh else "",
                "expected_fusion": "REVIEW", "fusion_boleh": "|".join(boleh),
                "aturan": f"KNOWN + {bagian_utama} tanpa baris Gambar -> REVIEW"
                          + ("; AUTO_LINK ke baris bagian_boleh juga benar" if rows_boleh else "")}
    if punya_baris:
        return {"dinilai_kanonik": "Y", "expected_canonical_row": "", "canonical_rows_boleh": "|".join(rows_boleh),
                "expected_column": "", "expected_fusion": "CANDIDATE", "fusion_boleh": "CANDIDATE",
                "aturan": "OTHER (varietas tidak di registri run) -> CANDIDATE, tidak ditulis ke sel"}
    boleh = list(REVIEW) + (["CANDIDATE"] if rows_boleh else [])
    return {"dinilai_kanonik": "Y", "expected_canonical_row": "", "canonical_rows_boleh": "|".join(rows_boleh),
            "expected_column": "", "expected_fusion": "REVIEW", "fusion_boleh": "|".join(boleh),
            "aturan": f"OTHER + {bagian_utama} tanpa baris Gambar -> REVIEW"
                      + ("; CANDIDATE juga benar (bagian_boleh berbaris)" if rows_boleh else "")}


def _baca(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def buat_lembar() -> None:
    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    if LEMBAR.exists():
        raise SystemExit(f"{LEMBAR} sudah ada (mungkin berisi verifikasi); pindahkan dulu bila ingin membuat ulang.")
    sumber = _baca(SUMBER)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Anotasi"
    ws.append(KOLOM_LEMBAR)
    kuning = PatternFill("solid", fgColor="FFF2CC")
    biru = PatternFill("solid", fgColor="DDEBF7")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, r in enumerate(sumber, start=1):
        prioritas = 1 if (r["keyakinan_part"] == "L" or r["true_part"] == "TIDAK_JELAS" or r["catatan"]) else 2
        ws.append([i, None, r["filename"], r["true_variety"], r["label_kind_skenario_P01"], prioritas,
                   r["true_part"], r["keyakinan_part"], r["ada_kartu_nama"], r["catatan"],
                   r["true_part"], "", r["ada_kartu_nama"], "Y", "", ""])
        n = i + 1
        img = XLImage(str(ROOT / r["berkas"]))
        img.width = img.height = 110
        ws.add_image(img, f"B{n}")
        ws.row_dimensions[n].height = 86
        for col in ("K", "L", "M", "N", "O", "P"):
            ws[f"{col}{n}"].fill = biru
        if prioritas == 1:
            for col in ("F", "G", "H"):
                ws[f"{col}{n}"].fill = kuning
    lebar = {"A": 5, "B": 16, "C": 26, "D": 20, "E": 10, "F": 8, "G": 11, "H": 8, "I": 7, "J": 30,
             "K": 13, "L": 18, "M": 9, "N": 8, "O": 9, "P": 30}
    for col, w in lebar.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:P{len(sumber) + 1}"
    akhir = len(sumber) + 1
    dv_bagian = DataValidation(type="list", formula1='"' + ",".join(BAGIAN_SEMUA) + '"', allow_blank=False)
    dv_yn = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    ws.add_data_validation(dv_bagian)
    ws.add_data_validation(dv_yn)
    dv_bagian.add(f"K2:K{akhir}")
    for col in ("M", "N", "O"):
        dv_yn.add(f"{col}2:{col}{akhir}")

    p = wb.create_sheet("Petunjuk")
    for baris in [
        "Gold kanonik 317 foto PVT. Isi hanya kolom biru (K-P); kolom lain jangan diubah.",
        "",
        "bagian_utama: bagian tanaman yang paling jelas (sudah terisi usulan awal; ganti bila salah).",
        "  DAUN, BATANG, BUAH, BUNGA = punya baris Gambar di template.",
        "  HABITUS (tanaman utuh), BIJI, TIDAK_JELAS (objek tidak terlihat) = tidak punya baris Gambar.",
        "bagian_boleh_tambahan: bagian lain yang juga jelas terlihat dan boleh dianggap benar, pisahkan dengan |",
        "  (mis. foto buah yang daunnya juga jelas: DAUN). Kosongkan bila tidak ada.",
        "ada_kartu_nama: Y bila ada tulisan nama/singkatan varietas di foto (bocoran label).",
        "foto_layak: N bila foto tidak bisa dipakai sama sekali (rusak, bukan cabai). N = tidak dinilai.",
        "diperiksa: isi Y setelah baris ini kamu periksa.",
        "prioritas 1 (kuning) = usulan berkeyakinan rendah, TIDAK_JELAS, atau ada catatan: periksa dulu.",
        "",
        "Kolom sel dan tindakan TIDAK diisi di sini. Skrip --turunkan menghitungnya dengan aturan D21:",
        "  KNOWN + bagian berbaris  -> AUTO_LINK ke sel Gambar <bagian> x kolom varietas",
        "  KNOWN + bagian tanpa baris -> REVIEW (AUTO_LINK ke baris bagian_boleh juga benar bila ada)",
        "  OTHER + bagian berbaris  -> CANDIDATE (varietas P02 tidak ada di registri run)",
        "  OTHER + bagian tanpa baris -> REVIEW (CANDIDATE juga benar bila bagian_boleh berbaris)",
        "Skenario: P01 (24 varietas) = varietas run (KNOWN); P02 (10 varietas lokal) = OTHER.",
        "Penilaian per foto. Gold tidak bergantung kartu nama; kartu hanya untuk memisahkan skor.",
    ]:
        p.append([baris])
    p.column_dimensions["A"].width = 110
    LEMBAR.parent.mkdir(parents=True, exist_ok=True)
    wb.save(LEMBAR)
    print(f"{len(sumber)} foto -> {LEMBAR.relative_to(ROOT)}")


def _teks(v) -> str:
    return "" if v is None else str(v).strip()


def turunkan_gold() -> list[dict]:
    import openpyxl

    sumber = {r["filename"]: r for r in _baca(SUMBER)}
    peta = baris_gambar()
    ws = openpyxl.load_workbook(LEMBAR, read_only=True, data_only=True)["Anotasi"]
    rows = list(ws.iter_rows(values_only=True))
    idx = {k: i for i, k in enumerate(rows[0])}
    hasil, galat = [], []
    for r in rows[1:]:
        fn = _teks(r[idx["filename"]])
        if not fn:
            continue
        s = sumber.get(fn)
        if s is None:
            galat.append(f"{fn}: tidak ada di {SUMBER.name}")
            continue
        try:
            utama = urai_bagian(_teks(r[idx["bagian_utama"]]) or s["true_part"])
            if len(utama) != 1:
                raise ValueError("bagian_utama harus tepat satu kode")
            boleh = utama + [b for b in urai_bagian(_teks(r[idx["bagian_boleh_tambahan"]])) if b not in utama]
            kartu = _teks(r[idx["ada_kartu_nama"]]).upper() or s["ada_kartu_nama"]
            layak = _teks(r[idx["foto_layak"]]).upper() or "Y"
            if kartu not in ("Y", "N") or layak not in ("Y", "N"):
                raise ValueError("ada_kartu_nama dan foto_layak harus Y atau N")
            d = turunkan(utama[0], boleh, s["label_kind_skenario_P01"], s["true_variety"], peta, layak)
        except ValueError as e:
            galat.append(f"{fn}: {e}")
            continue
        diperiksa = _teks(r[idx["diperiksa"]]).upper() == "Y"
        hasil.append({
            "filename": fn, "berkas": s["berkas"], "true_variety": s["true_variety"],
            "label_kind_skenario_P01": s["label_kind_skenario_P01"],
            "in_registry_skenario_P01": s["in_registry_skenario_P01"],
            "bagian_utama": utama[0], "bagian_boleh": "|".join(boleh), "ada_kartu_nama": kartu, "foto_layak": layak,
            **d,
            "annotation_source_part": "terverifikasi_v1",
            "file_sha256": s["file_sha256"], "no_publikasi": s["no_publikasi"],
        })
    if galat:
        raise SystemExit("Lembar belum valid:\n  " + "\n  ".join(galat))
    hilang = set(sumber) - {h["filename"] for h in hasil}
    if hilang:
        raise SystemExit(f"{len(hilang)} foto tidak ada di lembar, mis. {sorted(hilang)[:3]}")
    return hasil


def tulis_gold(hasil: list[dict]) -> None:
    with open(KELUARAN, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=KOLOM_GOLD, lineterminator="\n")
        w.writeheader()
        w.writerows(hasil)
    from collections import Counter
    print(f"{len(hasil)} foto -> {KELUARAN.relative_to(ROOT)}")
    print("  terverifikasi:", sum(h["annotation_source_part"] == "terverifikasi_v1" for h in hasil))
    print("  expected_fusion:", dict(Counter(h["expected_fusion"] or "-" for h in hasil)))
    print("  baris kanonik:", dict(Counter(h["expected_canonical_row"] or "-" for h in hasil)))


if __name__ == "__main__":
    if "--buat-lembar" in sys.argv:
        buat_lembar()
    elif "--turunkan" in sys.argv:
        tulis_gold(turunkan_gold())
    else:
        sys.exit("Pilih --buat-lembar atau --turunkan")
