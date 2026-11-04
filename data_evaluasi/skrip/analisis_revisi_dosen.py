"""Analisis untuk revisi paper berdasarkan masukan dosen (3 November 2026), poin 2, 9, dan 10.

Tidak ada eksperimen baru; semua angka dihitung ulang dari keluaran harness yang sama dengan analisis_paper.py.

Poin 2  - Bootstrap per workbook (cluster bootstrap) dan F1 per workbook. Butir dalam satu workbook saling berkaitan,
          jadi workbook yang diresampel, bukan butir.
Poin 9  - Sensitivitas terhadap 19 butir AMBIGUOUS/COMPOSITE yang dikeluarkan dari skor inti:
          longgar (kunci mana pun benar) dan pesimis (tidak pernah benar).
Poin 10 - Rincian beban review menurut alasan sistem (usulan NULL vs usulan baris yang diragukan) dan status gold.

Keluaran: hasil_eksperimen/analisis_revisi_dosen.md dan .json
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\analisis_revisi_dosen.py
"""
import csv
import json
import random
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analisis_lanjut as al  # noqa: E402
import analisis_paper as ap  # noqa: E402
import hitung_metrik as hm  # noqa: E402
import konversi_ui as ku  # noqa: E402

N_BOOT = 10000
SEED = 20261103
HARN = ap.HARN
ROOT_A = HARN / "2026-10-31" / "rep1"
ROOT_B = HARN / "2026-11-01_bc3c21b" / "rep1"
ROOT_S3 = HARN / "2026-11-02_S3" / "rep1"
EXTRA = ("AMBIGUOUS", "COMPOSITE")
VARIANTS = ("S1", "S2", "S2T", "S3", "S4")
NAME = {"S2T": "S2+tau"}
ORDER = ["R01", "S01", "S02", "S03", "R02", "N07", "N08", "N09"]


# ------------------------------------------------------------------ data
def gold_rows(include_extra):
    """Gold; bila include_extra, butir AMBIGUOUS/COMPOSITE dijadikan bertarget dengan himpunan kunci gabungan."""
    rows = []
    for g in ap.read(ap.GOLD):
        g = dict(g)
        g["orig_status"] = g["gold_status"]
        if include_extra and g["gold_status"] in EXTRA:
            keys = [k for k in (g["gold_canonical_keys"] + "|" + g["ambiguous_candidate_canonical_keys"]).split("|") if k.strip()]
            g["gold_status"] = "ONE_TO_ONE"
            g["gold_canonical_keys"] = "|".join(dict.fromkeys(k.strip() for k in keys))
        rows.append(g)
    return rows


def load(include_extra):
    gold = gold_rows(include_extra)
    items = al.load_attr(ROOT_A, ROOT_B, ROOT_A / "atribut_n08var", gold)
    s3 = {i["id"]: i["S4"] for i in al.load_attr(ROOT_S3, ROOT_B, ROOT_S3 / "atribut_n08var", gold)}
    by_id = {g["mapping_item_id"]: g for g in gold}
    cands = {}
    for r in ap.read(ap.DUMP):
        cands.setdefault((r["dataset"], r["source_attribute"].strip(), r["source_context"].strip()), []).append(r)
    for it in items:
        g = by_id[it["id"]]
        it["orig_status"] = g["orig_status"]
        key = (ap.DS_DUMP.get(it["dataset"], it["dataset"]), g["source_attribute"].strip(), (g["source_context"] or "").strip())
        c = sorted(cands.get(key, []), key=lambda r: int(r["rank"]))
        it["cands"] = [(r["canonical_key"], float(r["distance"])) for r in c if r["rank"] != "0"]
        it["top1_dist"] = it["cands"][0][1] if it["cands"] else None
        it["S3"] = s3.get(it["id"]) if it["dataset"] in {"R01", "R02", "N07", "N08", "N09"} else None
    return items


