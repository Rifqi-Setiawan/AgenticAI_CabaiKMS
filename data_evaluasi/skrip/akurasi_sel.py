"""Akurasi isi spreadsheet keluaran per sel (masukan dosen poin 3). Definisi metrik disetujui peneliti 4 Nov 2026.

KUNCI JAWABAN (dibuat otomatis, dibaca langsung dari workbook sumber mentah dengan pembaca terpisah dari parser produksi):
  sel harapan (canonical_key, varietas) = gabungan nilai mentah semua atribut sumber yang gold-nya ONE_TO_ONE ke baris itu,
  untuk varietas tersebut (nilai unik, urutan sumber). Atribut NO_MATCH tidak menghasilkan sel. Atribut AMBIGUOUS/COMPOSITE
  dikecualikan: nilainya dibuang dari sel keluaran sebelum dinilai (sama dengan skor pemetaan yang mengeluarkan butir itu).
  Nama varietas harapan = nilai unik kolom varietas sumber (row-oriented) atau header kolom (transposed).

METRIK per workbook:
  1. Kolom varietas: kolom keluaran yang namanya sama dengan nama varietas sumber (tanpa beda huruf besar/kecil dan spasi).
  2. Akurasi sel: sel benar bila terisi, kolomnya varietas yang benar, dan himpunan nilainya setara dengan harapan setelah
     penyeragaman ringan (huruf kecil, koma desimal -> titik, tanda rentang -> "--", spasi; nilai dipisah ";").
       ketat : kolom dicocokkan lewat nama varietas di header keluaran.
       posisi: kolom ke-i keluaran dianggap varietas ke-i sumber (mengabaikan nama header; memperlihatkan dampak bug anchor).
     Precision = benar / sel keluaran terisi; Recall = benar / sel harapan; F1.
  3. Normalisasi: pada sel yang terisi di keluaran dan di kunci (kolom posisi), apakah teks keluaran identik dengan nilai
     sumber, berubah tetapi setara, atau berbeda. Semua sel yang tidak identik ditulis ke lembar cek manual.

Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\akurasi_sel.py
Keluaran: gold/kunci_sel/kunci_sel_semua.csv, hasil_eksperimen/akurasi_sel/{akurasi_sel.md, akurasi_sel.json, cek_normalisasi.xlsx}
"""
import csv
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

import openpyxl

EV = Path(".").resolve()
DS = EV.parent / "dataset_eksperimen"
SRC = DS / "1_input_spreadsheet"
GOLD = EV / "gold" / "final" / "gold_semua_dataset_final.csv"
ROW_KEYS = EV.parent / "src" / "schema" / "row_keys.yaml"  # identik dengan versi VPS (dicek 4 Nov 2026)
OUT = EV / "hasil_eksperimen" / "akurasi_sel"
KEY_OUT = EV / "gold" / "kunci_sel"
DEV = {"R01", "S01", "S02", "S03"}
# Baris tautan foto diisi klasifikasi foto, bukan pemetaan atribut; dinilai terpisah di analisis foto.
BARIS_GAMBAR = {"gambar_daun", "gambar_batang", "gambar_buah", "gambar_bunga"}
SEED, N_BOOT = 20261104, 10000

# id: (berkas, sheet, orientasi, baris header, kolom varietas (indeks 0) untuk row-oriented)
SUMBER = {
    "R01": ("data_input.xlsx", "Resume Data", "row", 2, 5),
    "R02": ("input_cabai_kms.xlsx", "Data Varietas", "row", 1, 0),
    "N07": ("E07_kementan_deskripsi_ext.xlsx", "Deskripsi Varietas", "row", 1, 0),
    "N08": ("E08_zenodo_capsicum_en_variety.xlsx", "Observed85_readable", "row", 1, 0),
    "N09": ("dataset_cabai_deskripsi_varietas.xlsx", "transposed", "trans", None, None),
    "S01": ("D01_transposed_indonesia_mixed.xlsx", "Data_Transposed", "trans", None, None),
    "S02": ("D02_row_flat_english_semantic.xlsx", "English_Flat_Data", "row", 1, 1),
    "S03": ("D03_row_multilevel_indonesia.xlsx", "Data_Bertingkat", "row", 2, 0),
}
A = DS / "4_hasil_sistem" / "A_atribut"
B = DS / "4_hasil_sistem" / "B_kombinasi_spreadsheet_foto"
KELUARAN_PAPER = {  # keluaran yang dipakai paper (UI, 31 Okt 2026)
    "R01": A / "R01_data_input", "R02": A / "R02_input_cabai_kms", "N07": A / "N07_kementan",
    "N08": A / "N08_zenodo_variety", "N09": A / "N09_deskripsi_varietas",
    "S01": B / "S01_D01_transposed", "S02": B / "S02_D02_english", "S03": B / "S03_D03_bertingkat",
}
RERUN = EV / "hasil_eksperimen" / "hasil_harness" / "2026-11-04_sel_ac4f2e4" / "rep1" / "atribut"


