"""Analisis lanjut: paired bootstrap + Holm, dev vs held-out, stratum lookup vs semantik, dan perbandingan foto.

Pemakaian (dari folder data_evaluasi, setelah arsipkan_hasil.sh):
  python skrip/analisis_lanjut.py --out hasil_eksperimen/analisis_lanjut.md

Sumber atribut : harness (kolom S4 = proposed key, S1 = exact_name saja, S2 = retrieval_s2_key)
Sumber foto    : hasil UI Bagian C (160 foto), dikonversi dengan konversi_ui.py
"""
import argparse
import csv
import glob
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hitung_metrik as hm  # noqa: E402
import konversi_ui as ku  # noqa: E402

N_PAIRED = 10000
SEED = 20261101
DEV = {"R01", "S01", "S02", "S03", "S04"}
HELDOUT = {"R02", "N07", "N08", "N09"}


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def holm(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    adj, running = [None] * len(pvals), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvals) - rank) * pvals[i]))
        adj[i] = running
    return adj


def paired(items, fa, fb, n=N_PAIRED, seed=SEED):
    """items: daftar butir; fa/fb: fungsi daftar -> skor. Mengembalikan selisih, CI 95%, p dua sisi."""
    rng = random.Random(seed)
    diffs = []
    m = len(items)
    for _ in range(n):
        s = [items[rng.randrange(m)] for _ in range(m)]
        diffs.append(fa(s) - fb(s))
    diffs.sort()
    obs = fa(items) - fb(items)
    lo, hi = diffs[int(0.025 * (n - 1))], diffs[int(0.975 * (n - 1))]
    p_le = sum(1 for d in diffs if d <= 0) / n
    p_ge = sum(1 for d in diffs if d >= 0) / n
    return obs, lo, hi, min(1.0, 2 * min(p_le, p_ge))


def load_attr(root_a, root_b, root_n08, gold):
    """Gabung keluaran harness rep1 menjadi butir per atribut dengan prediksi S4, S1, S2 dan metode."""
    exact = {(g["dataset_id"], g["source_attribute_display"].strip()): g for g in gold}
    fuzzy = {}
    for g in gold:
        fuzzy.setdefault((g["dataset_id"], ku.norm(g["source_attribute_display"])), []).append(g)
    sources = []
    for ds in ("R01", "R02", "N07", "N09"):
        sources.append((ds, Path(root_a) / "atribut" / ds / "mapping.csv"))
    sources.append(("N08", Path(root_n08) / "N08" / "mapping.csv"))
    for ds in ("S01", "S02", "S03"):
        sources.append((ds, Path(root_b) / "kombinasi" / ds / "mapping.csv"))
    rows = {}
    for ds, f in sources:
        for r in read(f):
            disp = r["source_attribute_display"].strip()
            g = exact.get((ds, disp))
            if g is None:
                c = fuzzy.get((ds, ku.norm(disp)), [])
                g = c[0] if len(c) == 1 else None
            if g is None:
                continue
            method = (r.get("mapping_method") or "").lower()
            prop = (r.get("proposed_target_canonical_key") or "").strip()
            rows[g["mapping_item_id"]] = {
                "id": g["mapping_item_id"], "dataset": ds, "gold_status": g["gold_status"], "gold_key": g["gold_canonical_keys"],
                "S4": prop, "S1": prop if method.startswith("exact") else "",
                "S2": (r.get("retrieval_s2_key") or "").strip(), "method": method,
            }
    for g in gold:  # butir yang tidak dihasilkan sistem pada dataset yang dijalankan = tanpa pemetaan
        ds = g["dataset_id"]
        if ds in {d for d, _ in sources} and g["mapping_item_id"] not in rows:
            rows[g["mapping_item_id"]] = {"id": g["mapping_item_id"], "dataset": ds, "gold_status": g["gold_status"], "gold_key": g["gold_canonical_keys"],
                                          "S4": "", "S1": "", "S2": "", "method": "tidak_dihasilkan"}
    return [v for v in rows.values() if v["gold_status"] in ("ONE_TO_ONE", "NO_MATCH")]


def attr_f1(variant):
    def fn(items):
        sel = [{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[variant]} for i in items]
        return hm.attr_metrics(sel)["f1"]
    return fn


