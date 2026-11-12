"""RQ4: recall kelas OTHER (varietas di luar daftar terdaftar) untuk V3, V1, V2 pada foto Commons.

Dijalankan dari data_evaluasi/: python -I skrip/analisis_rq4.py --out hasil_eksperimen/analisis_rq4.md
Memakai hasil UI yang sudah diarsipkan dan gold final (terverifikasi, lihat README_DATA_EVALUASI.md).
"""
import argparse
import glob
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analisis_lanjut as al  # noqa: E402

N = 10000


def recall_other(variant):
    def fn(items):
        pos = [i for i in items if i["gold"] == "OTHER"]
        return 0.0 if not pos else sum(i[variant][0] == "OTHER" for i in pos) / len(pos)
    return fn


def boot_ci(items, fn, seed=al.SEED):
    rng = random.Random(seed)
    vals = sorted(fn([items[rng.randrange(len(items))] for _ in range(len(items))]) for _ in range(N))
    return vals[int(0.025 * (N - 1))], vals[int(0.975 * (N - 1))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gold", default="gambar/manifest/gold_gambar_manifest_final.csv")
    a = ap.parse_args()
    ui_dir = glob.glob("hasil_eksperimen/hasil_ui/2026-11-01/gambar")[0]
    ph = al.photo_items(ui_dir, a.gold)
    n_other = sum(p["gold"] == "OTHER" for p in ph)
    out = ["# RQ4: recall kelas OTHER (foto Commons, hasil UI)\n",
           f"Foto dinilai: {len(ph)}; gold OTHER: {n_other}. Gold: `{a.gold}`.\n",
           "| Varian | Recall OTHER | CI 95% (bootstrap) |", "|---|---|---|"]
    for v in ("V3", "V1", "V2"):
        r = recall_other(v)(ph)
        lo, hi = boot_ci(ph, recall_other(v))
        out.append(f"| {v} | {r:.3f} | {lo:.3f} sampai {hi:.3f} |")
    out.append("")
    res = [al.paired(ph, recall_other("V3"), recall_other("V1")), al.paired(ph, recall_other("V3"), recall_other("V2"))]
    adj = al.holm([r[3] for r in res])
    out += ["| Perbandingan | Selisih | CI 95% | p mentah | p Holm |", "|---|---|---|---|---|"]
    for name, r, p in zip(("V3 vs V1 (H4)", "V3 vs V2 (eksploratori)"), res, adj):
        out.append(f"| {name} | {r[0]:+.3f} | {r[1]:+.3f} sampai {r[2]:+.3f} | {r[3]:.4f} | {p:.4f} |")
    out.append("\nCatatan: V3 dan V1 identik pada pemetaan yang dipakai, sehingga selisih V3 vs V1 nol menurut konstruksi; H4 tidak dapat didukung dengan data ini.\n")
    miss = [p for p in ph if p["gold"] == "OTHER" and p["V3"][0] != "OTHER"]
    out.append(f"OTHER yang tidak terdeteksi V3: {len(miss)} dari {n_other}; status prediksi: "
               + ", ".join(sorted({p['V3'][0] for p in miss})) + ".")
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
