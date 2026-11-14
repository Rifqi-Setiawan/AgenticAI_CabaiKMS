"""Presisi jawaban KNOWN (tanpa ambang AUTO_LINK) dari rincian_foto.csv, per set dan total."""
import csv, sys
from collections import defaultdict
for spec in sys.argv[1:]:
    nama, path = spec.split("=")
    t = defaultdict(lambda: [0, 0, 0, 0])  # known_gold, pred_known, pred_known_benar, pred_known_pada_other
    for r in csv.DictReader(open(path, encoding="utf-8")):
        s = r["set"]
        for k in (s, "TOTAL"):
            x = t[k]
            x[0] += r["gold"] == "KNOWN"
            if r["pred"] == "KNOWN":
                x[1] += 1
                x[2] += r["gold"] == "KNOWN" and r["pred_varietas"] == r["varietas_gold"]
                x[3] += r["gold"] != "KNOWN"
    print(f"== {nama}")
    for k, (g, p, b, o) in sorted(t.items()):
        print(f"  {k:18s} gold KNOWN {g:3d} | jawab KNOWN {p:3d} | benar {b:3d} (presisi {b/p if p else 0:.2f}, recall {b/g if g else 0:.2f}) | KNOWN padahal bukan {o}")