def tau_from_dev(items):
    """Sama dengan analisis_paper.py: tau dipilih di dev pada butir inti, lalu dibekukan."""
    dev = [i for i in items if i["dataset"] in al.DEV and i["orig_status"] not in EXTRA]
    grid = sorted({i["top1_dist"] for i in dev if i["top1_dist"] is not None})
    return max(grid, key=lambda t: (metrics(ap.s2tau(dev, t), "S2T")["f1"], -t))


# --------------------------------------------------------------- metrik
def metrics(items, v, mode="inti"):
    """mode inti/longgar: benar bila pred termasuk himpunan kunci gold. mode pesimis: butir ekstra tidak pernah benar.
    mode abstain: butir ekstra diperlakukan seperti NO_MATCH (NULL = penolakan yang benar, baris lain = salah tulis);
    memilih salah satu kunci yang mungkin tidak dihukum dan tidak dihitung (butir dibuang)."""
    if mode == "abstain":
        kept = []
        for i in items:
            if i["orig_status"] in EXTRA:
                if i[v] and i[v] in i["gold_key"].split("|"):
                    continue
                i = {**i, "gold_status": "NO_MATCH"}
            kept.append(i)
        items = kept
    target = [i for i in items if i["gold_status"] == "ONE_TO_ONE"]
    notarget = [i for i in items if i["gold_status"] == "NO_MATCH"]
    keyed = [i for i in target + notarget if i[v]]

    def ok(i):
        if mode == "pesimis" and i["orig_status"] in EXTRA:
            return False
        return bool(i[v]) and i[v] in i["gold_key"].split("|")
    tp = sum(1 for i in target if ok(i))
    p = tp / len(keyed) if keyed else 0.0
    r = tp / len(target) if target else 0.0
    return {"n_target": len(target), "n_null": len(notarget), "precision": p, "recall": r, "f1": hm.f1(p, r),
            "null_recall": (sum(1 for i in notarget if not i[v]) / len(notarget)) if notarget else None}


def pct(vals):
    vals = sorted(vals)
    return vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]


def cluster_boot(items, fn, n=N_BOOT, seed=SEED):
    """Resampel workbook dengan pengembalian; fn: daftar butir -> skor."""
    groups = {}
    for i in items:
        groups.setdefault(i["dataset"], []).append(i)
    keys = sorted(groups)
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        s = []
        for _k in keys:
            s.extend(groups[keys[rng.randrange(len(keys))]])
        out.append(fn(s))
    return out


def item_boot(items, fn, n=N_BOOT, seed=SEED):
    rng = random.Random(seed)
    m = len(items)
    return [fn([items[rng.randrange(m)] for _ in range(m)]) for _ in range(n)]


def f1_of(v, mode="inti"):
    return lambda xs: metrics(xs, v, mode)["f1"]


def paired_cluster(items, va, vb):
    obs = f1_of(va)(items) - f1_of(vb)(items)
    diffs = cluster_boot(items, lambda s: f1_of(va)(s) - f1_of(vb)(s))
    lo, hi = pct(diffs)
    p = min(1.0, 2 * min(sum(d <= 0 for d in diffs), sum(d >= 0 for d in diffs)) / len(diffs))
    return obs, lo, hi, p


def fmt(x):
    return "-" if x is None else f"{x:.3f}"


