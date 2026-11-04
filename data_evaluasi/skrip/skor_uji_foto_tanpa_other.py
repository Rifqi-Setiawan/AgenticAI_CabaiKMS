"""Skor run foto Commons pelengkap: tanpa OTHER (17 varietas terdaftar) vs dengan OTHER (8 varietas), skrip dan commit sama.

Gold: gambar/manifest/gold_gambar_manifest.csv (label sumber Commons, sama dengan paper).
  - dengan OTHER: label_kind apa adanya (KNOWN 99, OTHER 45, UNCERTAIN 16).
  - tanpa OTHER : 45 foto OTHER menjadi KNOWN dengan varietas aslinya (semua varietas ada di spreadsheet); UNCERTAIN tetap.
Prediksi: hasil_eksperimen/uji_foto_tanpa_other/hasil_{tanpa_other,dengan_other}.csv (uji_visi_commons_vps.py di VPS).
Pembanding reproduksi: run UI 1 Nov 2026 (dataset_eksperimen/4_hasil_sistem/C_foto_commons/F*/klasifikasi_foto.csv).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\skor_uji_foto_tanpa_other.py
"""
import csv
import glob
import json
import random
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hitung_metrik as hm  # noqa: E402

D = Path("hasil_eksperimen/uji_foto_tanpa_other")
GOLD = "gambar/manifest/gold_gambar_manifest.csv"
UI = "../dataset_eksperimen/4_hasil_sistem/C_foto_commons/F*/klasifikasi_foto.csv"
KOND = ("INFORMATIF", "NETRAL", "MENYESATKAN")
N_BOOT, SEED = 10000, 20261103


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def items(pred, gold, closed):
    out = []
    for g in gold:
        p = pred.get(g["filename"])
        if p is None:
            continue
        kind = "KNOWN" if closed and g["label_kind"] == "OTHER" else g["label_kind"]
        out.append({"fn": g["filename"], "cond": g["filename_condition"], "orig": g["label_kind"], "gold": kind,
                    "gold_var": g["true_variety"] if kind == "KNOWN" else "", "pred": (p.get("status") or "").upper(),
                    "pred_var": p.get("matched_variety") or "", "action": p.get("fusion_action", ""), "failed": p.get("status") == "FAILED"})
    return out


def benar(i):
    return i["pred"] == i["gold"] and (i["gold"] != "KNOWN" or norm(i["pred_var"]) == norm(i["gold_var"]))


def metr(xs):
    m = hm.img_metrics([{"gold": i["gold"], "gold_var": norm(i["gold_var"]), "pred": i["pred"], "pred_var": norm(i["pred_var"])} for i in xs])
    return m


def boot_ci(xs, key):
    rng = random.Random(SEED)
    vals = []
    for _ in range(N_BOOT):
        s = [xs[rng.randrange(len(xs))] for _ in xs]
        v = metr(s)[key]
        vals.append(0.0 if v is None else v)
    vals.sort()
    return vals[int(0.025 * (N_BOOT - 1))], vals[int(0.975 * (N_BOOT - 1))]


def paired(a, b, fn):
    """a, b: daftar butir sejajar (foto sama). Selisih fn(a)-fn(b), CI 95% dan p dua sisi (bootstrap berpasangan)."""
    rng = random.Random(SEED)
    idx = list(range(len(a)))
    diffs = []
    for _ in range(N_BOOT):
        s = [rng.choice(idx) for _ in idx]
        diffs.append(fn([a[i] for i in s]) - fn([b[i] for i in s]))
    diffs.sort()
    obs = fn(a) - fn(b)
    p = min(1.0, 2 * min(sum(d <= 0 for d in diffs), sum(d >= 0 for d in diffs)) / N_BOOT)
    return obs, diffs[int(0.025 * (N_BOOT - 1))], diffs[int(0.975 * (N_BOOT - 1))], p


def ringkas(xs):
    m = metr(xs)
    known = [i for i in xs if i["gold"] == "KNOWN"]
    nonk = [i for i in xs if i["gold"] != "KNOWN"]
    al = [i for i in xs if i["action"] == "AUTO_LINK"]
    r = {"n": len(xs), "gagal": sum(i["failed"] for i in xs), "macro_f1": m["macro_f1"], "mf1_ci": boot_ci(xs, "macro_f1"),
         "top1": m["top1_known"], "top1_ci": boot_ci(xs, "top1_known"), "n_known": len(known),
         "uncertain_pred": sum(i["pred"] == "UNCERTAIN" for i in xs),
         "nonknown_dipaksa": f"{sum(i['pred'] == 'KNOWN' for i in nonk)}/{len(nonk)}",
         "auto_link": {}}
    for c in KOND + ("SEMUA",):
        s = [i for i in al if c == "SEMUA" or i["cond"] == c]
        ok = sum(1 for i in s if i["gold"] == "KNOWN" and benar(i))
        r["auto_link"][c] = (ok, len(s))
    r["aksi"] = {a: sum(1 for i in xs if i["action"] == a) for a in sorted({i["action"] for i in xs})}
    return r