# ----------------------------------------------------------------------------------------------- utilitas
def teks(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def nama(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def seragam(seg):
    """Penyeragaman ringan untuk kesetaraan nilai (bukan normalisasi sistem)."""
    s = unicodedata.normalize("NFKC", seg).lower().strip()
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)
    s = re.sub(r"[‒–—−]", "-", s)
    s = re.sub(r"(?<=\d)\s*-{1,2}\s*(?=\d)", "--", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s


def himpunan(v):
    if not v:
        return frozenset()
    return frozenset(x for x in (seragam(p) for p in str(v).split(";")) if x)


def gabung(vals):
    seen = []
    for v in vals:
        if v is not None and v not in seen:
            seen.append(v)
    return "; ".join(seen) if seen else None


# -------------------------------------------------------------------------------------- baca sumber mentah
def baca_sumber(ds):
    """-> (urutan varietas, {(atribut, konteks): {varietas: [nilai mentah]}}, {judul_tampil: (atribut, konteks)})"""
    berkas, sheet, ori, hdr, vcol = SUMBER[ds]
    ws = openpyxl.load_workbook(SRC / berkas, data_only=True)[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    data, varietas = {}, []
    if ori == "trans":
        h = next(i for i, r in enumerate(rows) if teks(r[0]) == "Karakter")
        vnames = [teks(c) for c in rows[h][1:]]
        varietas = [v for v in vnames if v]
        for r in rows[h + 1:]:
            lab = teks(r[0])
            if not lab:
                continue
            per = data.setdefault((lab, ""), {})
            for v, val in zip(vnames, r[1:]):
                if v and teks(val) is not None:
                    per.setdefault(v, []).append(teks(val))
        return varietas, data
    # row-oriented: isi sel gabungan header agar induk berlaku ke semua kolom di bawahnya
    top = [teks(c) for c in rows[0]]
    for m in ws.merged_cells.ranges:
        if m.min_row == 1:
            for c in range(m.min_col, m.max_col + 1):
                top[c - 1] = teks(rows[0][m.min_col - 1])
    leaf = [teks(c) for c in rows[1]] if hdr == 2 else [None] * len(top)
    cols = []
    for i, t in enumerate(top):
        if hdr == 2 and leaf[i] and leaf[i] != t:
            cols.append((leaf[i], t or ""))
        else:
            cols.append((t, ""))
    for r in rows[hdr:]:
        v = teks(r[vcol]) if vcol < len(r) else None
        if not v:
            continue
        if v not in varietas:
            varietas.append(v)
        for i, (att, ctx) in enumerate(cols):
            if att is None or i == vcol or i >= len(r) or teks(r[i]) is None:
                continue
            data.setdefault((att, ctx), {}).setdefault(v, []).append(teks(r[i]))
    return varietas, data


def label_baris(s):
    """Label baris dicocokkan lewat teks (trim, kutip YAML dibuang, spasi ganda diseragamkan; mis. "warna buah  muda")."""
    return re.sub(r"\s+", " ", (s or "").strip().strip("'\"")).strip().lower()


def kunci_baris():
    lab = {}
    for line in ROW_KEYS.read_text(encoding="utf-8").splitlines():
        m = re.search(r"label:\s*(.+?),\s*canonical_key:\s*([a-z0-9_]+)", line)
        if m:
            lab[label_baris(m.group(1))] = m.group(2)
    return lab


def bangun_kunci(gold):
    """-> {ds: (varietas, {(key, var): nilai gabung}, {(key, var): set nilai dikecualikan}, [baris kunci])}"""
    out = {}
    for ds in SUMBER:
        varietas, data = baca_sumber(ds)
        exp, excl, rows = {}, {}, []
        items = [g for g in gold if g["dataset_id"] == ds]
        for g in items:
            att, ctx = g["source_attribute"].strip(), (g["source_context"] or "").strip()
            per = data.get((att, ctx))
            if per is None and ds == "N08" and att == "Genotype name":
                continue  # kolom varietas (A1 diganti "Variety" pada berkas varian)
            if per is None:
                per = next((p for (a_, c_), p in data.items() if nama(a_) == nama(att) and nama(c_) == nama(ctx)), None)
            if per is None:
                if g["gold_status"] == "ONE_TO_ONE":
                    raise SystemExit(f"{ds}: atribut gold tidak ditemukan di sumber: {att!r} / {ctx!r}")
                continue
            keys = [k for k in (g["gold_canonical_keys"] + "|" + g["ambiguous_candidate_canonical_keys"]).split("|") if k]
            if g["gold_status"] == "ONE_TO_ONE":
                k = g["gold_canonical_keys"]
                for v, vals in per.items():
                    exp.setdefault((k, v), []).extend(vals)
                    rows.append({"dataset": ds, "canonical_key": k, "varietas": v, "atribut_sumber": g["source_attribute_display"],
                                 "nilai_sumber": gabung(vals)})
            elif g["gold_status"] in ("AMBIGUOUS", "COMPOSITE"):
                for k in keys:
                    for v, vals in per.items():
                        excl.setdefault((k, v), set()).update(himpunan(gabung(vals)))
        out[ds] = (varietas, {kv: gabung(v) for kv, v in exp.items()}, excl, rows)
    return out


# ----------------------------------------------------------------------------------------------- baca keluaran
def baca_keluaran(path, lab2key):
    ws = openpyxl.load_workbook(path, data_only=True)["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    head = [teks(c) for c in rows[0][2:]]
    n = 0
    while n < len(head) and head[n]:
        n += 1
    head = head[:n]
    cells = {}
    for r in rows[1:]:
        k = lab2key.get(label_baris(teks(r[1]) or ""))
        if not k or k in BARIS_GAMBAR:
            continue
        for i in range(n):
            val = teks(r[2 + i])
            if val is not None:
                cells[(k, i)] = val
    return head, cells


# -------------------------------------------------------------------------------------------------- penilaian
def nilai(ds, kunci, keluaran):
    varietas, exp, excl, _ = kunci
    head, cells = keluaran
    vn = {nama(v): v for v in varietas}
    kolom_benar = sum(1 for h in head if nama(h) in vn)
    res = {"n_varietas": len(varietas), "n_kolom": len(head), "kolom_benar": kolom_benar}
    norm_rows = []
    for mode in ("ketat", "posisi"):
        got = {}
        for (k, i), val in cells.items():
            v = vn.get(nama(head[i])) if mode == "ketat" else (varietas[i] if i < len(varietas) else None)
            s = himpunan(val) - excl.get((k, v), set()) if v else himpunan(val)
            if s:
                got[(k, v if v else f"#kolom{i}")] = (s, val)
        tp = sum(1 for kv, (s, _) in got.items() if kv in exp and s == himpunan(exp[kv]))
        fp = len(got) - tp
        fn = sum(1 for kv in exp if not (kv in got and got[kv][0] == himpunan(exp[kv])))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        res[mode] = {"benar": tp, "salah_tulis": fp, "harapan": len(exp), "terlewat": fn, "precision": p, "recall": r,
                     "f1": 0.0 if p + r == 0 else 2 * p * r / (p + r)}
        if mode == "posisi":
            res["sel"] = {f"{k}|{v}": [sorted(s), sorted(himpunan(exp.get((k, v))))] for (k, v), (s, _) in got.items()}
            for (k, v), (s, raw_out) in got.items():
                if (k, v) not in exp:
                    continue
                raw_in = exp[(k, v)]
                if raw_out == raw_in:
                    jenis = "identik"
                elif s == himpunan(raw_in):
                    jenis = "berubah_setara"
                else:
                    jenis = "berbeda"
                norm_rows.append({"dataset": ds, "canonical_key": k, "varietas": v, "nilai_sumber": raw_in, "nilai_keluaran": raw_out,
                                  "jenis": jenis})
    res["normalisasi"] = {j: sum(1 for x in norm_rows if x["jenis"] == j) for j in ("identik", "berubah_setara", "berbeda")}
    return res, norm_rows


def jenis_perubahan(src, out):
    """Daftar perubahan teks yang terlihat dari nilai sumber ke keluaran (membantu cek manual, bukan penentu)."""
    j = []
    if re.search(r"\d,\d", src or "") and not re.search(r"\d,\d", out or ""):
        j.append("koma_desimal")
    if re.search(r"\d\s*[-–—]\s*\d", src or "") and "--" in (out or ""):
        j.append("tanda_rentang")
    if (src or "").lower() == (out or "").lower() and src != out:
        j.append("huruf_kosakata")
    if re.search(r"\d\.\d{3}(?!\d)", src or "") or re.search(r"\d,\d{3}(?!\d)", src or ""):
        j.append("RISIKO_ribuan")
    return ", ".join(j) or "lain"


def ci_cluster(per_ds, mode, key):
    """CI bootstrap per workbook untuk precision/recall/F1 gabungan (micro)."""
    ids = list(per_ds)
    rng = random.Random(SEED)
    vals = []
    for _ in range(N_BOOT):
        s = [ids[rng.randrange(len(ids))] for _ in ids]
        tp = sum(per_ds[i][mode]["benar"] for i in s)
        fp = sum(per_ds[i][mode]["salah_tulis"] for i in s)
        fn = sum(per_ds[i][mode]["terlewat"] for i in s)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        vals.append({"precision": p, "recall": r, "f1": 0.0 if p + r == 0 else 2 * p * r / (p + r)}[key])
    vals.sort()
    return vals[int(0.025 * (N_BOOT - 1))], vals[int(0.975 * (N_BOOT - 1))]


def gabungan(per_ds, mode):
    tp = sum(x[mode]["benar"] for x in per_ds.values())
    fp = sum(x[mode]["salah_tulis"] for x in per_ds.values())
    fn = sum(x[mode]["terlewat"] for x in per_ds.values())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"benar": tp, "salah_tulis": fp, "terlewat": fn, "precision": p, "recall": r, "f1": 0.0 if p + r == 0 else 2 * p * r / (p + r)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    gold = list(csv.DictReader(open(GOLD, encoding="utf-8-sig")))
    lab2key = kunci_baris()
    kunci = bangun_kunci(gold)
    KEY_OUT.mkdir(parents=True, exist_ok=True)
    with open(KEY_OUT / "kunci_sel_semua.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "canonical_key", "varietas", "atribut_sumber", "nilai_sumber"])
        w.writeheader()
        for ds in kunci:
            w.writerows(kunci[ds][3])

    hasil, cek = {"paper": {}, "rerun_ac4f2e4": {}}, []
    for ds, d in KELUARAN_PAPER.items():
        r, nr = nilai(ds, kunci[ds], baca_keluaran(d / "hasil_kanonik.xlsx", lab2key))
        hasil["paper"][ds] = r
        cek += [{**x, "keluaran": "paper"} for x in nr]
    for ds in ("N07", "R02"):
        p = RERUN / ds / "hasil_asli.xlsx"
        if p.exists():
            r, nr = nilai(ds, kunci[ds], baca_keluaran(p, lab2key))
            hasil["rerun_ac4f2e4"][ds] = r
            cek += [{**x, "keluaran": "rerun_ac4f2e4"} for x in nr]

    f3 = lambda v: f"{v:.3f}"
    out = ["# Akurasi isi spreadsheet per sel (masukan dosen poin 3)", "",
           "Kunci: gold pemetaan ONE_TO_ONE + nilai mentah sumber (pembaca terpisah dari parser produksi). Definisi metrik di docstring "
           "skrip/akurasi_sel.py. Keluaran paper = hasil UI 31 Okt 2026 (dataset_eksperimen/4_hasil_sistem).", "",
           "## Per workbook (keluaran paper)", "",
           "| Workbook | Split | Kolom varietas benar | Sel harapan | Ketat P / R / F1 | Posisi P / R / F1 | Normalisasi identik / berubah setara / berbeda |",
           "|---|---|---|---|---|---|---|"]
    for ds, r in hasil["paper"].items():
        k, p_ = r["ketat"], r["posisi"]
        n = r["normalisasi"]
        out.append(f"| {ds} | {'dev' if ds in DEV else 'held-out'} | {r['kolom_benar']}/{r['n_varietas']} (kolom {r['n_kolom']}) | {k['harapan']} | "
                   f"{f3(k['precision'])} / {f3(k['recall'])} / {f3(k['f1'])} | {f3(p_['precision'])} / {f3(p_['recall'])} / {f3(p_['f1'])} | "
                   f"{n['identik']} / {n['berubah_setara']} / {n['berbeda']} |")
    out += ["", "## Gabungan (micro), CI 95% bootstrap per workbook", "", "| Himpunan | Mode | Benar | Salah tulis | Terlewat | Precision [CI] | Recall [CI] | F1 [CI] |",
            "|---|---|---|---|---|---|---|---|"]
    ringkas = {}
    for lab, sel in (("held-out", lambda d: d not in DEV), ("semua", lambda d: True)):
        sub = {d: r for d, r in hasil["paper"].items() if sel(d)}
        for mode in ("ketat", "posisi"):
            g = gabungan(sub, mode)
            ci = {k: ci_cluster(sub, mode, k) for k in ("precision", "recall", "f1")}
            ringkas[f"{lab}_{mode}"] = {**g, "ci": ci}
            out.append(f"| {lab} | {mode} | {g['benar']} | {g['salah_tulis']} | {g['terlewat']} | {f3(g['precision'])} [{f3(ci['precision'][0])}, {f3(ci['precision'][1])}] | "
                       f"{f3(g['recall'])} [{f3(ci['recall'][0])}, {f3(ci['recall'][1])}] | {f3(g['f1'])} [{f3(ci['f1'][0])}, {f3(ci['f1'][1])}] |")
    if hasil["rerun_ac4f2e4"]:
        out += ["", "## Rerun N07 dan R02 pada commit ac4f2e4 (perbaikan deteksi kolom varietas)", "",
                "| Workbook | Kolom varietas benar | Ketat P / R / F1 | Posisi P / R / F1 |", "|---|---|---|---|"]
        for ds, r in hasil["rerun_ac4f2e4"].items():
            k, p_ = r["ketat"], r["posisi"]
            out.append(f"| {ds} | {r['kolom_benar']}/{r['n_varietas']} | {f3(k['precision'])} / {f3(k['recall'])} / {f3(k['f1'])} | "
                       f"{f3(p_['precision'])} / {f3(p_['recall'])} / {f3(p_['f1'])} |")
    else:
        out += ["", "Rerun N07/R02 (ac4f2e4) belum tersedia di " + str(RERUN)]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "akurasi_sel.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (OUT / "akurasi_sel.json").write_text(json.dumps({"hasil": hasil, "gabungan": ringkas}, indent=2, ensure_ascii=False, default=list), encoding="utf-8")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cek normalisasi"
    head = ["keluaran", "dataset", "canonical_key", "varietas", "nilai_sumber", "nilai_keluaran", "jenis", "perubahan_terlihat",
            "makna_tetap (Ya/Tidak)", "catatan"]
    ws.append(head)
    for x in cek:
        if x["jenis"] != "identik":
            ws.append([x["keluaran"], x["dataset"], x["canonical_key"], x["varietas"], x["nilai_sumber"], x["nilai_keluaran"], x["jenis"],
                       jenis_perubahan(x["nilai_sumber"], x["nilai_keluaran"]), "", ""])
    from openpyxl.styles import PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    for row in ws.iter_rows(min_row=2, min_col=9, max_col=10):
        for c in row:
            c.fill = PatternFill("solid", fgColor="FFF2CC")
    dv = DataValidation(type="list", formula1='"Ya,Tidak"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"I2:I{ws.max_row}")
    for col, w in zip("ABCDEFGHIJ", (14, 8, 24, 22, 40, 40, 15, 28, 12, 30)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    wb.save(OUT / "cek_normalisasi.xlsx")
    print("\n".join(out))
    print(f"\nkunci: {sum(len(k[1]) for k in kunci.values())} sel harapan; cek normalisasi: {sum(1 for x in cek if x['jenis'] != 'identik')} baris")


if __name__ == "__main__":
    main()