# ---------------------------------------------------------- poin 10: review
def review_rows():
    """Baris mapping S4 rep1 dengan status penerimaan, dipasangkan ke gold (termasuk butir ekstra)."""
    gold = ap.read(ap.GOLD)
    exact = {(g["dataset_id"], g["source_attribute_display"].strip()): g for g in gold}
    fuzzy = {}
    for g in gold:
        fuzzy.setdefault((g["dataset_id"], ku.norm(g["source_attribute_display"])), []).append(g)
    sources = [(ds, ROOT_A / "atribut" / ds / "mapping.csv") for ds in ("R01", "R02", "N07", "N09")]
    sources.append(("N08", ROOT_A / "atribut_n08var" / "N08" / "mapping.csv"))
    sources += [(ds, ROOT_B / "kombinasi" / ds / "mapping.csv") for ds in ("S01", "S02", "S03")]
    rows = []
    for ds, f in sources:
        for r in ap.read(f):
            disp = r["source_attribute_display"].strip()
            g = exact.get((ds, disp))
            if g is None:
                c = fuzzy.get((ds, ku.norm(disp)), [])
                g = c[0] if len(c) == 1 else None
            if g is None:
                continue
            prop = (r.get("proposed_target_canonical_key") or "").strip()
            status = r["acceptance_status"].strip()
            if status == "AUTO_ACCEPT":
                reason = "AUTO_ACCEPT"
            elif status == "REVIEW" and not prop:
                reason = "REVIEW_NULL"
            elif status == "REVIEW":
                reason = "REVIEW_RAGU"
            else:
                reason = status or "LAIN"
            keys = (g["gold_canonical_keys"] + "|" + g["ambiguous_candidate_canonical_keys"]).split("|")
            correct = bool(prop) and prop in [k.strip() for k in keys if k.strip()]
            rows.append({"dataset": ds, "gold": g["gold_status"], "reason": reason, "prop": prop, "correct": correct,
                         "conf": r.get("confidence", ""), "label": ku.norm(r["source_attribute"])})
    return rows


