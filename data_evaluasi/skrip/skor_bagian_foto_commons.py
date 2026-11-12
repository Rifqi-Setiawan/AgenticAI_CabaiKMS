"""Gold bagian tanaman 160 foto Commons dari anotasi peneliti + akurasi bagian tanaman sistem (4 Nov 2026).

Masukan : gold/bagian_foto_commons/lembar_bagian_160.xlsx (diisi peneliti, buta: tanpa nama file/label lama/prediksi)
          gold/bagian_foto_commons/kunci_nomor.csv (nomor -> folder, nama file)
Keluaran: gold/bagian_foto_commons/gold_bagian_commons.csv  (gold bagian per foto; dipakai skor_workbook_gabungan.py)
          hasil_eksperimen/bagian_foto/hasil_skor.md, rincian_bagian.csv

Aturan:
- bagian_boleh = {bagian_utama, bagian_lain} yang termasuk empat kelas sistem (DAUN, BATANG, BUAH, BUNGA).
  bagian_lain yang sama dengan bagian_utama berarti tidak ada bagian kedua.
- Foto TANAMAN_UTUH tanpa bagian kedua (bagian_boleh kosong): tidak punya satu bagian yang benar; tidak dinilai untuk
  akurasi bagian dan link-nya tidak dihukum karena bagian.
- Foto LAIN: bukan bagian tanaman; tidak dinilai untuk akurasi bagian (link ke foto ini sudah salah karena statusnya).
- Prediksi bagian = identified_part di hasil terkoreksi D18 (hasil_ui/2026-11-04_koreksi_mock).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\skor_bagian_foto_commons.py
"""
import csv
from collections import Counter
from pathlib import Path

import openpyxl

G = Path("gold/bagian_foto_commons")
KOREKSI = Path("hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar")
MANIFEST = Path("gambar/manifest/gold_gambar_manifest.csv")
OUT = Path("hasil_eksperimen/bagian_foto")
EMPAT = ("DAUN", "BATANG", "BUAH", "BUNGA")


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def gold_bagian():
    kunci = {int(r["no"]): r for r in read(G / "kunci_nomor.csv")}
    ws = openpyxl.load_workbook(G / "lembar_bagian_160.xlsx", data_only=True)["Anotasi"]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        no, _, utama, lain, yakin, catatan = r[:6]
        if no is None:
            continue
        assert utama, f"bagian_utama kosong pada nomor {no}"
        lain = lain if lain and lain != utama else ""
        boleh = sorted({b for b in (utama, lain) if b in EMPAT})
        k = kunci[int(no)]
        out.append({"filename": k["filename"], "folder": k["folder"], "no_lembar": no, "bagian_utama": utama,
                    "bagian_lain": lain, "bagian_boleh": "|".join(boleh), "yakin": yakin or "", "catatan": catatan or "",
                    "anotator": "", "tanggal": "2026-11-04"})
    assert len(out) == 160, len(out)
    return sorted(out, key=lambda x: (x["folder"], x["filename"]))


def main():
    gold = gold_bagian()
    with open(G / "gold_bagian_commons.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(gold[0]))
        w.writeheader()
        w.writerows(gold)
    man = {r["filename"]: r for r in read(MANIFEST)}
    pred = {}
    for i in range(1, 9):
        for r in read(KOREKSI / f"F{i}" / "vision.csv"):
            pred[r["filename"]] = r

    rinci, out = [], []
    for g in gold:
        p, m = pred[g["filename"]], man[g["filename"]]
        boleh = set(filter(None, g["bagian_boleh"].split("|")))
        sp = (p.get("identified_part") or "").upper()
        dinilai = bool(boleh)
        link = str(p.get("write_applied")).lower() == "true" and p.get("status") == "KNOWN"
        rinci.append({**{k: g[k] for k in ("folder", "filename", "bagian_utama", "bagian_lain", "bagian_boleh")},
                      "bagian_lama": m["true_part"], "label_kind": m["label_kind"], "prediksi_bagian": sp,
                      "status_sistem": p.get("status", ""), "auto_link": link,
                      "dinilai": dinilai, "benar": (sp in boleh) if dinilai else ""})

    def akurasi(xs):
        n = [x for x in xs if x["dinilai"]]
        b = sum(1 for x in n if x["benar"])
        return f"{b}/{len(n)} = {b / len(n):.3f}" if n else "-"

    sepakat = sum(1 for x in rinci if x["bagian_utama"] == x["bagian_lama"])
    sepakat_boleh = sum(1 for x in rinci if x["bagian_lama"] in set(x["bagian_boleh"].split("|")))
    out += ["# Bagian tanaman 160 foto Commons: gold peneliti dan akurasi sistem", "",
            "Gold: anotasi buta peneliti (4 Nov 2026), `gold/bagian_foto_commons/gold_bagian_commons.csv`. Prediksi: "
            "`identified_part` hasil terkoreksi D18. Bagian dianggap benar bila sama dengan bagian_utama atau bagian_lain "
            "(hanya empat kelas sistem). Foto TANAMAN_UTUH tanpa bagian kedua dan foto LAIN tidak dinilai.", "",
            "## Gold peneliti", "",
            "bagian_utama: " + ", ".join(f"{k} {v}" for k, v in Counter(x["bagian_utama"] for x in rinci).most_common()),
            "",
            f"Tidak dinilai untuk bagian: {sum(1 for x in rinci if not x['dinilai'])} foto "
            f"(TANAMAN_UTUH tanpa bagian kedua {sum(1 for x in rinci if not x['dinilai'] and x['bagian_utama'] == 'TANAMAN_UTUH')}, "
            f"LAIN {sum(1 for x in rinci if x['bagian_utama'] == 'LAIN')}).", "",
            f"Kesesuaian dengan label bagian lama (dari judul foto): bagian_utama sama {sepakat}/160; label lama termasuk "
            f"bagian yang boleh {sepakat_boleh}/160.", "",
            "## Akurasi bagian tanaman sistem", "",
            "| Himpunan | Benar / dinilai |", "|---|---|",
            f"| Semua foto | {akurasi(rinci)} |",
            f"| Foto yang ditautkan otomatis (AUTO_LINK) | {akurasi([x for x in rinci if x['auto_link']])} |"]
    for b in EMPAT:
        out.append(f"| gold utama {b} | {akurasi([x for x in rinci if x['bagian_utama'] == b])} |")
    out += ["", "Matriks (baris = gold bagian_utama, kolom = prediksi sistem), semua 160 foto:", "",
            "| gold \\ sistem | " + " | ".join(EMPAT) + " |", "|---" * 5 + "|"]
    for b in ("BUAH", "DAUN", "BUNGA", "BATANG", "TANAMAN_UTUH", "LAIN"):
        c = Counter(x["prediksi_bagian"] for x in rinci if x["bagian_utama"] == b)
        if c:
            out.append(f"| {b} | " + " | ".join(str(c.get(s, 0)) for s in EMPAT) + " |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hasil_skor.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    with open(OUT / "rincian_bagian.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rinci[0]))
        w.writeheader()
        w.writerows(rinci)
    print("\n".join(out))


if __name__ == "__main__":
    main()
