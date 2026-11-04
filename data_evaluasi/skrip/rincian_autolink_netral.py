"""Lembar rincian 64 foto Commons bernama file NETRAL: gambar, gold, keputusan sistem (run UI 1 Nov 2026), benar/salah.

Menjelaskan angka presisi AUTO_LINK nama netral di paper (29/45 = 0,644, hasil terkoreksi D18).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\rincian_autolink_netral.py
Keluaran: hasil_eksperimen/rincian_autolink_netral.xlsx
"""
import glob
import io
import os
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skor_foto_grin as s  # noqa: E402

FOTO = Path("../dataset_eksperimen/2_input_foto/commons_8_folder")
PX = 150
MERAH, HIJAU, ABU = PatternFill("solid", fgColor="F8D7DA"), PatternFill("solid", fgColor="D4EDDA"), PatternFill("solid", fgColor="EEEEEE")


def main():
    gold = {g["filename"]: g for g in s.read(s.GOLD)}
    ui = {}
    for f in glob.glob(s.UI):
        for r in s.read(f):
            ui[r["filename"]] = {**r, "folder": os.path.basename(os.path.dirname(f))}
    X = [i for i in s.items(ui, list(gold.values())) if i["cond"] == "NETRAL"]

    def status_baris(i):
        if i["aksi"] != "AUTO_LINK":
            return 2, "tidak ditaut otomatis"
        if i["gold"] == "KNOWN" and s.benar(i):
            return 1, "BENAR"
        if i["orig"] == "KNOWN":
            return 0, "SALAH: varietas terdaftar keliru"
        if i["orig"] == "OTHER":
            return 0, "SALAH: varietas tidak terdaftar dipaksa ke kolom terdaftar"
        return 0, "SALAH: foto tak dapat ditentukan tetap ditautkan"
    X.sort(key=lambda i: (status_baris(i)[0], i["fn"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Foto nama netral"
    head = ["foto", "filename", "folder Drive", "gold: jenis", "gold: varietas", "gold: kategori Commons (asal label)",
            "sistem: status visual", "sistem: varietas", "sistem: confidence", "sistem: tindakan", "hasil", "bukti visual model"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for n, i in enumerate(X, 2):
        g, u = gold[i["fn"]], ui[i["fn"]]
        st = status_baris(i)
        ws.append(["", i["fn"], u["folder"], i["orig"], g["true_variety"] or "-", g["source_category"].replace("Category:", ""),
                   i["pred"], i["pred_var"] or "-", u.get("confidence", ""), i["aksi"], st[1], (u.get("visual_evidence") or "")[:300]])
        im = Image.open(FOTO / u["folder"] / i["fn"]).convert("RGB")
        im.thumbnail((PX, PX))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        ws.add_image(XLImage(buf), f"A{n}")
        ws.row_dimensions[n].height = PX * 0.75 + 6
        fill = {0: MERAH, 1: HIJAU, 2: ABU}[st[0]]
        for c in ws[n][1:]:
            c.fill = fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
    for col, w in zip("ABCDEFGHIJKL", (22, 14, 8, 11, 20, 26, 12, 15, 10, 14, 30, 60)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "B2"

    al = [i for i in X if i["aksi"] == "AUTO_LINK"]
    ok = sum(1 for i in al if i["gold"] == "KNOWN" and s.benar(i))
    r = wb.create_sheet("Perhitungan")
    for line in [
        ["Presisi AUTO_LINK pada foto bernama file netral (run UI 1 Nov 2026, gold = label sumber Commons)"],
        [],
        ["Foto bernama netral (IMG_xxxx.jpg)", len(X)],
        ["Ditautkan otomatis (AUTO_LINK)", len(al)],
        ["  di antaranya benar (gold KNOWN dan varietas sama)", ok],
        ["  di antaranya salah", len(al) - ok],
        ["Presisi = benar / ditautkan otomatis", f"{ok}/{len(al)} = {ok / len(al):.3f}"],
        ["Tidak ditautkan otomatis (CANDIDATE atau REVIEW)", len(X) - len(al)],
        [],
        ["Salah: gold OTHER (varietas tidak terdaftar dipaksa ke kolom terdaftar)", sum(1 for i in al if i["orig"] == "OTHER")],
        ["Salah: gold KNOWN tetapi varietas keliru", sum(1 for i in al if i["orig"] == "KNOWN" and not s.benar(i))],
        ["Salah: gold UNCERTAIN", sum(1 for i in al if i["orig"] == "UNCERTAIN")],
        [],
        ["Aturan AUTO_LINK: status visual KNOWN, confidence >= 0,85, varietas terdaftar, nama file tidak bertentangan."],
        ["Nama file netral tidak memberi petunjuk, jadi keputusan sepenuhnya dari visual model."],
        ["Gold = varietas menurut kategori Wikimedia Commons asal foto (kolom 'gold: kategori Commons'), bukan penilaian pakar."],
    ]:
        r.append(line)
    r.column_dimensions["A"].width = 95
    out = Path("hasil_eksperimen/rincian_autolink_netral.xlsx")
    wb.save(out)
    print(out, len(X), "foto;", f"AUTO_LINK benar {ok}/{len(al)}")


if __name__ == "__main__":
    main()
