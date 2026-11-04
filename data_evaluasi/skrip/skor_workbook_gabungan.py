"""Skor workbook akhir gabungan: isi sel atribut + link foto di baris Gambar, satu skor per run (4 Nov 2026).

Keluaran sistem adalah satu workbook: baris karakter diisi dari spreadsheet, baris Gambar Daun/Batang/Buah/Bunga diisi link
foto per varietas. Skor ini menilai keduanya sekaligus dengan satuan yang sama, yaitu UNIT TULISAN:
  - satu sel atribut  = satu unit (hasil akurasi_sel.py mode ketat: kolom dicocokkan lewat nama varietas)
  - satu link foto    = satu unit
Link foto BENAR bila foto itu menurut gold berstatus KNOWN pada run tersebut, ditulis di kolom varietas gold (nama header),
dan di baris Gambar sesuai bagian tanaman gold (gold Indonesia "TANGKAI DAUN" boleh di baris Daun atau Batang).
Link SALAH TULIS: foto OTHER/UNCERTAIN yang ditautkan, varietas salah, atau bagian tanaman salah.
Link TERLEWAT: foto gold KNOWN yang tidak tertulis di sel yang benar (mis. dikirim ke review).
Link dari foto tanpa label yang dapat dinilai (gold Indonesia dinilai = N) tidak dihitung.
Precision = benar / unit tertulis; Recall = benar / unit harapan; F1.

Run yang dinilai (keluaran sama dengan paper):
  Indonesia S01-S03 : spreadsheet sintetis beratribut + 12 foto Indonesia (UI 31 Okt 2026).
  Commons F1-F8     : spreadsheet 8 nama varietas + 20 foto per folder (UI 1 Nov 2026); tidak punya sel atribut.
Jalankan dari folder data_evaluasi (setelah akurasi_sel.py):  ..\\.venv\\Scripts\\python.exe -I skrip\\skor_workbook_gabungan.py
Keluaran: hasil_eksperimen/workbook_gabungan/{hasil_skor.md, hasil_skor.json, rincian_link_foto.csv}
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import openpyxl

DS = Path("../dataset_eksperimen/4_hasil_sistem")
OUT = Path("hasil_eksperimen/workbook_gabungan")
KOREKSI = Path("hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar")
BARIS = {"gambar daun": "DAUN", "gambar batang": "BATANG", "gambar buah": "BUAH", "gambar bunga": "BUNGA"}
BOLEH = {"TANGKAI DAUN": {"DAUN", "BATANG"}}
RUN_IND = {"S01": "S01_D01_transposed", "S02": "S02_D02_english", "S03": "S03_D03_bertingkat"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def link_di_workbook(path):
    """-> daftar (file_id, bagian_baris, nama_kolom_varietas) dari baris Gambar."""
    ws = openpyxl.load_workbook(path, data_only=True)["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    head = [str(c).strip() if c else "" for c in rows[0]]
    out = []
    for r in rows[1:]:
        lab = re.sub(r"\s+", " ", str(r[1] or "").strip().lower())
        if lab not in BARIS:
            continue
        for j in range(2, len(r)):
            if r[j] and head[j]:
                for fid in re.findall(r"/file/d/([^/;\s]+)", str(r[j])):
                    out.append((fid, BARIS[lab], head[j]))
    return out


def nilai_foto(links, fid2fn, gold_run):
    """gold_run: nama berkas (dinormalisasi) -> dict(status, varietas, bagian, dinilai)."""
    benar, salah, abaikan, rincian = 0, 0, 0, []
    tertulis_benar = set()
    for fid, bagian, kolom in links:
        fn = fid2fn.get(fid)
        g = gold_run.get(norm(fn)) if fn else None
        if g is None or not g["dinilai"]:
            abaikan += 1
            rincian.append((fn or fid, bagian, kolom, "tidak dinilai"))
            continue
        ok_bagian = bagian in BOLEH.get(g["bagian"], {g["bagian"]})
        ok = g["status"] == "KNOWN" and norm(kolom) == norm(g["varietas"]) and ok_bagian
        if ok:
            benar += 1
            tertulis_benar.add(norm(fn))
            hasil = "benar"
        else:
            salah += 1
            hasil = ("salah: foto " + g["status"]) if g["status"] != "KNOWN" else (
                "salah: varietas" if norm(kolom) != norm(g["varietas"]) else "salah: bagian tanaman")
        rincian.append((fn, bagian, kolom, hasil))
    harapan = [k for k, g in gold_run.items() if g["dinilai"] and g["status"] == "KNOWN"]
    terlewat = sum(1 for k in harapan if k not in tertulis_benar)
    return {"benar": benar, "salah_tulis": salah, "terlewat": terlewat, "harapan": len(harapan), "tidak_dinilai": abaikan}, rincian


def prf(b, s, t):
    p = b / (b + s) if b + s else 0.0
    r = b / (b + t) if b + t else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    sel = json.loads(Path("hasil_eksperimen/akurasi_sel/akurasi_sel.json").read_text(encoding="utf-8"))["hasil"]["paper"]
    runs = {}
    # Indonesia
    gi = read("gambar_id/gold_kombinasi_drive1.csv")
    for run, d in RUN_IND.items():
        kl = read(DS / "B_kombinasi_spreadsheet_foto" / d / "klasifikasi_foto.csv")
        fid2fn = {r["file_id"]: r["filename"] for r in kl}
        gold = {norm(g["filename"]): {"status": g["expected_status"], "varietas": g["expected_variety"], "bagian": g["bagian"],
                                      "dinilai": g["dinilai"] == "Y"} for g in gi if g["spreadsheet"] == run}
        foto, rin = nilai_foto(link_di_workbook(DS / "B_kombinasi_spreadsheet_foto" / d / "hasil_kanonik.xlsx"), fid2fn, gold)
        a = sel[run]["ketat"]
        runs[f"Indonesia {run}"] = {"atribut": {"benar": a["benar"], "salah_tulis": a["salah_tulis"], "terlewat": a["terlewat"],
                                                "harapan": a["harapan"]}, "foto": foto, "rincian": rin, "kelompok": "Indonesia"}
    # Commons
    gc = {r["filename"]: r for r in read("gambar/manifest/gold_gambar_manifest.csv")}
    folder = {r["filename"]: r["folder"] for r in read("gambar/manifest/pembagian_8_folder.csv")}
    for i in range(1, 9):
        f = f"F{i}"
        # D18: 19 baris run UI 1 Nov adalah jawaban mock; dipakai hasil terkoreksi (koreksi_foto_mock.py). Link foto dibentuk ulang
        # dari baris yang tertaut otomatis, persis seperti apply_vision_result_to_worksheet: baris Gambar <bagian>, kolom <varietas>.
        kl = read(KOREKSI / f / "vision.csv")
        fid2fn = {r["file_id"]: r["filename"] for r in kl}
        gold = {norm(fn): {"status": g["label_kind"], "varietas": g["true_variety"], "bagian": g["true_part"], "dinilai": True}
                for fn, g in gc.items() if folder.get(fn) == f}
        wb = DS / "C_foto_commons" / f / "hasil_kanonik.xlsx"
        links = [(r["file_id"], r["identified_part"], r["matched_variety"]) for r in kl
                 if str(r.get("write_applied")).lower() == "true" and r["status"] == "KNOWN" and r["matched_variety"]]
        foto, rin = nilai_foto(links, fid2fn, gold)
        # spreadsheet Commons hanya berisi nama varietas: tidak ada sel atribut yang diharapkan; sel atribut terisi = salah tulis
        ws = openpyxl.load_workbook(wb, data_only=True)["Sheet1"]
        terisi = sum(1 for r in list(ws.iter_rows(values_only=True))[1:]
                     if re.sub(r"\s+", " ", str(r[1] or "").strip().lower()) not in BARIS for v in r[2:] if v not in (None, ""))
        runs[f"Commons {f}"] = {"atribut": {"benar": 0, "salah_tulis": terisi, "terlewat": 0, "harapan": 0}, "foto": foto,
                                "rincian": rin, "kelompok": "Commons"}

    def baris(lab, rs):
        tot = {k: {m: sum(r[k][m] for r in rs) for m in ("benar", "salah_tulis", "terlewat", "harapan")} for k in ("atribut", "foto")}
        g = {m: tot["atribut"][m] + tot["foto"][m] for m in tot["atribut"]}
        cell = lambda d: "{}/{}/{} | {:.3f} / {:.3f} / {:.3f}".format(d["benar"], d["salah_tulis"], d["terlewat"], *prf(d["benar"], d["salah_tulis"], d["terlewat"]))
        return f"| {lab} | {cell(tot['atribut']) if tot['atribut']['harapan'] or tot['atribut']['salah_tulis'] else '- | -'} | {cell(tot['foto'])} | {cell(g)} |", tot, g

    out = ["# Skor workbook akhir gabungan (sel atribut + link foto)", "",
           "Satuan: unit tulisan (satu sel atribut atau satu link foto). Kolom: benar/salah tulis/terlewat | precision / recall / F1. "
           "Link foto benar = foto gold KNOWN di kolom varietas dan baris bagian tanaman yang benar. Definisi lengkap: docstring skrip.", "",
           "| Run | Atribut b/s/t | P / R / F1 | Foto b/s/t | P / R / F1 | Gabungan b/s/t | P / R / F1 |", "|---|---|---|---|---|---|---|"]
    ringkas = {}
    for lab, r in runs.items():
        line, tot, g = baris(lab, [r])
        out.append(line)
        ringkas[lab] = {"atribut": tot["atribut"], "foto": tot["foto"], "gabungan": g, "foto_tidak_dinilai": r["foto"]["tidak_dinilai"]}
    out.append("|  |  |  |  |  |  |  |")
    for lab, sel_ in (("Indonesia S01-S03", "Indonesia"), ("Commons F1-F8", "Commons"), ("SEMUA RUN", None)):
        line, tot, g = baris(f"**{lab}**", [r for r in runs.values() if sel_ is None or r["kelompok"] == sel_])
        out.append(line)
        ringkas[lab] = {"atribut": tot["atribut"], "foto": tot["foto"], "gabungan": g}
    # sebab salah tulis foto
    from collections import Counter
    sebab = Counter(x[3] for r in runs.values() for x in r["rincian"])
    out += ["", "Rincian link foto: " + ", ".join(f"{k} {v}" for k, v in sorted(sebab.items()))]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hasil_skor.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (OUT / "hasil_skor.json").write_text(json.dumps(ringkas, indent=2), encoding="utf-8")
    with open(OUT / "rincian_link_foto.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["run", "foto", "baris_gambar", "kolom_varietas", "hasil"])
        for lab, r in runs.items():
            for x in r["rincian"]:
                w.writerow([lab, *x])
    print("\n".join(out))


if __name__ == "__main__":
    main()