def attr_new(variant):
    def fn(items):
        sel = [{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[variant]} for i in items]
        r = hm.attr_metrics(sel)["recall_atribut_baru"]
        return 0.0 if r is None else r
    return fn


def line(label, items, variant):
    sel = [{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[variant]} for i in items]
    m = hm.attr_metrics(sel)
    boots = hm.bootstrap(sel, hm.attr_metrics)
    lo, hi = hm.ci([b["f1"] for b in boots])
    return (f"| {label} | {variant} | {m['n_target']} / {m['n_tanpa_target']} | {m['precision']:.3f} | {m['recall']:.3f} | "
            f"{m['f1']:.3f} ({lo:.3f} sampai {hi:.3f}) | " + ("-" if m["recall_atribut_baru"] is None else f"{m['recall_atribut_baru']:.3f}") + " |")


def photo_items(ui_dir, gold_path):
    tmp = tempfile.mkdtemp()
    subprocess.run([sys.executable, "-I", str(HERE / "konversi_ui.py"), "gambar", "--gold", gold_path, "--dir", ui_dir,
                    "--out", str(Path(tmp) / "p")], check=True, capture_output=True)
    gold = {r["filename"]: r for r in read(gold_path)}
    pred = {v: {r["filename"]: r for r in read(Path(tmp) / f"p_{v}.csv")} for v in ("V3", "V1", "V2")}
    items = []
    for fn, g in gold.items():
        if fn not in pred["V3"]:
            continue
        items.append({"cond": g["filename_condition"], "split": g.get("split", ""),
                      "gold": g["label_kind"], "gold_var": g.get("true_variety", ""),
                      **{v: (pred[v][fn]["predicted_status"].upper(), pred[v][fn].get("predicted_variety", "")) for v in pred},
                      "action": pred["V3"][fn].get("fusion_action", "")})
    return items


def photo_fn(variant):
    def fn(items):
        sel = [{"gold": i["gold"], "gold_var": i["gold_var"], "pred": i[variant][0], "pred_var": i[variant][1]} for i in items]
        return hm.img_metrics(sel)["macro_f1"]
    return fn


