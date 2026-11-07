"""Skor pemetaan atribut end-to-end: run harness baru vs run pembanding (mis. bge-m3 vs MiniLM).

Pencocokan butir sama dengan analisis_lanjut.load_attr: per (dataset, source_attribute_display), lalu nama
ternormalisasi bila unik. Varian: S4 (sistem penuh), S1 (exact-name saja), S2 (retrieval top-1 tanpa LLM).
Metrik inti (hitung_metrik.attr_metrics): precision, recall, F1 butir ONE_TO_ONE, recall NULL butir NO_MATCH.
Beban review: AUTO_ACCEPT benar/salah, REVIEW_NULL, REVIEW_RAGU (definisi analisis_revisi_dosen.py).

Jalankan dari folder data_evaluasi:
  python skrip/skor_atribut_e2e.py --baru <root run baru> --lama-a <root atribut lama> --lama-b <root kombinasi lama>
       --label-baru bge-m3 --label-lama MiniLM --out hasil_eksperimen/<nama>
<root> berisi rep1..repN/{atribut,atribut_n08var,kombinasi}/<ID>/mapping.csv (struktur harness_vps.py).
"""
import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analisis_lanjut as al  # noqa: E402
import hitung_metrik as hm  # noqa: E402
import konversi_ui as ku  # noqa: E402

GOLD = "gold/final/gold_semua_dataset_final.csv"
HELD = ("R02", "N07", "N08", "N09")
DEV = ("S01", "S02", "S03")
# Workbook yang isinya identik sebelum dan sesudah pembersihan D19 (perbandingan model paling bersih).
INPUT_SAMA = ("R02", "N07", "N09")
VARIAN = ("S1", "S2", "S4")


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sumber(root_a, root_b, rep):
    s = [(ds, Path(root_a) / f"rep{rep}" / "atribut" / ds / "mapping.csv") for ds in ("R02", "N07", "N09")]
    s.append(("N08", Path(root_a) / f"rep{rep}" / "atribut_n08var" / "N08" / "mapping.csv"))
    s += [(ds, Path(root_b) / f"rep{rep}" / "kombinasi" / ds / "mapping.csv") for ds in DEV]
    return s


def butir(gold, root_a, root_b, rep):
    exact = {(g["dataset_id"], g["source_attribute_display"].strip()): g for g in gold}
    fuzzy = {}
    for g in gold:
        fuzzy.setdefault((g["dataset_id"], ku.norm(g["source_attribute_display"])), []).append(g)
    rows, dijalankan = {}, set()
    for ds, f in sumber(root_a, root_b, rep):
        if not f.exists():
            continue
        dijalankan.add(ds)
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
            status = (r.get("acceptance_status") or "").strip()
            alasan = ("AUTO_ACCEPT" if status == "AUTO_ACCEPT" else
                      "REVIEW_NULL" if status == "REVIEW" and not prop else
                      "REVIEW_RAGU" if status == "REVIEW" else status or "LAIN")
            rows[g["mapping_item_id"]] = {
                "id": g["mapping_item_id"], "dataset": ds, "gold_status": g["gold_status"],
                "gold_key": g["gold_canonical_keys"], "S4": prop, "S1": prop if method.startswith("exact") else "",
                "S2": (r.get("retrieval_s2_key") or "").strip(), "method": method, "alasan": alasan}
    for g in gold:
        if g["dataset_id"] in dijalankan and g["mapping_item_id"] not in rows:
            rows[g["mapping_item_id"]] = {"id": g["mapping_item_id"], "dataset": g["dataset_id"],
                                          "gold_status": g["gold_status"], "gold_key": g["gold_canonical_keys"],
                                          "S4": "", "S1": "", "S2": "", "method": "tidak_dihasilkan", "alasan": "TIDAK_DIHASILKAN"}
    return {k: v for k, v in rows.items() if v["gold_status"] in ("ONE_TO_ONE", "NO_MATCH")}


def metrik(items, v):
    return hm.attr_metrics([{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[v]} for i in items])


def ci(items, v):
    sel = [{"gold_status": i["gold_status"], "gold_key": i["gold_key"], "pred_key": i[v]} for i in items]
    return hm.ci([b["f1"] for b in hm.bootstrap(sel, hm.attr_metrics)])


