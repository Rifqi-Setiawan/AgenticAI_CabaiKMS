"""Buat lembar anotasi bagian tanaman untuk uji 40 foto PVT (pilot poin 8).

Anotasi buta: lembar hanya berisi foto dan kolom isian; tidak ada varietas, prediksi sistem, atau confidence.
Foto yang ditampilkan adalah versi kartu terlihat (bagian tanaman dan keberadaan kartu harus bisa dinilai).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\buat_lembar_bagian_pvt.py
Keluaran: pilot_foto_pvt/uji_visi_40/lembar_anotasi_bagian.xlsx
"""
import csv
import io
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image

D = Path("pilot_foto_pvt/uji_visi_40")
PV = Path("pilot_foto_pvt")
BAGIAN = ["DAUN", "BATANG", "BUAH", "BUNGA", "TANAMAN_UTUH", "BIJI", "LAIN"]
KUNING = PatternFill("solid", fgColor="FFF2CC")
PX = 240  # tinggi/lebar foto di lembar

PETUNJUK = [
    "PETUNJUK ANOTASI BAGIAN TANAMAN - UJI 40 FOTO PVT CABAI-KMS",
    "",
    "Tujuan: menentukan bagian tanaman yang menjadi objek utama setiap foto, untuk menilai prediksi bagian tanaman",
    "sistem (sistem hanya memakai empat kelas: DAUN, BATANG, BUAH, BUNGA).",
    "",
    "Kerjakan sendiri dan isi hanya kolom berwarna kuning di sheet 'Anotasi'. Jangan membuka hasil sistem",
    "(hasil.csv, hasil_skor.md) sebelum selesai.",
    "",
    "Kolom:",
    "  bagian_utama    bagian tanaman yang paling menonjol / menjadi tujuan foto (wajib, pilih dari daftar):",
    "                  DAUN, BATANG, BUAH (termasuk buah muda, masak, irisan), BUNGA,",
    "                  TANAMAN_UTUH (habitus/tajuk/tanaman di lahan, tidak ada satu bagian yang dominan),",
    "                  BIJI, LAIN (bukan bagian tanaman, mis. hanya bagan warna).",
    "  bagian_lain     bagian kedua yang juga jelas terlihat dan bisa dianggap benar (boleh kosong).",
    "  ada_kartu_nama  Ya bila foto memuat kartu/label/stiker bertuliskan nama varietas (terbaca atau tidak).",
    "  yakin           Ya atau Ragu.",
    "  catatan         bebas, mis. 'foto buram', 'dua bagian sama dominan'.",
    "  nama_anotator   isi nama Anda pada baris pertama saja.",
    "",
    "Foto ditampilkan diperbesar dari resolusi asli 125-164 px, jadi tampak buram; nilai sebisanya.",
    "Perkiraan waktu: 10-15 menit.",
]


def main():
    rows = list(csv.DictReader(open(D / "sampel.csv", encoding="utf-8")))
    wb = Workbook()
    p = wb.active
    p.title = "Petunjuk"
    for i, t in enumerate(PETUNJUK, 1):
        p.cell(i, 1, t)
    p["A1"].font = Font(bold=True)
    p.column_dimensions["A"].width = 130

    ws = wb.create_sheet("Anotasi")
    head = ["id_foto", "foto", "bagian_utama", "bagian_lain", "ada_kartu_nama", "yakin", "catatan", "nama_anotator"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDEFGH", (11, 36, 16, 16, 15, 9, 40, 18)):
        ws.column_dimensions[col].width = w
    for n, r in enumerate(rows, 2):
        ws.cell(n, 1, r["id"]).alignment = Alignment(vertical="center")
        im = Image.open(PV / r["berkas_sumber"]).convert("RGB").resize((PX, PX), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        xi = XLImage(buf)
        xi.width = xi.height = PX
        ws.add_image(xi, f"B{n}")
        ws.row_dimensions[n].height = PX * 0.75 + 4
        for col in range(3, 9):
            c = ws.cell(n, col)
            c.fill = KUNING
            c.alignment = Alignment(vertical="center", wrap_text=True)
    last = len(rows) + 1
    for rng, opts in ((f"C2:D{last}", BAGIAN), (f"E2:E{last}", ["Ya", "Tidak"]), (f"F2:F{last}", ["Ya", "Ragu"])):
        dv = DataValidation(type="list", formula1='"' + ",".join(opts) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(rng)
    ws.freeze_panes = "B2"
    out = D / "lembar_anotasi_bagian.xlsx"
    wb.save(out)
    print("ditulis:", out, len(rows), "foto")


if __name__ == "__main__":
    main()
