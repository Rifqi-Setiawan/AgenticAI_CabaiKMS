"""Buat lembar verifikasi gold (atribut dan foto) dari usulan awal, untuk diperiksa reviewer manusia.

Keluaran ke verifikasi_gold/ :
  verifikasi_atribut.xlsx   (326 butir; sheet Petunjuk, Verifikasi, Canonical Reference)
  verifikasi_foto.xlsx      (160 foto; sheet Petunjuk, Verifikasi)

Kolom keputusan dibiarkan kosong. Usulan awal disusun dengan bantuan model bahasa dan dicatat apa adanya pada kolom asal usulan.
"""
import csv
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verifikasi_gold"
OUT.mkdir(exist_ok=True)

HEAD = PatternFill("solid", fgColor="1F3864")
HEAD_USUL = PatternFill("solid", fgColor="7F7F7F")
HEAD_REV = PatternFill("solid", fgColor="2E75B6")
WHITE = Font(color="FFFFFF", bold=True)


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def style_header(ws, fills):
    for idx, fill in enumerate(fills, start=1):
        c = ws.cell(row=1, column=idx)
        c.fill, c.font = fill, WHITE
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions


def widths(ws, spec):
    for idx, w in enumerate(spec, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w


def petunjuk(ws, lines):
    ws.column_dimensions["A"].width = 150
    for i, text in enumerate(lines, start=1):
        c = ws.cell(row=i, column=1, value=text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            c.font = Font(bold=True, size=13)


def atribut():
    gold = read(ROOT / "gold" / "gold_semua_dataset.csv")
    ref = load_workbook(ROOT / "gold" / "gold_semua_dataset.xlsx")["Canonical Reference"]
    wb = Workbook()
    p = wb.active
    p.title = "Petunjuk"
    petunjuk(p, [
        "LEMBAR VERIFIKASI GOLD PEMETAAN ATRIBUT",
        "Usulan awal (kolom abu-abu) disusun dengan bantuan model bahasa. Tugas reviewer: memeriksa tiap butir terhadap Canonical Reference dan contoh nilai sumber, lalu mengisi kolom biru.",
        "1. Kolom 'keputusan': SETUJU (usulan benar), UBAH (isi kolom final), atau RAGU (butir sulit; akan dibahas dengan pembimbing).",
        "2. Bila UBAH: isi 'gold_status_final' (ONE_TO_ONE, NO_MATCH, AMBIGUOUS, COMPOSITE, EXCLUDE) dan 'gold_canonical_keys_final' (kunci dari sheet Canonical Reference, dipisah ' | ' bila lebih dari satu). Bila SETUJU, kolom final boleh dikosongkan.",
        "3. ONE_TO_ONE = tepat satu baris kanonik. NO_MATCH = tidak ada padanan di 59 baris kanonik. AMBIGUOUS = dua atau lebih kandidat sama masuk akal (isi kandidatnya). COMPOSITE = satu kolom sumber memuat lebih dari satu karakter kanonik. EXCLUDE = bukan atribut (mis. kolom identitas varietas).",
        "4. Prioritas: urutkan/filter kolom 'prioritas_periksa' = Y lebih dulu (57 butir yang ditandai ragu pada usulan).",
        "5. Isi 'reviewer_id' (nama atau inisial) dan 'tanggal' pada setiap butir yang diperiksa. Jangan mengisi atas nama orang lain.",
        "6. Setelah selesai, jalankan skrip terapkan_verifikasi.py. Skrip menolak butir tanpa keputusan dan melaporkan persentase butir yang diubah.",
        "Catatan metodologi: usulan awal dibuat dengan model bahasa, gold final adalah hasil verifikasi manusia. Persentase perubahan dilaporkan pada skripsi.",
    ])
    ws = wb.create_sheet("Verifikasi")
    cols_u = ["mapping_item_id", "dataset_id", "source_attribute_display", "source_context", "contoh_nilai_sumber",
              "usulan_status", "usulan_kunci", "usulan_kandidat_ambiguous", "usulan_catatan", "usulan_keyakinan", "prioritas_periksa"]
    cols_r = ["keputusan", "gold_status_final", "gold_canonical_keys_final", "kandidat_ambiguous_final", "catatan_reviewer", "reviewer_id", "tanggal"]
    ws.append(cols_u + cols_r)
    order = {d: i for i, d in enumerate(["R01", "R02", "N07", "N08", "N09", "S01", "S02", "S03", "S04"])}
    for g in sorted(gold, key=lambda r: (order.get(r["dataset_id"], 99), 0)):
        ws.append([g["mapping_item_id"], g["dataset_id"], g["source_attribute_display"], g["source_context"], g["contoh_nilai_sumber"],
                   g["gold_status"], g["gold_canonical_keys"], g["ambiguous_candidate_canonical_keys"], g["notes"],
                   g["confidence_claude"], g["perlu_adjudikasi"]] + [""] * len(cols_r))
    style_header(ws, [HEAD_USUL] * len(cols_u) + [HEAD_REV] * len(cols_r))
    widths(ws, [14, 9, 36, 28, 40, 14, 28, 24, 40, 10, 10, 12, 16, 28, 24, 40, 14, 12])
    n = ws.max_row
    dv = DataValidation(type="list", formula1='"SETUJU,UBAH,RAGU"', allow_blank=True)
    dv2 = DataValidation(type="list", formula1='"ONE_TO_ONE,NO_MATCH,AMBIGUOUS,COMPOSITE,EXCLUDE"', allow_blank=True)
    ws.add_data_validation(dv)
    ws.add_data_validation(dv2)
    dv.add(f"L2:L{n}")
    dv2.add(f"M2:M{n}")
    for row in ws.iter_rows(min_row=2, max_row=n):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    cr = wb.create_sheet("Canonical Reference")
    for r in ref.iter_rows(values_only=True):
        cr.append(list(r))
    widths(cr, [30, 34, 18, 50, 40])
    cr.freeze_panes = "A2"
    wb.save(OUT / "verifikasi_atribut.xlsx")
    print("verifikasi_atribut.xlsx:", n - 1, "butir")


def foto():
    man = read(ROOT / "gambar" / "manifest" / "gold_gambar_manifest.csv")
    folder = {r["filename"]: r["folder"] for r in read(ROOT / "gambar" / "manifest" / "pembagian_8_folder.csv")}
    wb = Workbook()
    p = wb.active
    p.title = "Petunjuk"
    petunjuk(p, [
        "LEMBAR VERIFIKASI GOLD FOTO",
        "Usulan awal (kolom abu-abu) berasal dari kategori dan judul berkas Wikimedia Commons serta pemeriksaan visual kasar. Reviewer memeriksa foto (folder Drive F1 sampai F8 sesuai kolom folder_drive, atau tautan sumber) dan mengisi kolom biru.",
        "1. 'keputusan': SETUJU, UBAH, atau RAGU. Bila UBAH isi 'label_final' (KNOWN, OTHER, UNCERTAIN) dan 'varietas_final' (untuk KNOWN, salah satu dari 8 varietas terdaftar).",
        "2. KNOWN = varietas terlihat jelas dan termasuk 8 varietas terdaftar (Cabai Rawit, Jalapeno, Habanero, Cayenne, Paprika, Cabai Korea, Serrano, Hungarian Wax). OTHER = cabai varietas lain yang jelas bukan salah satunya. UNCERTAIN = tidak dapat dipastikan dari foto.",
        "3. Kolom 'foto_layak' = T bila foto sebaiknya dikeluarkan (mis. bukan cabai, terlalu kabur, ada watermark atau orang).",
        "4. Isi reviewer_id dan tanggal. Setelah selesai jalankan terapkan_verifikasi.py.",
    ])
    ws = wb.create_sheet("Verifikasi")
    cols_u = ["filename", "folder_drive", "sumber_judul", "sumber_url", "usulan_label", "usulan_varietas", "usulan_bagian", "alasan_uncertain_usulan"]
    cols_r = ["keputusan", "label_final", "varietas_final", "foto_layak", "catatan_reviewer", "reviewer_id", "tanggal"]
    ws.append(cols_u + cols_r)
    for m in man:
        ws.append([m["filename"], folder.get(m["filename"], ""), m["commons_title"], m["source_url"], m["label_kind"], m["true_variety"], m["true_part"],
                   m["uncertain_reason"]] + [""] * len(cols_r))
    style_header(ws, [HEAD_USUL] * len(cols_u) + [HEAD_REV] * len(cols_r))
    widths(ws, [24, 8, 40, 44, 12, 16, 12, 30, 12, 12, 16, 10, 30, 14, 12])
    n = ws.max_row
    for formula, rng in (('"SETUJU,UBAH,RAGU"', f"I2:I{n}"), ('"KNOWN,OTHER,UNCERTAIN"', f"J2:J{n}"), ('"T"', f"L2:L{n}")):
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(rng)
    wb.save(OUT / "verifikasi_foto.xlsx")
    print("verifikasi_foto.xlsx:", n - 1, "foto")


if __name__ == "__main__":
    atribut()
    foto()
