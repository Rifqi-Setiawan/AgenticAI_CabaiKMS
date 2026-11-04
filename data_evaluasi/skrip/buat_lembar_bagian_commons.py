"""Lembar anotasi bagian tanaman untuk 160 foto Commons (gold bagian dibuat peneliti, 4 Nov 2026).

Varietas gold tetap dari kategori Commons; yang dianotasi hanya bagian tanaman (baris Gambar Daun/Batang/Buah/Bunga).
Anotasi buta: lembar hanya berisi nomor dan foto. Nama file (yang bisa memuat kata "buah"/"daun"), label bagian lama,
varietas, dan prediksi sistem tidak ditampilkan. Urutan diacak (seed tetap) agar foto satu varietas tidak berkumpul.
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\buat_lembar_bagian_commons.py
Keluaran: gold/bagian_foto_commons/lembar_bagian_160.xlsx dan kunci_nomor.csv (nomor -> folder, nama file).
"""
import csv
import io
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image

FOTO = Path("gambar/drive_8folder")
BAGI = Path("gambar/manifest/pembagian_8_folder.csv")
OUT = Path("gold/bagian_foto_commons")
BAGIAN = ["BUAH", "DAUN", "BUNGA", "BATANG", "TANAMAN_UTUH", "LAIN"]
KUNING = PatternFill("solid", fgColor="FFF2CC")
PX = 260
SEED = 20261104

PETUNJUK = [
    "PETUNJUK ANOTASI BAGIAN TANAMAN - 160 FOTO COMMONS CABAI-KMS",
    "",
    "Tujuan: menentukan bagian tanaman yang menjadi objek utama setiap foto. Ini menjadi gold bagian tanaman,",
    "dipakai untuk menilai apakah link foto ditulis di baris Gambar yang benar (Gambar Daun / Batang / Buah / Bunga).",
    "Varietas TIDAK perlu diisi (gold varietas tetap dari kategori Wikimedia Commons).",
    "",
    "Isi hanya kolom berwarna kuning di sheet 'Anotasi'. Jangan membuka hasil sistem atau manifest gold sebelum selesai.",
    "",
    "Kolom:",
    "  bagian_utama   WAJIB. Bagian tanaman yang paling menonjol / menjadi tujuan foto:",
    "                 BUAH   (buah utuh, irisan, buah muda/masak, buah kering, tumpukan buah di pasar)",
    "                 DAUN   (daun menjadi objek utama)",
    "                 BUNGA  (bunga menjadi objek utama, walau ada daun di sekitarnya)",
    "                 BATANG (batang/cabang menjadi objek utama)",
    "                 TANAMAN_UTUH  hanya bila tidak ada satu bagian yang dominan (tanaman/tajuk/lahan)",
    "                 LAIN   bukan bagian tanaman cabai (mis. olahan, bubuk, biji saja, bukan cabai)",
    "  bagian_lain    bagian kedua yang juga jelas terlihat dan wajar dianggap benar (boleh kosong).",
    "                 Contoh: tanaman berbuah lebat dengan daun jelas -> utama BUAH, lain DAUN.",
    "  yakin          Ya atau Ragu.",
    "  catatan        bebas, mis. 'buah dan bunga sama dominan', 'foto buram'.",
    "",
    "Sistem hanya mengenal empat kelas (DAUN, BATANG, BUAH, BUNGA). TANAMAN_UTUH dan LAIN dicatat agar jelas",
    "foto mana yang memang tidak punya satu bagian yang benar.",
    "Perkiraan waktu: 25-40 menit. Simpan berkas (Ctrl+S) sesekali.",
]


def gambar(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((PX, PX), Image.Resampling.LANCZOS)
    kanvas = Image.new("RGB", (PX, PX), "white")
    kanvas.paste(im, ((PX - im.width) // 2, (PX - im.height) // 2))
    buf = io.BytesIO()
    kanvas.save(buf, format="JPEG", quality=82)
    buf.seek(0)
    xi = XLImage(buf)
    xi.width = xi.height = PX
    return xi


def main():
    rows = [(r["folder"], r["filename"]) for r in csv.DictReader(open(BAGI, encoding="utf-8-sig"))]
    assert len(rows) == 160, len(rows)
    random.Random(SEED).shuffle(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "kunci_nomor.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["no", "folder", "filename"])
        for i, (fo, fn) in enumerate(rows, 1):
            w.writerow([i, fo, fn])

    wb = Workbook()
    p = wb.active
    p.title = "Petunjuk"
    for i, t in enumerate(PETUNJUK, 1):
        p.cell(i, 1, t)
    p["A1"].font = Font(bold=True)
    p.column_dimensions["A"].width = 120

    ws = wb.create_sheet("Anotasi")
    ws.append(["no", "foto", "bagian_utama", "bagian_lain", "yakin", "catatan"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, wd in zip("ABCDEF", (6, 38, 16, 16, 9, 40)):
        ws.column_dimensions[col].width = wd
    for n, (fo, fn) in enumerate(rows, 2):
        ws.cell(n, 1, n - 1).alignment = Alignment(vertical="center")
        ws.add_image(gambar(FOTO / fo / fn), f"B{n}")
        ws.row_dimensions[n].height = PX * 0.75 + 4
        for col in range(3, 7):
            c = ws.cell(n, col)
            c.fill = KUNING
            c.alignment = Alignment(vertical="center", wrap_text=True)
    last = len(rows) + 1
    for rng, opts in ((f"C2:D{last}", BAGIAN), (f"E2:E{last}", ["Ya", "Ragu"])):
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(rng)
    ws.freeze_panes = "C2"
    wb.active = 1
    out = OUT / "lembar_bagian_160.xlsx"
    wb.save(out)
    print("ditulis:", out, len(rows), "foto")


if __name__ == "__main__":
    main()
