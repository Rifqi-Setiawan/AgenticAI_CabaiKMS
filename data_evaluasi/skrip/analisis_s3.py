"""Baseline S3 (aproksimasi: penilai melihat seluruh 60 baris, tanpa retrieval) dibanding S4 (sistem penuh).

Dijalankan dari data_evaluasi/: python -I skrip/analisis_s3.py --out hasil_eksperimen/analisis_s3.md
S4 = harness 2026-10-31 rep1 (sama seperti analisis_lanjut.py). S3 = tiap pengulangan 2026-11-02_S3. Dataset: R01, R02, N07, N08 (berkas varian), N09
(kombinasi S01 sampai S03 tidak dijalankan untuk S3). Gold: sama dengan analisis_lanjut.py.
"""
import argparse
import glob
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analisis_lanjut as al  # noqa: E402
import hitung_metrik as hm  # noqa: E402

DATASETS = {"R01", "R02", "N07", "N08", "N09"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base = Path("hasil_eksperimen/hasil_harness")
    s4_a = str(base / "2026-10-31" / "rep1")
    s4_n08 = str(base / "2026-10-31" / "rep1" / "atribut_n08var")
    root_b = str(base / "2026-11-01_bc3c21b" / "rep1")
    gold = al.read("gold/gold_semua_dataset.csv")
    ref = [i for i in al.load_attr(s4_a, root_b, s4_n08, gold) if i["dataset"] in DATASETS]
    out = ["# Baseline S3 (aproksimasi) dibanding S4\n",
           "S3: pipeline yang sama, tetapi penilai LLM menerima seluruh 60 baris kanonik dalam urutan template (tanpa peringkat retrieval). "
           "Tahap pencocokan nama persis tetap berjalan. Bukan 'LLM murni': ini mengisolasi kontribusi penyempitan kandidat oleh retrieval.\n",
           f"Dataset: {', '.join(sorted(DATASETS))}; n butir = {len(ref)}. S4 dari harness rep1 (2026-10-31); S3 dari tiga pengulangan.\n",
           "| Himpunan | Varian | n target / tanpa target | Precision | Recall | F1 (CI 95%) | Recall atribut baru |", "|---|---|---|---|---|---|---|"]
    held = {"R02", "N07", "N08", "N09"}
    s3_reps = []
    for rep in (1, 2, 3):
        r = base / "2026-11-02_S3" / f"rep{rep}"
        its = [i for i in al.load_attr(str(r), root_b, str(r / "atribut_n08var"), gold) if i["dataset"] in DATASETS]
        s3_reps.append(its)
    # pasangkan per butir: urutan sama karena sumber dan gold sama; verifikasi
    by_id = [{i["id"]: i for i in its} for its in s3_reps]
    merged = []
    for base_item in ref:
        row = dict(base_item)
        for n, d in enumerate(by_id, 1):
            row[f"S3_{n}"] = d[base_item["id"]]["S4"]
        merged.append(row)
    for label, sub in (("Held-out", [i for i in merged if i["dataset"] in held]), ("Dev (R01)", [i for i in merged if i["dataset"] not in held]), ("Semua", merged)):
        for v in ("S4", "S3_1", "S3_2", "S3_3"):
            out.append(al.line(label, sub, v).replace(f"| {v} |", f"| {v.replace('_', ' rep')} |"))
    out.append("")
    out += ["## Uji berpasangan S4 vs S3 (S3 = tiap pengulangan; bootstrap berpasangan 10.000, Holm per himpunan)\n",
            "| Himpunan | Perbandingan | Selisih F1 | CI 95% | p mentah | p Holm |", "|---|---|---|---|---|---|"]
    for label, sub in (("Held-out", [i for i in merged if i["dataset"] in held]), ("Semua", merged)):
        res = [al.paired(sub, al.attr_f1("S4"), al.attr_f1(f"S3_{n}")) for n in (1, 2, 3)]
        adj = al.holm([r[3] for r in res])
        for n, r, p in zip((1, 2, 3), res, adj):
            out.append(f"| {label} | S4 vs S3 rep{n} | {r[0]:+.3f} | {r[1]:+.3f} sampai {r[2]:+.3f} | {r[3]:.4f} | {p:.4f} |")
    out.append("")
    changed = sum(1 for i in merged if len({i["S4"], i["S3_1"], i["S3_2"], i["S3_3"]}) > 1)
    out.append(f"Butir dengan prediksi berbeda antara S4 dan S3 pada minimal satu pengulangan: {changed} dari {len(merged)}.")
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
