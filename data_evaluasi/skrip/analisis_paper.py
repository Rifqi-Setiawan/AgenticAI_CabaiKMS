"""Analisis tambahan untuk paper IEEE (2 November 2026).

1. Baseline S2+tau: retrieval top-1 dengan ambang jarak; tau dituning di dev (maks. Mapping F1), dibekukan untuk held-out.
2. Hit@k retrieval pada butir semantik bertarget (kandidat yang benar-benar dilihat reranker).
3. Latency S4 vs S3 per dataset (detik per run dari meta.json harness).
4. Foto: metrik dengan dua gold (label sumber Commons dan tinjauan visual AI), ketepatan AUTO_LINK,
   forced-link rate, recall OTHER, uji V3 vs V2.
Keluaran: hasil_eksperimen/analisis_paper.md dan hasil_eksperimen/analisis_paper.json (dipakai pembuat gambar).

Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe skrip\\analisis_paper.py
"""
import csv
import glob
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analisis_lanjut as al  # noqa: E402
import hitung_metrik as hm  # noqa: E402
import konversi_ui as ku  # noqa: E402

DUMP = "hasil_eksperimen/hasil_retrieval/2026-11-02/retrieval_dump.csv"
GOLD = "gold/final/gold_semua_dataset_final.csv"
HARN = Path("hasil_eksperimen/hasil_harness")
DS_DUMP = {"N08": "N08VAR"}


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_items():
    """Butir atribut (ONE_TO_ONE/NO_MATCH) dengan prediksi S4/S1/S2 dari harness rep1 + kandidat retrieval."""
    gold = read(GOLD)
    root_a = HARN / "2026-10-31" / "rep1"
    items = al.load_attr(root_a, HARN / "2026-11-01_bc3c21b" / "rep1", root_a / "atribut_n08var", gold)
    by_id = {g["mapping_item_id"]: g for g in gold}
    cands = {}
    for r in read(DUMP):
        cands.setdefault((r["dataset"], r["source_attribute"].strip(), r["source_context"].strip()), []).append(r)
    for it in items:
        g = by_id[it["id"]]
        key = (DS_DUMP.get(it["dataset"], it["dataset"]), g["source_attribute"].strip(), (g["source_context"] or "").strip())
        c = sorted(cands.get(key, []), key=lambda r: int(r["rank"]))
        it["cands"] = [(r["canonical_key"], float(r["distance"])) for r in c if r["rank"] != "0"]
        it["top1_dist"] = it["cands"][0][1] if it["cands"] else None
    return items


def s2tau(items, tau):
    for it in items:
        if it["method"].startswith("exact"):
            it["S2T"] = it["S4"]
        elif it["top1_dist"] is not None and it["top1_dist"] <= tau:
            it["S2T"] = it["cands"][0][0]
        else:
            it["S2T"] = ""
    return items


def metrics(items, v):
    return hm.attr_metrics([{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[v]} for i in items])


def ci_f1(items, v):
    sel = [{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[v]} for i in items]
    return hm.ci([b["f1"] for b in hm.bootstrap(sel, hm.attr_metrics)])


