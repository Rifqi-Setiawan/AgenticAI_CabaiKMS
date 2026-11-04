"""Lembar gold foto Indonesia (12 foto koleksi peneliti) yang diisi sendiri oleh peneliti (4 Nov 2026).

Peneliti mengisi per foto: varietas sebenarnya, apakah varietas itu bisa dikenali dari foto saja, bagian tanaman, dan
kelayakan foto. Status KNOWN/OTHER/UNCERTAIN per spreadsheet (S01-S03) TIDAK diisi peneliti: status itu diturunkan
otomatis dari varietas isian + daftar varietas tiap spreadsheet, supaya aturannya sama untuk semua foto.
Label lama (gold_kombinasi_drive1.csv, disusun dengan bantuan AI) dan prediksi sistem tidak ditampilkan.
Nama file ditampilkan karena berasal dari peneliti sendiri.
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\buat_lembar_gold_foto_indonesia.py
Keluaran: gambar_id/gold_peneliti/lembar_gold_foto_indonesia.xlsx
"""
import csv
import io
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image

FOTO = Path("gambar_id/foto_peneliti")
OUT = Path("gambar_id/gold_peneliti")
VARIETAS = ["Katokkon", "Kopay", "Gendot", "Domba", "Cabai Rawit", "Cabai Keriting", "Cabai Besar", "TIDAK_DIKETAHUI"]
BAGIAN = ["BUAH", "DAUN", "BUNGA", "BATANG", "TANAMAN_UTUH", "LAIN"]
KUNING = PatternFill("solid", fgColor="FFF2CC")
PX = 300

PETUNJUK = [
    "PETUNJUK GOLD FOTO CABAI INDONESIA (12 FOTO KOLEKSI PENELITI) - CABAI-KMS",
    "",
    "Tujuan: membuat kunci jawaban foto dari pengetahuan peneliti sendiri, menggantikan label lama yang disusun dengan",
    "bantuan AI dari nama berkas. Isi hanya kolom berwarna kuning di sheet 'Gold'.",
    "",
    "Kolom:",
    "  varietas            Varietas sebenarnya dari foto ini (yang Anda ketahui dari sumber/koleksi, bukan tebakan dari",
    "                      gambar). Pilih dari daftar ATAU ketik sendiri (mis. 'C. chinense'). Isi TIDAK_DIKETAHUI bila",
    "                      memang tidak tahu. Bila foto memuat dua varietas, tulis keduanya dan jelaskan di catatan.",
    "  yakin_varietas      Ya atau Ragu.",
    "  terlihat_dari_foto  Ya bila varietas itu WAJAR dikenali hanya dari foto ini (mis. bentuk buah khas Katokkon).",
    "                      Tidak bila dari foto saja tidak bisa dibedakan (mis. daun saja, bunga saja). Dipakai untuk",
    "                      menentukan apakah jawaban UNCERTAIN dari sistem dianggap wajar.",
    "  bagian_utama        BUAH / DAUN / BUNGA / BATANG / TANAMAN_UTUH (tidak ada yang dominan) / LAIN (bukan bagian",
    "                      tanaman). Tangkai daun -> DAUN, lalu tulis 'tangkai daun' di catatan.",
    "  bagian_lain         Bagian kedua yang juga jelas terlihat dan wajar dianggap benar (boleh kosong).",
    "  layak_dipakai       Ya / Tidak. Tidak bila bukan foto asli varietas itu (gambar stok, ilustrasi), hak ciptanya",
    "                      bermasalah, atau isinya tidak jelas.",
    "  catatan             bebas.",
    "",
    "Yang TIDAK perlu diisi: status KNOWN/OTHER/UNCERTAIN. Status itu dihitung otomatis per spreadsheet:",
    "  - varietas ada di daftar varietas spreadsheet itu dan terlihat_dari_foto = Ya  -> KNOWN",
    "  - varietas diketahui tetapi tidak ada di daftar spreadsheet itu                -> OTHER",
    "  - varietas TIDAK_DIKETAHUI, atau tidak bisa dikenali dari foto                 -> UNCERTAIN",
    "Aturan akhirnya akan dikonfirmasi dulu sebelum skor dihitung.",
]


def gambar(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((PX, PX), Image.Resampling.LANCZOS)
    kanvas = Image.new("RGB", (PX, PX), "white")
    kanvas.paste(im, ((PX - im.width) // 2, (PX - im.height) // 2))
    buf = io.BytesIO()
    kanvas.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    xi = XLImage(buf)
    xi.width = xi.height = PX
    return xi


def main():
    daftar = [r["filename"] for r in csv.DictReader(open(FOTO / "foto_peneliti.csv", encoding="utf-8-sig"))]
    assert len(daftar) == 12, len(daftar)
    OUT.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    p = wb.active
    p.title = "Petunjuk"
    for i, t in enumerate(PETUNJUK, 1):
        p.cell(i, 1, t)
    p["A1"].font = Font(bold=True)
    p.column_dimensions["A"].width = 120

    ws = wb.create_sheet("Gold")
    head = ["no", "foto", "nama_file", "varietas", "yakin_varietas", "terlihat_dari_foto", "bagian_utama", "bagian_lain",
            "layak_dipakai", "catatan"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, wd in zip("ABCDEFGHIJ", (5, 43, 30, 18, 10, 12, 15, 15, 10, 40)):
        ws.column_dimensions[col].width = wd
    for n, fn in enumerate(daftar, 2):
        ws.cell(n, 1, n - 1)
        ws.cell(n, 3, fn)
        ws.add_image(gambar(FOTO / fn), f"B{n}")
        ws.row_dimensions[n].height = PX * 0.75 + 4
        for col in range(1, 11):
            c = ws.cell(n, col)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            if col >= 4:
                c.fill = KUNING
    last = len(daftar) + 1
    for rng, opts, ketik in ((f"D2:D{last}", VARIETAS, True), (f"E2:E{last}", ["Ya", "Ragu"], False),
                             (f"F2:F{last}", ["Ya", "Tidak"], False), (f"G2:H{last}", BAGIAN, False),
                             (f"I2:I{last}", ["Ya", "Tidak"], False)):
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        if ketik:  # varietas boleh diketik bebas di luar daftar
            dv.showErrorMessage = False
        ws.add_data_validation(dv)
        dv.add(rng)
    ws.freeze_panes = "D2"
    wb.active = 1
    out = OUT / "lembar_gold_foto_indonesia.xlsx"
    wb.save(out)
    print("ditulis:", out, len(daftar), "foto")


if __name__ == "__main__":
    main()