def beban(items):
    c = {k: 0 for k in ("AUTO_ACCEPT_benar", "AUTO_ACCEPT_salah", "REVIEW_NULL", "REVIEW_RAGU", "lain")}
    for i in items:
        if i["alasan"] == "AUTO_ACCEPT":
            ok = (i["gold_status"] == "ONE_TO_ONE" and i["S4"] == i["gold_key"])
            c["AUTO_ACCEPT_benar" if ok else "AUTO_ACCEPT_salah"] += 1
        elif i["alasan"] in ("REVIEW_NULL", "REVIEW_RAGU"):
            c[i["alasan"]] += 1
        else:
            c["lain"] += 1
    return c


def latensi(root, reps):
    out = {}
    for rep in reps:
        for m in Path(root).glob(f"rep{rep}/*/*/meta.json"):
            j = json.loads(m.read_text(encoding="utf-8"))
            if j.get("status") == "ok":
                out.setdefault(f"{j['kind']}/{j['run']}", []).append(j["detik"])
    return {k: st.median(v) for k, v in sorted(out.items())}


def reps_di(root):
    return sorted(int(p.name[3:]) for p in Path(root).glob("rep[0-9]*") if p.name[3:].isdigit())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baru", required=True)
    ap.add_argument("--lama-a", required=True)
    ap.add_argument("--lama-b", required=True)
    ap.add_argument("--label-baru", default="baru")
    ap.add_argument("--label-lama", default="lama")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    gold = read(GOLD)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    reps_baru = [r for r in reps_di(a.baru) if r > 0]
    reps_lama = [r for r in reps_di(a.lama_a) if r > 0 and r in reps_di(a.lama_b)]
    run = {(a.label_baru, r): butir(gold, a.baru, a.baru, r) for r in reps_baru}
    run.update({(a.label_lama, r): butir(gold, a.lama_a, a.lama_b, r) for r in reps_lama})

    himpunan = {"held-out": HELD, "held-out input sama (R02, N07, N09)": INPUT_SAMA, "dev (S01-S03)": DEV}
    res = {"reps": {a.label_baru: reps_baru, a.label_lama: reps_lama}, "metrik": {}, "beban_review": {}, "berpasangan": []}
    md = [f"# Skor pemetaan atribut end-to-end: {a.label_baru} vs {a.label_lama}", "",
          f"Gold: `{GOLD}` (butir ONE_TO_ONE dan NO_MATCH). Run {a.label_baru}: `{a.baru}` (rep {reps_baru}). "
          f"Run {a.label_lama}: `{a.lama_a}` + `{a.lama_b}` (rep {reps_lama}).",
          "Workbook R02, N07, N09 identik di kedua run; N08 dan S01-S03 berubah karena pembersihan level varietas (D19), "
          "tetapi nama atributnya sama.", "",
          "## 1. Pemetaan atribut (rep1, CI 95% bootstrap; rerata antarpengulangan dalam kurung)", "",
          "| Himpunan | Run | Varian | n target / NULL | Precision | Recall | F1 rep1 (CI 95%) | F1 rerata (min-maks) | Recall NULL |",
          "|---|---|---|---|---|---|---|---|---|"]
    for lab, dss in himpunan.items():
        for label in (a.label_baru, a.label_lama):
            reps = reps_baru if label == a.label_baru else reps_lama
            if not reps:
                continue
            for v in VARIAN:
                per = [metrik([i for i in run[(label, r)].values() if i["dataset"] in dss], v) for r in reps]
                items1 = [i for i in run[(label, reps[0])].values() if i["dataset"] in dss]
                m = per[0]
                lo, hi = ci(items1, v)
                f1s = [p["f1"] for p in per]
                rn = "-" if m["recall_atribut_baru"] is None else f"{m['recall_atribut_baru']:.3f}"
                md.append(f"| {lab} | {label} | {v} | {m['n_target']} / {m['n_tanpa_target']} | {m['precision']:.3f} | "
                          f"{m['recall']:.3f} | {m['f1']:.3f} ({lo:.3f} sampai {hi:.3f}) | "
                          f"{st.mean(f1s):.3f} ({min(f1s):.3f}-{max(f1s):.3f}) | {rn} |")
                res["metrik"].setdefault(lab, {}).setdefault(label, {})[v] = {
                    **m, "f1_lo": lo, "f1_hi": hi, "f1_per_rep": f1s, "f1_rerata": st.mean(f1s)}
    md.append("")

    md += [f"## 2. Uji berpasangan {a.label_baru} vs {a.label_lama} (rep1, butir yang sama, bootstrap 10.000)", "",
           "| Himpunan | Varian | Selisih F1 | CI 95% | p | Selisih recall NULL | CI 95% |", "|---|---|---|---|---|---|---|"]
    if reps_lama:
        nb, nl = run[(a.label_baru, reps_baru[0])], run[(a.label_lama, reps_lama[0])]
        for lab, dss in himpunan.items():
            ids = [k for k in nb if k in nl and nb[k]["dataset"] in dss]
            for v in ("S2", "S4"):
                gab = [{**nb[k], "B": nb[k][v], "L": nl[k][v]} for k in ids]
                d = al.paired(gab, al.attr_f1("B"), al.attr_f1("L"))
                dn = al.paired(gab, al.attr_new("B"), al.attr_new("L"))
                md.append(f"| {lab} | {v} | {d[0]:+.3f} | {d[1]:+.3f} sampai {d[2]:+.3f} | {d[3]:.4f} | "
                          f"{dn[0]:+.3f} | {dn[1]:+.3f} sampai {dn[2]:+.3f} |")
                res["berpasangan"].append({"himpunan": lab, "varian": v, "n": len(ids), "selisih_f1": d[0],
                                           "lo": d[1], "hi": d[2], "p": d[3], "selisih_recall_null": dn[0],
                                           "lo_null": dn[1], "hi_null": dn[2]})
    md.append("")

    md += ["## 3. Beban review dan penulisan otomatis (rep1)", "",
           "| Himpunan | Run | Butir | AUTO_ACCEPT benar | AUTO_ACCEPT salah | REVIEW_NULL | REVIEW_RAGU | Lain |",
           "|---|---|---|---|---|---|---|---|"]
    for lab, dss in himpunan.items():
        for label, reps in ((a.label_baru, reps_baru), (a.label_lama, reps_lama)):
            if not reps:
                continue
            xs = [i for i in run[(label, reps[0])].values() if i["dataset"] in dss]
            c = beban(xs)
            md.append(f"| {lab} | {label} | {len(xs)} | {c['AUTO_ACCEPT_benar']} | {c['AUTO_ACCEPT_salah']} | "
                      f"{c['REVIEW_NULL']} | {c['REVIEW_RAGU']} | {c['lain']} |")
            res["beban_review"].setdefault(lab, {})[label] = c
    md.append("")

    lat_b = latensi(a.baru, reps_baru)
    lat_l = {**latensi(a.lama_a, reps_lama), **latensi(a.lama_b, reps_lama)}
    md += ["## 4. Latensi per run (detik, median antarpengulangan)", "",
           f"| Run | {a.label_baru} | {a.label_lama} |", "|---|---|---|"]
    for k in sorted(set(lat_b) | set(lat_l)):
        md.append(f"| {k} | {lat_b.get(k, '-')} | {lat_l.get(k, '-')} |")
    res["latensi"] = {a.label_baru: lat_b, a.label_lama: lat_l}
    md.append("")

    beda = []
    if reps_lama:
        for k, i in nb.items():
            if k in nl and i["S4"] != nl[k]["S4"]:
                beda.append({"dataset": i["dataset"], "id": k, "gold_status": i["gold_status"], "gold_key": i["gold_key"],
                             a.label_baru: i["S4"], a.label_lama: nl[k]["S4"],
                             "benar_baru": i["S4"] == (i["gold_key"] if i["gold_status"] == "ONE_TO_ONE" else ""),
                             "benar_lama": nl[k]["S4"] == (i["gold_key"] if i["gold_status"] == "ONE_TO_ONE" else "")})
        if beda:
            with open(out / "butir_berubah_S4.csv", "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(beda[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(beda)
    md += [f"Butir yang jawabannya berubah (S4, rep1): {len(beda)} (rincian `butir_berubah_S4.csv`).", ""]
    (out / "skor_atribut_e2e.md").write_text("\n".join(md), encoding="utf-8")
    (out / "skor_atribut_e2e.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
