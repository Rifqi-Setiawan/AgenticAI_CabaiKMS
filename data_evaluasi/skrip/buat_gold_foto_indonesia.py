"""Gold foto Indonesia dari isian peneliti -> status per spreadsheet S01-S03 (4 Nov 2026).

Masukan : gambar_id/gold_peneliti/lembar_gold_foto_indonesia.xlsx (diisi peneliti)
Keluaran: gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv
          (kolom sama dengan gold_kombinasi_drive1.csv lama, ditambah bagian_lain, bagian_boleh, sumber_varietas)

Aturan status (disetujui peneliti 4 Nov 2026), per spreadsheet:
  varietas ada di daftar varietas spreadsheet, terlihat = Ya   -> KNOWN
  varietas ada di daftar, terlihat_dari_foto = Tidak           -> UNCERTAIN
  varietas diketahui tetapi tidak ada di daftar spreadsheet    -> OTHER
  varietas kosong                                              -> UNCERTAIN (tidak terjadi: lihat ISIAN_AI)
Daftar varietas = kolom varietas spreadsheet sumber (sama dengan header hasil_kanonik.xlsx run 31 Okt).
dinilai = Y bila layak_dipakai = Ya. bagian_boleh = {bagian_utama, bagian_lain} dalam empat kelas sistem.

ISIAN_AI: tiga foto yang varietasnya dikosongkan peneliti diisi dengan tebakan visual AI (Claude) atas permintaan
peneliti, tanpa melihat prediksi sistem; disetujui peneliti. Ditandai sumber_varietas = "tebakan AI".
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\buat_gold_foto_indonesia.py
"""
import csv
import re
from pathlib import Path

import openpyxl

LEMBAR = Path("gambar_id/gold_peneliti/lembar_gold_foto_indonesia.xlsx")
OUT = Path("gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv")
REGISTRY = {"S01": ["Gendot", "Kopay", "Katokkon", "Cabai tanjung"],
            "S02": ["Gendot", "Kopay", "Katokkon"],
            "S03": ["Katokkon", "Cabai tanjung", "Domba", "Cabai rawit NTB"]}
EMPAT = ("DAUN", "BATANG", "BUAH", "BUNGA")
ISIAN_AI = {
    "C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.jpg": "Cabai Besar",
    "p9vb80t0ldt5cms.webp": "Gendot",
    "warna tangkai daun C. chinense dan C. annuum permukaan bawah.jpg": "C. chinense + C. annuum",
}


def kunci(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def main():
    ws = openpyxl.load_workbook(LEMBAR, data_only=True)["Gold"]
    foto = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        no, _, fn, var, yakin, terlihat, utama, lain, layak, catatan = r[:10]
        assert utama, f"bagian_utama kosong pada foto {no}"
        var = (var or "").strip()
        sumber = "peneliti"
        if (not var or var.upper() == "TIDAK_DIKETAHUI") and fn in ISIAN_AI:
            var, sumber = ISIAN_AI[fn], "tebakan AI"
        lain = lain if lain and lain != utama else ""
        foto.append({"filename": fn, "varietas": var, "sumber": sumber, "yakin": yakin or "", "terlihat": terlihat or "",
                     "utama": utama, "lain": lain, "boleh": "|".join(sorted({b for b in (utama, lain) if b in EMPAT})),
                     "layak": layak or "", "catatan": catatan or ""})
    assert len(foto) == 12, len(foto)
    rows = []
    for s, reg in REGISTRY.items():
        regk = {kunci(v): v for v in reg}
        for f in foto:
            if not f["varietas"]:
                st, ev = "UNCERTAIN", ""
            elif kunci(f["varietas"]) in regk:
                st, ev = ("KNOWN", regk[kunci(f["varietas"])]) if f["terlihat"] == "Ya" else ("UNCERTAIN", "")
            else:
                st, ev = "OTHER", ""
            rows.append({"spreadsheet": s, "filename": f["filename"], "varietas_atau_jenis": f["varietas"],
                         "sumber_varietas": f["sumber"], "bagian": f["utama"], "bagian_lain": f["lain"],
                         "bagian_boleh": f["boleh"], "expected_status": st, "expected_variety": ev,
                         "dinilai": "Y" if f["layak"] == "Ya" else "N",
                         "dapat_dibedakan_dari_gambar": "Y" if f["terlihat"] == "Ya" else "N",
                         "yakin_varietas": f["yakin"], "catatan": f["catatan"],
                         "anotator": "peneliti (Rifqi)", "tanggal": "2026-11-04"})
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("ditulis:", OUT, len(rows), "baris")
    for r in rows:
        print(r["spreadsheet"], r["filename"][:40], r["varietas_atau_jenis"], r["expected_status"], r["bagian_boleh"], r["dinilai"])


if __name__ == "__main__":
    main()