def photo_top1(variant):
    def fn(items):
        sel = [{"gold": i["gold"], "gold_var": i["gold_var"], "pred": i[variant][0], "pred_var": i[variant][1]} for i in items]
        r = hm.img_metrics(sel)["top1_known"]
        return 0.0 if r is None else r
    return fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base = Path("hasil_eksperimen/hasil_harness")
    root_a = sorted(glob.glob(str(base / "2026-10-31" / "rep1")))[0]
    root_n08 = sorted(glob.glob(str(base / "2026-10-31" / "rep1" / "atribut_n08var")))[0]
    root_b = sorted(glob.glob(str(base / "2026-11-01_bc3c21b" / "rep1")))[0]
    gold = read("gold/gold_semua_dataset.csv")
    items = load_attr(root_a, root_b, root_n08, gold)
    out = []
    out.append("# Analisis lanjut (sementara; gold pra-anotasi AI)\n")
    out.append("Sumber atribut: harness rep1; N08 memakai berkas varian (D4); S04 ditolak sistem dan tidak masuk. "
               f"Paired bootstrap {N_PAIRED} ulangan, seed {SEED}; koreksi Holm pada perbandingan confirmatory.\n")

    # 1) dev vs held-out
    out.append("## 1. Mapping F1 per partisi dan varian\n")
    out.append("| Partisi | Varian | n target / tanpa target | Precision | Recall | F1 (CI 95%) | Recall atribut baru |")
    out.append("|---|---|---|---|---|---|---|")
    parts = [("Held-out (R02, N07, N08, N09)", [i for i in items if i["dataset"] in HELDOUT]),
             ("Dev (R01, S01, S02, S03)", [i for i in items if i["dataset"] in DEV]),
             ("Semua", items)]
    for label, sub in parts:
        for v in ("S4", "S1", "S2"):
            out.append(line(label, sub, v))
    out.append("")

    # 2) stratum
    out.append("## 2. Stratum kesulitan (lookup = dihasilkan exact_name pada S4; semantik = sisanya)\n")
    out.append("| Partisi | Stratum | Varian | n target / tanpa target | Precision | Recall | F1 (CI 95%) | Recall atribut baru |")
    out.append("|---|---|---|---|---|---|---|---|")
    for label, sub in parts[:2] + parts[2:]:
        lookup = [i for i in sub if i["method"].startswith("exact")]
        sem = [i for i in sub if not i["method"].startswith("exact")]
        for sname, ss in (("lookup", lookup), ("semantik", sem)):
            for v in ("S4", "S2"):
                if not ss:
                    continue
                row = line(label, ss, v).split("|")
                row.insert(2, f" {sname} ")
                out.append("|".join(row))
    out.append("")

    # 3) uji berpasangan atribut
    out.append("## 3. Uji berpasangan atribut (confirmatory; Holm)\n")
    out.append("| Himpunan | Perbandingan | Selisih F1 | CI 95% | p mentah | p Holm |")
    out.append("|---|---|---|---|---|---|")
    for label, sub in (parts[0], parts[2]):
        res, names = [], []
        for va, vb in (("S4", "S1"), ("S4", "S2")):
            res.append(paired(sub, attr_f1(va), attr_f1(vb))); names.append(f"{va} vs {vb} (Mapping F1)")
        res.append(paired(sub, attr_new("S4"), attr_new("S2"))); names.append("S4 vs S2 (recall atribut baru)")
        adj = holm([r[3] for r in res])
        for n, r, p in zip(names, res, adj):
            out.append(f"| {label} | {n} | {r[0]:+.3f} | {r[1]:+.3f} sampai {r[2]:+.3f} | {r[3]:.4f} | {p:.4f} |")
    out.append("")

    # 4) foto
    koreksi = Path("hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar")  # D18: 19 baris mock diganti
    ui_dir = str(koreksi) if koreksi.exists() else glob.glob("hasil_eksperimen/hasil_ui/2026-11-01/gambar")[0]
    ph = photo_items(ui_dir, "gambar/manifest/gold_gambar_manifest.csv")
    out.append("## 4. Foto (160 foto Commons, hasil UI)\n")
    out.append("| Himpunan | Perbandingan | Selisih macro-F1 | CI 95% | p mentah | p Holm |")
    out.append("|---|---|---|---|---|---|")
    mis = [p for p in ph if p["cond"] == "MENYESATKAN"]
    comps = [("Semua foto", ph, "V3", "V1"), ("Nama file MENYESATKAN", mis, "V3", "V2"), ("Semua foto", ph, "V3", "V2")]
    res = [paired(s, photo_fn(a1), photo_fn(b1)) for _, s, a1, b1 in comps]
    adj = holm([r[3] for r in res])
    for (lab, s, a1, b1), r, p in zip(comps, res, adj):
        out.append(f"| {lab} (n={len(s)}) | {a1} vs {b1} | {r[0]:+.3f} | {r[1]:+.3f} sampai {r[2]:+.3f} | {r[3]:.4f} | {p:.4f} |")
    out.append("")
    out.append("Catatan: V3 dan V1 identik pada pemetaan yang dipakai (tindakan review mempertahankan status visual); perbandingan V3 vs V1 selalu 0.\n")

    # 5) ketepatan AUTO_LINK
    out.append("## 5. Ketepatan tautan otomatis (eksploratori)\n")
    out.append("| Kondisi nama file | AUTO_LINK | benar | ketepatan | REVIEW (dialihkan) | di antaranya benar |")
    out.append("|---|---|---|---|---|---|")
    for cond in ("INFORMATIF", "NETRAL", "MENYESATKAN", None):
        sub = [p for p in ph if cond is None or p["cond"] == cond]
        al = [p for p in sub if p["action"] == "AUTO_LINK"]
        rv = [p for p in sub if p["action"].startswith("REVIEW")]
        ok = lambda p: p["V3"][0] == p["gold"] and (p["gold"] != "KNOWN" or ku.norm(p["V3"][1]) == ku.norm(p["gold_var"]))
        out.append(f"| {cond or 'Semua'} | {len(al)} | {sum(ok(p) for p in al)} | {sum(ok(p) for p in al) / len(al):.3f} | {len(rv)} | {sum(ok(p) for p in rv)} |"
                   if al else f"| {cond} | 0 | 0 | - | {len(rv)} | {sum(ok(p) for p in rv)} |")
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