# ------------------------------------------------------------------ main
def main():
    core = [i for i in load(include_extra=False)]
    ext = load(include_extra=True)
    tau = tau_from_dev(core)
    ap.s2tau(core, tau)
    ap.s2tau(ext, tau)
    held = lambda xs: [i for i in xs if i["dataset"] in al.HELDOUT]
    dev = lambda xs: [i for i in xs if i["dataset"] in al.DEV]
    s3set = lambda xs: [i for i in xs if i["S3"] is not None]
    res = {"tau": tau, "n_boot": N_BOOT, "seed": SEED}
    out = ["# Analisis revisi paper (masukan dosen poin 2, 9, 10)", "",
           f"Sumber: harness rep1 (S1/S2/S4: 2026-10-31 dan 2026-11-01_bc3c21b; S3: 2026-11-02_S3). Gold `{ap.GOLD}`. "
           f"tau S2+tau = {tau:.4f} (sama dengan analisis_paper.py). Bootstrap {N_BOOT} ulangan, seed {SEED}.", ""]

    # ---------------- poin 2a: F1 per workbook
    out += ["## Poin 2a. F1 per workbook (butir inti)", "",
            "| Workbook | Split | T / N | S1 | S2 | S2+tau | S3 | S4 | S4 P | S4 R | S4 NULL R |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    res["per_workbook"] = {}
    for ds in ORDER:
        sub = [i for i in core if i["dataset"] == ds]
        m4 = metrics(sub, "S4")
        row = {v: (metrics(sub, v)["f1"] if all(i[v] is not None for i in sub) else None) for v in VARIANTS}
        res["per_workbook"][ds] = {**row, "n_target": m4["n_target"], "n_null": m4["n_null"], "S4_detail": m4}
        split = "held-out" if ds in al.HELDOUT else "dev"
        out.append(f"| {ds} | {split} | {m4['n_target']} / {m4['n_null']} | " + " | ".join(fmt(row[v]) for v in VARIANTS) +
                   f" | {m4['precision']:.3f} | {m4['recall']:.3f} | {fmt(m4['null_recall'])} |")
    out += ["", "Catatan: F1 R01 dihitung dari 1 butir bertarget sehingga hanya bernilai 0 atau 1; S3 tidak dijalankan pada S01 sampai S03.", ""]

    # rata-rata makro per workbook dan konsistensi arah
    out += ["### Rata-rata F1 per workbook (macro) dan konsistensi arah, held-out", "",
            "| Varian | F1 gabungan (micro) | Rata-rata F1 per workbook | Min | Maks | S4 lebih tinggi di | S4 sama |", "|---|---|---|---|---|---|---|"]
    res["macro_heldout"] = {}
    for v in VARIANTS:
        vals = [res["per_workbook"][d][v] for d in ORDER if d in al.HELDOUT]
        micro = metrics(held(core), v)["f1"]
        s4 = [res["per_workbook"][d]["S4"] for d in ORDER if d in al.HELDOUT]
        better = sum(a > b + 1e-9 for a, b in zip(s4, vals))
        same = sum(abs(a - b) <= 1e-9 for a, b in zip(s4, vals))
        res["macro_heldout"][v] = {"micro": micro, "macro": st.mean(vals), "min": min(vals), "max": max(vals), "s4_better": better, "s4_same": same}
        cmpcol = "-" if v == "S4" else f"{better} dari 4"
        samecol = "-" if v == "S4" else f"{same} dari 4"
        out.append(f"| {NAME.get(v, v)} | {micro:.3f} | {st.mean(vals):.3f} | {min(vals):.3f} | {max(vals):.3f} | {cmpcol} | {samecol} |")
    out.append("")

    # ---------------- poin 2b: CI per butir vs per workbook
    out += ["## Poin 2b. Selang kepercayaan F1: bootstrap per butir vs per workbook", "",
            "| Himpunan | Varian | F1 | CI per butir | CI per workbook (cluster) |", "|---|---|---|---|---|"]
    res["ci"] = {}
    for lab, sub in (("held-out (4 workbook)", held(core)), ("dev (4 workbook)", dev(core)), ("semua (8 workbook)", core)):
        for v in VARIANTS:
            s = sub if v != "S3" else s3set(sub)
            if not s or (v == "S3" and lab.startswith("dev")):
                continue
            f = metrics(s, v)["f1"]
            ib = pct(item_boot(s, f1_of(v)))
            cb = pct(cluster_boot(s, f1_of(v)))
            nwb = len({i["dataset"] for i in s})
            res["ci"].setdefault(lab, {})[v] = {"f1": f, "item_ci": ib, "cluster_ci": cb, "n_workbook": nwb}
            note = "" if v != "S3" else f" ({nwb} wb)"
            out.append(f"| {lab}{note} | {NAME.get(v, v)} | {f:.3f} | [{ib[0]:.3f}, {ib[1]:.3f}] | [{cb[0]:.3f}, {cb[1]:.3f}] |")
    out.append("")
    # untuk gambar: CI per workbook pada tiga kelompok Fig. 2 (format sama dengan analisis_paper.json["mapping"])
    sem = lambda xs: [i for i in xs if not i["method"].startswith("exact")]
    res["mapping_cluster"] = {}
    for key, sub in (("held-out", held(core)), ("held-out semantik", sem(held(core))), ("dev", dev(core))):
        for v in ("S1", "S2", "S2T", "S4"):
            lo, hi = pct(cluster_boot(sub, f1_of(v)))
            res["mapping_cluster"].setdefault(key, {})[v] = {"f1": metrics(sub, v)["f1"], "f1_lo": lo, "f1_hi": hi}
    out += ["CI per workbook pada stratum semantik held-out: " + "; ".join(
        f"{NAME.get(v, v)} {res['mapping_cluster']['held-out semantik'][v]['f1']:.3f} "
        f"[{res['mapping_cluster']['held-out semantik'][v]['f1_lo']:.3f}, {res['mapping_cluster']['held-out semantik'][v]['f1_hi']:.3f}]"
        for v in ("S1", "S2", "S2T", "S4")) + ".", ""]

    out += ["## Poin 2c. Uji berpasangan held-out dengan resampel workbook (Holm)", "",
            "| Perbandingan | Selisih F1 | CI 95% per workbook | p cluster | p Holm |", "|---|---|---|---|---|"]
    comps = [("S4", "S1"), ("S4", "S2"), ("S4", "S2T")]
    r = [paired_cluster(held(core), a, b) for a, b in comps]
    adj = al.holm([x[3] for x in r])
    res["paired_cluster_heldout"] = []
    for (a, b), x, p in zip(comps, r, adj):
        res["paired_cluster_heldout"].append({"cmp": f"{a} vs {b}", "diff": x[0], "lo": x[1], "hi": x[2], "p": x[3], "p_holm": p})
        out.append(f"| {a} vs {NAME.get(b, b)} | {x[0]:+.3f} | [{x[1]:+.3f}, {x[2]:+.3f}] | {x[3]:.4f} | {p:.4f} |")
    x = paired_cluster(s3set(held(core)), "S4", "S3")
    res["paired_cluster_s4_s3"] = {"diff": x[0], "lo": x[1], "hi": x[2], "p": x[3]}
    out += [f"| S4 vs S3 (eksploratori) | {x[0]:+.3f} | [{x[1]:+.3f}, {x[2]:+.3f}] | {x[3]:.4f} | - |", "",
            "Dengan hanya 4 workbook held-out, resampel per workbook hanya punya 35 kombinasi berbeda, jadi CI kasar. "
            "p cluster bernilai 0 karena S4 lebih tinggi pada setiap workbook sehingga semua resampel positif; ini setara dengan "
            "pernyataan arah per workbook (tabel 2a), bukan bukti yang lebih kuat. Uji eksak yang paling jujur untuk 4 dari 4 workbook "
            "adalah uji tanda satu sisi, p = 0,0625; dengan 8 workbook (dev + held-out) dan S4 lebih tinggi di semuanya, p = 0,0039.", ""]
    allwb = {d: {v: res["per_workbook"][d][v] for v in ("S1", "S2", "S2T", "S4")} for d in ORDER}
    res["sign_all8"] = {b: sum(allwb[d]["S4"] > allwb[d][b] + 1e-9 for d in ORDER) for b in ("S1", "S2", "S2T")}
    out += [f"S4 lebih tinggi dari S1/S2/S2+tau pada {res['sign_all8']['S1']}/{res['sign_all8']['S2']}/{res['sign_all8']['S2T']} dari 8 workbook.", ""]

    # leave-one-workbook-out
    out += ["### Leave-one-workbook-out, held-out (F1 bila satu workbook dibuang)", "", "| Dibuang | S1 | S2 | S2+tau | S4 |", "|---|---|---|---|---|"]
    res["lowo"] = {}
    for d in ORDER:
        if d not in al.HELDOUT:
            continue
        sub = [i for i in held(core) if i["dataset"] != d]
        vals = {v: metrics(sub, v)["f1"] for v in ("S1", "S2", "S2T", "S4")}
        res["lowo"][d] = vals
        out.append(f"| {d} | " + " | ".join(f"{vals[v]:.3f}" for v in ("S1", "S2", "S2T", "S4")) + " |")
    out.append("")

    # ---------------- poin 9: sensitivitas
    extra_items = [i for i in ext if i["orig_status"] in EXTRA]
    out += ["## Poin 9. Sensitivitas terhadap 19 butir AMBIGUOUS/COMPOSITE", "",
            f"Butir ekstra yang dinilai: {len(extra_items)} (semua di held-out: "
            + ", ".join(f"{d} {sum(1 for i in extra_items if i['dataset'] == d)}" for d in ORDER if any(i['dataset'] == d for i in extra_items)) + ").",
            "Longgar: butir ekstra dihitung bertarget dan benar bila prediksi termasuk salah satu kunci yang mungkin. "
            "Pesimis: butir ekstra dihitung bertarget dan tidak pernah benar (batas bawah). "
            "Abstain benar: butir ekstra diperlakukan seperti NO_MATCH, karena sumber tidak cukup untuk memilih satu baris; "
            "NULL dihitung penolakan yang benar, baris di luar kemungkinan dihitung salah tulis, dan memilih salah satu kunci yang mungkin dibuang dari skor.", "",
            "| Himpunan | Skenario | Varian | n target / NULL | P | R | F1 [CI per workbook] |", "|---|---|---|---|---|---|---|"]
    res["sensitivity"] = {}
    for lab, fsel in (("held-out", held), ("semua", lambda xs: xs)):
        for scen, items, mode in (("inti (paper)", fsel(core), "inti"), ("longgar", fsel(ext), "longgar"), ("pesimis", fsel(ext), "pesimis"),
                                  ("abstain benar", fsel(ext), "abstain")):
            for v in ("S1", "S2", "S2T", "S4"):
                m = metrics(items, v, mode)
                cb = pct(cluster_boot(items, f1_of(v, mode)))
                res["sensitivity"].setdefault(lab, {}).setdefault(scen, {})[v] = {**m, "cluster_ci": cb}
                out.append(f"| {lab} | {scen} | {NAME.get(v, v)} | {m['n_target']} / {m['n_null']} | {m['precision']:.3f} | {m['recall']:.3f} | "
                           f"{m['f1']:.3f} [{cb[0]:.3f}, {cb[1]:.3f}] |")
    out.append("")
    out += ["### Apa yang dilakukan tiap varian pada 19 butir itu", "", "| Varian | Memilih salah satu kunci yang mungkin | Memilih baris lain | NULL (abstain) |", "|---|---|---|---|"]
    res["extra_behaviour"] = {}
    for v in ("S1", "S2", "S2T", "S3", "S4"):
        xs = [i for i in extra_items if i[v] is not None]
        okc = sum(1 for i in xs if i[v] and i[v] in i["gold_key"].split("|"))
        wrong = sum(1 for i in xs if i[v] and i[v] not in i["gold_key"].split("|"))
        null = sum(1 for i in xs if not i[v])
        res["extra_behaviour"][v] = {"n": len(xs), "candidate": okc, "other": wrong, "null": null}
        out.append(f"| {NAME.get(v, v)} (n={len(xs)}) | {okc} | {wrong} | {null} |")
    out += ["", "| Butir | Workbook | Status | Kunci yang mungkin | S4 | S2 |", "|---|---|---|---|---|---|"]
    for i in sorted(extra_items, key=lambda i: (ORDER.index(i["dataset"]), i["id"])):
        g = next(g for g in ap.read(ap.GOLD) if g["mapping_item_id"] == i["id"])
        out.append(f"| {g['source_attribute_display']} | {i['dataset']} | {i['orig_status']} | {i['gold_key'].replace('|', ', ')} | {i['S4'] or 'NULL'} | {i['S2'] or 'NULL'} |")
    out.append("")

    # ---------------- poin 10: review
    rows = review_rows()
    out += ["## Poin 10. Beban review menurut alasan sistem", "",
            "REVIEW_NULL = sistem mengusulkan tidak ada padanan (NULL) dan meminta konfirmasi kurator. "
            "REVIEW_RAGU = sistem mengusulkan baris tetapi tidak cukup yakin untuk menulis otomatis.", "",
            "| Himpunan | Butir | AUTO_ACCEPT | REVIEW_NULL | REVIEW_RAGU | Lain |", "|---|---|---|---|---|---|"]
    res["review"] = {}
    for lab, sel in (("dev", lambda r: r["dataset"] in al.DEV), ("held-out", lambda r: r["dataset"] in al.HELDOUT), ("semua", lambda r: True)):
        for scope, gsel in (("inti", lambda r: r["gold"] in ("ONE_TO_ONE", "NO_MATCH")), ("termasuk AMB/COMP", lambda r: True)):
            xs = [r for r in rows if sel(r) and gsel(r)]
            c = {k: sum(1 for r in xs if r["reason"] == k) for k in ("AUTO_ACCEPT", "REVIEW_NULL", "REVIEW_RAGU")}
            lain = len(xs) - sum(c.values())
            res["review"].setdefault(lab, {})[scope] = {"n": len(xs), **c, "lain": lain}
            out.append(f"| {lab}, {scope} | {len(xs)} | {c['AUTO_ACCEPT']} ({c['AUTO_ACCEPT'] / len(xs):.0%}) | "
                       f"{c['REVIEW_NULL']} ({c['REVIEW_NULL'] / len(xs):.0%}) | {c['REVIEW_RAGU']} | {lain} |")
    out += ["", "### REVIEW_NULL menurut status gold (semua workbook, termasuk AMB/COMP)", "",
            "| Status gold | REVIEW_NULL | AUTO_ACCEPT benar | AUTO_ACCEPT salah |", "|---|---|---|---|"]
    res["review_by_gold"] = {}
    for gs in ("NO_MATCH", "ONE_TO_ONE", "AMBIGUOUS", "COMPOSITE"):
        xs = [r for r in rows if r["gold"] == gs]
        rn = sum(1 for r in xs if r["reason"] == "REVIEW_NULL")
        aa_ok = sum(1 for r in xs if r["reason"] == "AUTO_ACCEPT" and r["correct"])
        aa_bad = sum(1 for r in xs if r["reason"] == "AUTO_ACCEPT" and not r["correct"])
        res["review_by_gold"][gs] = {"review_null": rn, "auto_ok": aa_ok, "auto_bad": aa_bad}
        out.append(f"| {gs} | {rn} | {aa_ok} | {aa_bad} |")
    out += ["", "### Beban review per workbook (butir inti)", "", "| Workbook | Butir | REVIEW_NULL | di antaranya gold NO_MATCH | di antaranya bertarget |", "|---|---|---|---|---|"]
    res["review_per_workbook"] = {}
    for d in ORDER:
        xs = [r for r in rows if r["dataset"] == d and r["gold"] in ("ONE_TO_ONE", "NO_MATCH")]
        rn = [r for r in xs if r["reason"] == "REVIEW_NULL"]
        nm = sum(1 for r in rn if r["gold"] == "NO_MATCH")
        res["review_per_workbook"][d] = {"n": len(xs), "review_null": len(rn), "gold_no_match": nm}
        out.append(f"| {d} | {len(xs)} | {len(rn)} | {nm} | {len(rn) - nm} |")
    confs = sorted({f"{float(r['conf']):.2f}" for r in rows if r["reason"] == "AUTO_ACCEPT" and r["conf"]})
    rn_all = [r for r in rows if r["reason"] == "REVIEW_NULL" and r["gold"] in ("ONE_TO_ONE", "NO_MATCH")]
    rn_held = [r for r in rn_all if r["dataset"] in al.HELDOUT]
    uniq_all, uniq_held = len({r["label"] for r in rn_all}), len({r["label"] for r in rn_held})
    rep = sorted({r["label"] for r in rn_held if sum(1 for x in rn_held if x["label"] == r["label"]) > 1})
    res["review_unique"] = {"all": {"items": len(rn_all), "labels": uniq_all}, "heldout": {"items": len(rn_held), "labels": uniq_held,
                                                                                         "repeated_labels": len(rep)}}
    out += ["", f"Keyakinan pada AUTO_ACCEPT: {', '.join(confs)}. Tidak ada usulan baris yang ditahan karena keyakinan rendah.", "",
            f"Label unik di antrean REVIEW_NULL (nama sumber dinormalisasi): semua {len(rn_all)} butir -> {uniq_all} label; "
            f"held-out {len(rn_held)} butir -> {uniq_held} label ({len(rep)} label muncul lebih dari sekali). "
            "Bila keputusan 'tanpa padanan' disimpan per label (mis. lewat katalog atribut/skema dinamis), kurator cukup memutuskan sekali per label.", ""]

    Path("hasil_eksperimen/analisis_revisi_dosen.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    Path("hasil_eksperimen/analisis_revisi_dosen.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
