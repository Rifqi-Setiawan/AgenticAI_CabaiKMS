"""Skor 160 foto Commons dengan spreadsheet pasangan data asli GRIN (4 Nov 2026).

Run (VPS, commit dicatat di commit.txt, tanpa tulis KMS):
  grin8  : varietas run dari workbook kanonik G01 (8 varietas terdaftar, sama dengan paper; OTHER 45 foto tetap OTHER).
  grin11 : varietas run dari G02 (8 + Scotch Bonnet, Banana Pepper, Poblano; 13 foto eks-OTHER menjadi KNOWN).
Pembanding: run UI 1 Nov 2026 (spreadsheet sintetis berisi 8 nama saja), dataset_eksperimen/4_hasil_sistem/C_foto_commons.
Gold: gambar/manifest/gold_gambar_manifest.csv (label sumber Commons, sama dengan paper).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\skor_foto_grin.py
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

D = Path("hasil_eksperimen/foto_grin")
GOLD = "gambar/manifest/gold_gambar_manifest.csv"
UI = "hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar/F*/vision.csv"  # D18: 19 baris mock diganti hasil model (koreksi_foto_mock.py)
TAMBAHAN_11 = {"Scotch Bonnet", "Banana Pepper", "Poblano"}
KOND = ("INFORMATIF", "NETRAL", "MENYESATKAN", "SEMUA")
N_BOOT, SEED = 10000, 20261104


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def items(pred, gold, terdaftar_tambahan=frozenset()):
    out = []
    for g in gold:
        p = pred.get(g["filename"])
        if p is None:
            continue
        kind = "KNOWN" if g["label_kind"] == "OTHER" and g["true_variety"] in terdaftar_tambahan else g["label_kind"]
        aksi = p.get("fusion_action") or ""
        status = (p.get("status") or "").upper()
        if not aksi and "write_applied" in p:  # run UI lama: tindakan fusi diturunkan seperti konversi_ui.py
            if status.startswith("CANDIDATE") or status == "FAILED_CANDIDATE_RECORD":
                aksi = "CANDIDATE"
            elif str(p.get("write_applied")).lower() == "true" or "AUTO_LINK" in (p.get("write_reason") or ""):
                aksi = "AUTO_LINK"
            else:
                aksi = "REVIEW"
        if status in ("CANDIDATE", "FAILED_CANDIDATE_RECORD"):
            status = "OTHER"  # vision_hook melaporkan antrean kandidat sebagai status CANDIDATE; status visualnya OTHER
        out.append({"fn": g["filename"], "cond": g["filename_condition"], "orig": g["label_kind"], "var": g["true_variety"],
                    "gold": kind, "gold_var": g["true_variety"] if kind == "KNOWN" else "",
                    "pred": status, "pred_var": p.get("matched_variety") or "", "aksi": aksi})
    return out


def benar(i):
    return i["pred"] == i["gold"] and (i["gold"] != "KNOWN" or norm(i["pred_var"]) == norm(i["gold_var"]))


def metr(xs):
    return hm.img_metrics([{"gold": i["gold"], "gold_var": norm(i["gold_var"]), "pred": i["pred"], "pred_var": norm(i["pred_var"])} for i in xs])


def ci(xs, key):
    rng = random.Random(SEED)
    v = sorted((metr([xs[rng.randrange(len(xs))] for _ in xs])[key] or 0.0) for _ in range(N_BOOT))
    return v[int(0.025 * (N_BOOT - 1))], v[int(0.975 * (N_BOOT - 1))]


def paired(a, b, fn):
    rng = random.Random(SEED)
    n = len(a)
    d = []
    for _ in range(N_BOOT):
        s = [rng.randrange(n) for _ in range(n)]
        d.append(fn([a[i] for i in s]) - fn([b[i] for i in s]))
    d.sort()
    p = min(1.0, 2 * min(sum(x <= 0 for x in d), sum(x >= 0 for x in d)) / N_BOOT)
    return fn(a) - fn(b), d[int(0.025 * (N_BOOT - 1))], d[int(0.975 * (N_BOOT - 1))], p


def ringkas(xs):
    m = metr(xs)
    nonk = [i for i in xs if i["gold"] != "KNOWN"]
    r = {"macro_f1": m["macro_f1"], "mf1_ci": ci(xs, "macro_f1"), "top1": m["top1_known"], "top1_ci": ci(xs, "top1_known"),
         "n_known": sum(i["gold"] == "KNOWN" for i in xs), "other_recall": None,
         "dipaksa": f"{sum(i['pred'] == 'KNOWN' for i in nonk)}/{len(nonk)}", "auto": {}}
    oth = [i for i in xs if i["gold"] == "OTHER"]
    r["other_recall"] = f"{sum(i['pred'] == 'OTHER' for i in oth)}/{len(oth)}" if oth else "-"
    for c in KOND:
        s = [i for i in xs if i["aksi"] == "AUTO_LINK" and (c == "SEMUA" or i["cond"] == c)]
        r["auto"][c] = (sum(1 for i in s if i["gold"] == "KNOWN" and benar(i)), len(s))
    return r


def main():
    gold = read(GOLD)
    runs = {k: {r["filename"]: r for r in read(D / f"hasil_{k}.csv")} for k in ("grin8", "grin11")}
    ui = {}
    for f in glob.glob(UI):
        for r in read(f):
            ui[r["filename"]] = r
    X = {"ui_8_nama": items(ui, gold), "grin8": items(runs["grin8"], gold), "grin11": items(runs["grin11"], gold, frozenset(TAMBAHAN_11))}
    R = {k: ringkas(v) for k, v in X.items()}
    meta = {k: json.load(open(D / f"meta_{k}.json", encoding="utf-8")) for k in runs}
    f3 = lambda v: f"{v:.3f}"
    al = lambda r, c: f"{r['auto'][c][0]}/{r['auto'][c][1]}" + (f" = {r['auto'][c][0] / r['auto'][c][1]:.3f}" if r["auto"][c][1] else "")
    out = ["# 160 foto Commons dengan spreadsheet pasangan data asli GRIN", "",
           f"Commit {(D / 'commit.txt').read_text().strip()}. Varietas run grin8: {meta['grin8']['run_scope']}. "
           f"grin11: {meta['grin11']['run_scope']}. Varietas DB KMS: {meta['grin8']['db_varieties'] or 'kosong'}. Bootstrap {N_BOOT}, seed {SEED}.", "",
           "| Metrik | UI lama (8 nama sintetis) | grin8 (8 varietas GRIN) | grin11 (11 varietas GRIN) |", "|---|---|---|---|",
           "| Foto KNOWN di gold | " + " | ".join(str(R[k]["n_known"]) for k in X) + " |",
           "| Macro-F1 status [CI] | " + " | ".join(f"{f3(R[k]['macro_f1'])} [{f3(R[k]['mf1_ci'][0])}, {f3(R[k]['mf1_ci'][1])}]" for k in X) + " |",
           "| Top-1 pada foto KNOWN [CI] | " + " | ".join(f"{f3(R[k]['top1'])} [{f3(R[k]['top1_ci'][0])}, {f3(R[k]['top1_ci'][1])}]" for k in X) + " |",
           "| Recall OTHER | " + " | ".join(R[k]["other_recall"] for k in X) + " |",
           "| Non-KNOWN diprediksi KNOWN | " + " | ".join(R[k]["dipaksa"] for k in X) + " |"]
    for c in KOND:
        out.append(f"| AUTO_LINK benar, nama {c.lower()} | " + " | ".join(al(R[k], c) for k in X) + " |")
    by = {k: {i["fn"]: i for i in v} for k, v in X.items()}
    fn99 = [i["fn"] for i in X["grin8"] if i["orig"] == "KNOWN"]
    acc = lambda xs: sum(benar(i) for i in xs) / len(xs)
    x = paired([by["grin8"][f] for f in fn99], [by["ui_8_nama"][f] for f in fn99], acc)
    f13 = [i["fn"] for i in X["grin11"] if i["orig"] == "OTHER" and i["var"] in TAMBAHAN_11]
    out += ["", "## Perbandingan", "",
            f"- 99 foto KNOWN, grin8 vs UI lama (pengaruh spreadsheet asli vs daftar nama): Top-1 {acc([by['grin8'][f] for f in fn99]):.3f} vs "
            f"{acc([by['ui_8_nama'][f] for f in fn99]):.3f}; selisih {x[0]:+.3f} [{x[1]:+.3f}, {x[2]:+.3f}], p {x[3]:.4f}. "
            "Model visi hanya menerima nama varietas (deskripsi hanya dari varietas referensi template), jadi beda di sini terutama "
            "mencerminkan keacakan model dan jalur run, bukan isi spreadsheet.",
            f"- 13 foto Scotch Bonnet/Banana Pepper/Poblano: grin11 benar {sum(benar(by['grin11'][f]) for f in f13)}/13; "
            f"pada grin8 (masih OTHER) dikenali OTHER {sum(by['grin8'][f]['pred'] == 'OTHER' for f in f13)}/13."]
    (D / "hasil_skor.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (D / "hasil_skor.json").write_text(json.dumps(R, indent=2, default=list), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