def main():
    items = load_items()
    missing = [i for i in items if not i["method"].startswith("exact") and i["top1_dist"] is None and i["method"] != "tidak_dihasilkan"]
    dev = [i for i in items if i["dataset"] in al.DEV]
    held = [i for i in items if i["dataset"] in al.HELDOUT]

    # 1) tuning tau di dev
    grid = sorted({i["top1_dist"] for i in dev if i["top1_dist"] is not None})
    best = max(grid, key=lambda t: (metrics(s2tau(dev, t), "S2T")["f1"], -t))
    tau = best
    s2tau(items, tau)
    out, res = [], {"tau": tau, "n_missing_candidates": len(missing)}
    out += ["# Analisis tambahan untuk paper", "",
            f"Gold atribut: `{GOLD}` (identik dengan gold awal). tau S2+tau = {tau:.4f} (dituning di dev, maks. Mapping F1).",
            f"Butir semantik tanpa kandidat di dump: {len(missing)}.", "",
            "## 1. Pemetaan atribut per varian", "",
            "| Himpunan | Varian | n target / NULL | Precision | Recall | F1 (CI 95%) | Recall NULL |", "|---|---|---|---|---|---|---|"]
    res["mapping"] = {}
    sem = lambda xs: [i for i in xs if not i["method"].startswith("exact")]
    for lab, sub in (("held-out", held), ("held-out semantik", sem(held)), ("dev", dev), ("semua", items), ("semua semantik", sem(items))):
        for v in ("S1", "S2", "S2T", "S4"):
            m = metrics(sub, v)
            lo, hi = ci_f1(sub, v)
            res["mapping"].setdefault(lab, {})[v] = {**m, "f1_lo": lo, "f1_hi": hi}
            rn = "-" if m["recall_atribut_baru"] is None else f"{m['recall_atribut_baru']:.3f}"
            out.append(f"| {lab} | {v.replace('S2T', 'S2+tau')} | {m['n_target']} / {m['n_tanpa_target']} | {m['precision']:.3f} | "
                       f"{m['recall']:.3f} | {m['f1']:.3f} ({lo:.3f} sampai {hi:.3f}) | {rn} |")
    out.append("")

    # uji berpasangan held-out (Holm, satu keluarga)
    comps = [("S4", "S1"), ("S4", "S2"), ("S4", "S2T")]
    r = [al.paired(held, al.attr_f1(a), al.attr_f1(b)) for a, b in comps]
    r.append(al.paired(held, al.attr_new("S4"), al.attr_new("S2T")))
    names = [f"{a} vs {b} F1" for a, b in comps] + ["S4 vs S2T recall NULL"]
    adj = al.holm([x[3] for x in r])
    out += ["## 2. Uji berpasangan held-out (bootstrap 10.000, Holm)", "", "| Perbandingan | Selisih | CI 95% | p Holm |", "|---|---|---|---|"]
    res["paired_heldout"] = []
    for n, x, p in zip(names, r, adj):
        out.append(f"| {n.replace('S2T', 'S2+tau')} | {x[0]:+.3f} | {x[1]:+.3f} sampai {x[2]:+.3f} | {p:.4f} |")
        res["paired_heldout"].append({"cmp": n, "diff": x[0], "lo": x[1], "hi": x[2], "p_holm": p})
    out.append("")

    # 2) Hit@k pada butir semantik bertarget
    tgt = [i for i in sem(items) if i["gold_status"] == "ONE_TO_ONE" and i["cands"]]
    def hit(k):
        return sum(1 for i in tgt if i["gold_key"] in [c[0] for c in i["cands"][:k]]) / len(tgt)
    hit_all = sum(1 for i in tgt if i["gold_key"] in [c[0] for c in i["cands"]]) / len(tgt)
    mrr = sum(next((1 / (n + 1) for n, c in enumerate(i["cands"]) if c[0] == i["gold_key"]), 0) for i in tgt) / len(tgt)
    avg_c = st.mean(len(i["cands"]) for i in tgt)
    res["retrieval"] = {"n": len(tgt), "hit1": hit(1), "hit5": hit(5), "hit8": hit(8), "hit_all": hit_all, "mrr": mrr, "avg_candidates": avg_c}
    out += ["## 3. Retrieval pada butir semantik bertarget", "",
            f"n = {len(tgt)}; rata-rata kandidat yang dilihat reranker {avg_c:.1f} (top-8 + header-only fallback).",
            f"Hit@1 {hit(1):.3f}; Hit@5 {hit(5):.3f}; Hit@8 {hit(8):.3f}; Hit@semua kandidat {hit_all:.3f}; MRR {mrr:.3f}.", ""]

    # 3) latency
    lat = {}
    for ds, sub in (("R01", "atribut/R01"), ("R02", "atribut/R02"), ("N07", "atribut/N07"), ("N09", "atribut/N09"), ("N08", "atribut_n08var/N08")):
        s4 = [json.load(open(f, encoding="utf-8"))["detik"] for f in glob.glob(str(HARN / "2026-10-31" / "rep*" / sub / "meta.json"))]
        s3 = [json.load(open(f, encoding="utf-8"))["detik"] for f in glob.glob(str(HARN / "2026-11-02_S3" / "rep*" / sub / "meta.json"))]
        lat[ds] = {"S4": s4, "S3": s3}
    res["latency"] = lat
    out += ["## 4. Latency per run (detik; median dari pengulangan)", "", "| Dataset | S4 median (n) | S3 median (n) | S3/S4 |", "|---|---|---|---|"]
    for ds, v in lat.items():
        a, b = st.median(v["S4"]), st.median(v["S3"])
        out.append(f"| {ds} | {a:.0f} ({len(v['S4'])}) | {b:.0f} ({len(v['S3'])}) | {b / a:.2f} |")
    tot4 = sum(st.median(v["S4"]) for v in lat.values()); tot3 = sum(st.median(v["S3"]) for v in lat.values())
    out += [f"| Total | {tot4:.0f} | {tot3:.0f} | {tot3 / tot4:.2f} |", "",
            "Catatan: S4 commit 323f1e4 (31 Okt), S3 commit 6217420 (2 Nov); waktu dinding termasuk antrean provider.", ""]

    # 4) foto
    # 4 Nov 2026 (D18): 19 baris run UI 1 Nov ternyata jawaban mock; dipakai versi terkoreksi bila ada (skrip/koreksi_foto_mock.py).
    koreksi = Path("hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar")
    ui = str(koreksi) if koreksi.exists() else glob.glob("hasil_eksperimen/hasil_ui/2026-11-01/gambar")[0]
    res["photo_source"] = ui
    res["photo"] = {}
    for glab, gpath in (("label_sumber", "gambar/manifest/gold_gambar_manifest.csv"), ("tinjauan_visual_ai", "gambar/manifest/gold_gambar_manifest_final.csv")):
        ph = al.photo_items(ui, gpath)
        ok = lambda p: p["V3"][0] == p["gold"] and (p["gold"] != "KNOWN" or ku.norm(p["V3"][1]) == ku.norm(p["gold_var"]))
        sel = lambda xs, v: [{"gold": i["gold"], "gold_var": i["gold_var"], "pred": i[v][0], "pred_var": i[v][1]} for i in xs]
        d = {"n": len(ph), "classes": {c: sum(1 for p in ph if p["gold"] == c) for c in hm.CLASSES}}
        for v in ("V3", "V2"):
            m = hm.img_metrics(sel(ph, v))
            boots = hm.bootstrap(sel(ph, v), hm.img_metrics)
            d[v] = {**m, "mf1_ci": hm.ci([b["macro_f1"] for b in boots]), "top1_ci": hm.ci([b["top1_known"] or 0 for b in boots])}
        cm = {g: {p: sum(1 for x in ph if x["gold"] == g and x["V3"][0] == p) for p in hm.CLASSES} for g in hm.CLASSES}
        d["confusion_V3"] = cm
        nonknown = [p for p in ph if p["gold"] != "KNOWN"]
        d["forced_link"] = {"n": len(nonknown), "pred_known": sum(1 for p in nonknown if p["V3"][0] == "KNOWN"),
                            "auto_linked": sum(1 for p in nonknown if p["action"] == "AUTO_LINK")}
        other = [p for p in ph if p["gold"] == "OTHER"]
        d["other_recall"] = sum(1 for p in other if p["V3"][0] == "OTHER") / len(other)
        d["auto_link"] = {}
        for cond in ("INFORMATIF", "NETRAL", "MENYESATKAN", "SEMUA"):
            sub = [p for p in ph if cond == "SEMUA" or p["cond"] == cond]
            alk = [p for p in sub if p["action"] == "AUTO_LINK"]
            d["auto_link"][cond] = {"n_photos": len(sub), "auto_link": len(alk), "correct": sum(ok(p) for p in alk),
                                    "review": sum(1 for p in sub if p["action"].startswith("REVIEW")),
                                    "candidate": sum(1 for p in sub if p["action"] == "CANDIDATE")}
        x = al.paired(ph, al.photo_fn("V3"), al.photo_fn("V2"))
        d["V3_vs_V2"] = {"diff": x[0], "lo": x[1], "hi": x[2], "p": x[3]}
        res["photo"][glab] = d
        out += [f"## 5. Foto, gold = {glab} (n={len(ph)}; kelas {d['classes']})", "",
                f"V3: macro-F1 {d['V3']['macro_f1']:.3f} ({d['V3']['mf1_ci'][0]:.3f} sampai {d['V3']['mf1_ci'][1]:.3f}); "
                f"Top-1 KNOWN {d['V3']['top1_known']:.3f} ({d['V3']['top1_ci'][0]:.3f} sampai {d['V3']['top1_ci'][1]:.3f}).",
                f"V2: macro-F1 {d['V2']['macro_f1']:.3f}; Top-1 KNOWN {d['V2']['top1_known']:.3f}. "
                f"V3 vs V2 macro-F1 {x[0]:+.3f} ({x[1]:+.3f} sampai {x[2]:+.3f}), p {x[3]:.4f}.",
                f"Recall OTHER {d['other_recall']:.3f}. Forced link: {d['forced_link']['pred_known']} dari {d['forced_link']['n']} foto non-KNOWN "
                f"diprediksi KNOWN; {d['forced_link']['auto_linked']} di antaranya tertaut otomatis.",
                f"Matriks V3 (baris gold): {cm}", "",
                "| Nama file | Foto | AUTO_LINK | Benar | Precision | REVIEW | CANDIDATE |", "|---|---|---|---|---|---|---|"]
        for cond, a in d["auto_link"].items():
            pr = f"{a['correct'] / a['auto_link']:.3f}" if a["auto_link"] else "-"
            out.append(f"| {cond} | {a['n_photos']} | {a['auto_link']} | {a['correct']} | {pr} | {a['review']} | {a['candidate']} |")
        out.append("")

    Path("hasil_eksperimen/analisis_paper.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    Path("hasil_eksperimen/analisis_paper.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