def main():
    gold = read(GOLD)
    runs = {k: {r["filename"]: r for r in read(D / f"hasil_{k}.csv")} for k in ("tanpa_other", "dengan_other")}
    T = items(runs["tanpa_other"], gold, closed=True)
    O = items(runs["dengan_other"], gold, closed=False)
    res = {"tanpa_other": ringkas(T), "dengan_other": ringkas(O)}
    meta = {k: json.load(open(D / f"meta_{k}.json", encoding="utf-8")) for k in runs}
    commit = (D / "commit.txt").read_text().strip() if (D / "commit.txt").exists() else "?"

    f2 = lambda v: f"{v:.3f}"
    al = lambda r, c: (f"{r['auto_link'][c][0]}/{r['auto_link'][c][1]} = {r['auto_link'][c][0] / r['auto_link'][c][1]:.3f}"
                       if r["auto_link"][c][1] else "0/0")
    a, b = res["tanpa_other"], res["dengan_other"]
    out = ["# Foto Commons: run pelengkap tanpa OTHER vs dengan OTHER", "",
           f"Skrip dan commit sama ({commit}); 160 foto, nama file asli. Varietas terdaftar: tanpa OTHER {len(meta['tanpa_other']['run_scope'])}, "
           f"dengan OTHER {len(meta['dengan_other']['run_scope'])}; varietas DB KMS: {meta['tanpa_other']['db_varieties'] or 'kosong'}. "
           f"Bootstrap {N_BOOT} ulangan, seed {SEED}.", "",
           "| Metrik | Tanpa OTHER (17 varietas) | Dengan OTHER (8 varietas) |", "|---|---|---|",
           f"| Gold | KNOWN {a['n_known']}, UNCERTAIN {a['n'] - a['n_known']} | KNOWN {b['n_known']}, OTHER 45, UNCERTAIN 16 |",
           f"| Gagal | {a['gagal']} | {b['gagal']} |",
           f"| Macro-F1 status [CI] | {f2(a['macro_f1'])} [{f2(a['mf1_ci'][0])}, {f2(a['mf1_ci'][1])}] | {f2(b['macro_f1'])} [{f2(b['mf1_ci'][0])}, {f2(b['mf1_ci'][1])}] |",
           f"| Top-1 pada foto KNOWN [CI] | {f2(a['top1'])} [{f2(a['top1_ci'][0])}, {f2(a['top1_ci'][1])}] | {f2(b['top1'])} [{f2(b['top1_ci'][0])}, {f2(b['top1_ci'][1])}] |",
           f"| Prediksi UNCERTAIN | {a['uncertain_pred']} | {b['uncertain_pred']} |",
           f"| Foto non-KNOWN diprediksi KNOWN | {a['nonknown_dipaksa']} | {b['nonknown_dipaksa']} |"]
    for c in KOND + ("SEMUA",):
        out.append(f"| AUTO_LINK benar, nama {c.lower()} | {al(a, c)} | {al(b, c)} |")
    out.append(f"| Tindakan fusi | {a['aksi']} | {b['aksi']} |")

    # pasangan: 99 foto KNOWN di kedua konfigurasi, dan 45 foto OTHER
    byT = {i["fn"]: i for i in T}
    byO = {i["fn"]: i for i in O}
    k99 = [fn for fn in byO if byO[fn]["orig"] == "KNOWN"]
    o45 = [fn for fn in byO if byO[fn]["orig"] == "OTHER"]
    acc = lambda xs: sum(benar(i) for i in xs) / len(xs)
    x = paired([byT[f] for f in k99], [byO[f] for f in k99], acc)
    out += ["", "## Perbandingan berpasangan", "",
            f"- 99 foto varietas yang terdaftar di kedua konfigurasi: Top-1 tanpa OTHER {acc([byT[f] for f in k99]):.3f}, "
            f"dengan OTHER {acc([byO[f] for f in k99]):.3f}; selisih {x[0]:+.3f} [{x[1]:+.3f}, {x[2]:+.3f}], p {x[3]:.4f}. "
            "Menunjukkan pengaruh daftar pilihan yang lebih panjang (17 vs 8) pada foto yang sama.",
            f"- 45 foto varietas yang hanya terdaftar di konfigurasi tanpa OTHER: varietas benar {sum(benar(byT[f]) for f in o45)}/45; "
            f"di konfigurasi dengan OTHER dikenali sebagai OTHER {sum(byO[f]['pred'] == 'OTHER' for f in o45)}/45, "
            f"dipaksa ke varietas terdaftar {sum(byO[f]['pred'] == 'KNOWN' for f in o45)}/45."]
    per = {}
    for f in o45:
        v = byT[f]["gold_var"]
        per.setdefault(v, [0, 0])
        per[v][0] += benar(byT[f])
        per[v][1] += 1
    out.append("- Varietas eks-OTHER, benar/jumlah (tanpa OTHER): " + "; ".join(f"{v} {a_}/{n}" for v, (a_, n) in sorted(per.items())))

    # reproduksi terhadap run UI lama (dengan OTHER, 8 varietas)
    ui = {}
    for f in glob.glob(UI):
        for r in read(f):
            ui[r["filename"]] = r
    same = [fn for fn in byO if fn in ui]
    agree = sum(byO[fn]["pred"] == (ui[fn]["status"] or "").upper() for fn in same)
    agree_v = sum(byO[fn]["pred"] == (ui[fn]["status"] or "").upper() and norm(byO[fn]["pred_var"]) == norm(ui[fn]["matched_variety"]) for fn in same)
    U = items(ui, gold, closed=False)
    mu = metr(U)
    out += ["", "## Reproduksi run UI 1 Nov 2026 (dengan OTHER)", "",
            f"Status sama pada {agree}/{len(same)} foto; status dan varietas sama pada {agree_v}/{len(same)}. "
            f"Run UI: macro-F1 {mu['macro_f1']:.3f}, Top-1 {mu['top1_known']:.3f}; run skrip: macro-F1 {b['macro_f1']:.3f}, Top-1 {b['top1']:.3f}.",
            "Perbedaan mencerminkan ketidakdeterministikan model dan jalur run (UI + Drive vs skrip), bukan perubahan kode vision "
            "(tidak ada perubahan pada modul vision antara bc3c21b dan ac4f2e4)."]
    (D / "hasil_skor.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (D / "hasil_skor.json").write_text(json.dumps(res, indent=2, default=list), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
