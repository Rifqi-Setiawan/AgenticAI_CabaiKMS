"""Hitung metrik inti dengan membandingkan keluaran sistem dengan gold.

Pemakaian:
  python hitung_metrik.py atribut --gold gold/gold_semua_dataset.csv --pred pred_atribut.csv [--out hasil_atribut.csv]
  python hitung_metrik.py gambar  --gold gambar/manifest/gold_gambar_manifest.csv --pred pred_gambar.csv [--split test]

pred_atribut.csv  : mapping_item_id, predicted_key (kosong = tidak ada pemetaan)
pred_gambar.csv   : filename, predicted_status (KNOWN/OTHER/UNCERTAIN), predicted_variety (boleh kosong)

Hanya pustaka standar. Selang kepercayaan = bootstrap 95% (1000 ulangan, seed tetap).
"""
import argparse
import csv
import random
import sys

SEED = 20261029
N_BOOT = 1000


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f1(p, r):
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def ci(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return (None, None)
    return (values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))])


def bootstrap(items, fn):
    rng = random.Random(SEED)
    n = len(items)
    out = []
    for _ in range(N_BOOT):
        sample = [items[rng.randrange(n)] for _ in range(n)]
        out.append(fn(sample))
    return out


# ------------------------------------------------------------------ atribut
def attr_metrics(items):
    """items: list of dict(gold_status, gold_key, pred_key)."""
    target = [i for i in items if i["gold_status"] == "ONE_TO_ONE"]
    notarget = [i for i in items if i["gold_status"] == "NO_MATCH"]
    scope = target + notarget
    keyed = [i for i in scope if i["pred_key"]]
    tp = sum(1 for i in target if i["pred_key"] == i["gold_key"])
    p = tp / len(keyed) if keyed else 0.0
    r = tp / len(target) if target else 0.0
    new_rec = sum(1 for i in notarget if not i["pred_key"]) / len(notarget) if notarget else None
    return {"n_target": len(target), "n_tanpa_target": len(notarget), "precision": p, "recall": r, "f1": f1(p, r),
            "recall_atribut_baru": new_rec}


def run_attr(args):
    gold = {r["mapping_item_id"]: r for r in read_csv(args.gold)}
    pred = {r["mapping_item_id"]: r for r in read_csv(args.pred)}
    ran = {g["dataset_id"] for k, g in gold.items() if k in pred}  # hanya dataset yang dijalankan
    gold = {k: g for k, g in gold.items() if g["dataset_id"] in ran}
    missing = [k for k in gold if k not in pred]
    if missing:
        sys.exit("Prediksi tidak lengkap: %d butir gold tidak ada di berkas prediksi (contoh: %s)" % (len(missing), missing[0]))
    print("Dataset dinilai:", ", ".join(sorted(ran)))
    rows = []
    for k, g in gold.items():
        pr = pred[k]
        rows.append({"id": k, "group": g["dataset_id"][0], "dataset": g["dataset_id"], "gold_status": g["gold_status"],
                     "gold_key": g["gold_canonical_keys"], "pred_key": (pr.get("predicted_key") or "").strip()})
    skipped = sum(1 for r in rows if r["gold_status"] in ("AMBIGUOUS", "COMPOSITE", "EXCLUDE"))
    print("Butir dikeluarkan dari skor inti (AMBIGUOUS/COMPOSITE/EXCLUDE): %d" % skipped)
    out = []
    groups = [("SEMUA", rows)] + [(f"kelompok {g}", [r for r in rows if r["group"] == g]) for g in "RNS"]
    groups += [(d, [r for r in rows if r["dataset"] == d]) for d in sorted({r["dataset"] for r in rows})]
    for name, items in groups:
        if not items:
            continue
        m = attr_metrics(items)
        boots = bootstrap(items, attr_metrics)
        row = {"kelompok": name, **{k: v for k, v in m.items()}}
        for key in ("precision", "recall", "f1", "recall_atribut_baru"):
            lo, hi = ci([b[key] for b in boots])
            row[key + "_ci95"] = "" if lo is None else "%.3f-%.3f" % (lo, hi)
        out.append(row)
    emit(out, args.out)


# ------------------------------------------------------------------- gambar
CLASSES = ("KNOWN", "OTHER", "UNCERTAIN")


def norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def img_metrics(items):
    f1s = []
    for c in CLASSES:
        tp = sum(1 for i in items if i["gold"] == c and i["pred"] == c)
        fp = sum(1 for i in items if i["gold"] != c and i["pred"] == c)
        fn = sum(1 for i in items if i["gold"] == c and i["pred"] != c)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(f1(p, r))
    known = [i for i in items if i["gold"] == "KNOWN"]
    top1 = (sum(1 for i in known if i["pred"] == "KNOWN" and norm(i["pred_var"]) == norm(i["gold_var"])) / len(known)) if known else None
    return {"n": len(items), "n_known": len(known), "macro_f1": sum(f1s) / 3, "top1_known": top1}


def run_img(args):
    gold = {r["filename"]: r for r in read_csv(args.gold)}
    pred = {r["filename"]: r for r in read_csv(args.pred)}
    missing = [k for k in gold if k not in pred]
    if missing:
        sys.exit("Prediksi tidak lengkap: %d foto gold tidak ada di berkas prediksi (contoh: %s)" % (len(missing), missing[0]))
    rows = []
    for k, g in gold.items():
        if args.split and g.get("split") != args.split:
            continue
        pr = pred[k]
        rows.append({"gold": g["label_kind"], "gold_var": g.get("true_variety", ""), "pred": (pr.get("predicted_status") or "").strip().upper(),
                     "pred_var": pr.get("predicted_variety", ""), "cond": g.get("filename_condition", "")})
    groups = [("SEMUA", rows)] + [(f"nama file {c}", [r for r in rows if r["cond"] == c]) for c in ("NETRAL", "INFORMATIF", "MENYESATKAN")]
    out = []
    for name, items in groups:
        if not items:
            continue
        m = img_metrics(items)
        boots = bootstrap(items, img_metrics)
        row = {"kelompok": name, **m}
        for key in ("macro_f1", "top1_known"):
            lo, hi = ci([b[key] for b in boots])
            row[key + "_ci95"] = "" if lo is None else "%.3f-%.3f" % (lo, hi)
        out.append(row)
    emit(out, args.out)


def emit(rows, path):
    if not rows:
        print("tidak ada data")
        return
    cols = list(rows[0].keys())
    for r in rows:
        print(" | ".join("%s=%s" % (c, ("%.3f" % r[c]) if isinstance(r[c], float) else r[c]) for c in cols))
    if path:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print("ditulis:", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("atribut")
    a.add_argument("--gold", required=True)
    a.add_argument("--pred", required=True)
    a.add_argument("--out")
    a.set_defaults(fn=run_attr)
    g = sub.add_parser("gambar")
    g.add_argument("--gold", required=True)
    g.add_argument("--pred", required=True)
    g.add_argument("--split")
    g.add_argument("--out")
    g.set_defaults(fn=run_img)
    args = ap.parse_args()
    args.fn(args)
