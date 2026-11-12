"""Skor desain nama file berpasangan (D23): foto yang sama, nama berkas NETRAL / BENAR / SALAH_TERDAFTAR.

Gold: data_evaluasi/gold/nama_file_berpasangan/gold_nama_file_berpasangan.csv (buat_nama_file_berpasangan.py).
Foto Indonesia varian BENAR = nama berkas asli; prediksinya dari run ulang foto 7 Nov (--ind-benar).
Per sel (set x status gold x varian):
  tindakan sesuai gold   tindakan fusi termasuk expected_fusion_boleh
  status visual benar    status model (KNOWN/OTHER/UNCERTAIN) = gold, dan varietas benar bila KNOWN
  AUTO_LINK salah        tautan otomatis ke varietas/foto yang salah (kesalahan paling berbahaya)
  ikut nama file         prediksi varietas = varietas di nama file SALAH_TERDAFTAR (model terbawa nama berkas)
Uji berpasangan (foto sama): selisih proporsi tindakan sesuai gold antarvarian, bootstrap per foto.

Jalankan dari folder data_evaluasi:
  python skrip/skor_nama_file_berpasangan.py --hasil /tmp/visi_berpasangan --ind-benar /tmp/visi_ulang/indonesia --out <folder>
"""
import argparse
import csv
import json
import random
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import buat_nama_file_berpasangan as bn  # noqa: E402

GOLD = Path("gold/nama_file_berpasangan/gold_nama_file_berpasangan.csv")
VARIAN = ("NETRAL", "BENAR", "SALAH_TERDAFTAR")
SEED, N_BOOT = 20261107, 10000


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def status(p):
    s = (p.get("status") or "").upper()
    return "OTHER" if s.startswith("CANDIDATE") else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasil", required=True)
    ap.add_argument("--ind-benar", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    gold = [g for g in read(GOLD) if g["dinilai"] == "Y"]
    # varian BENAR foto Indonesia = nama berkas asli
    for g in [g for g in gold if g["set"] == "ind6"]:
        gold.append({**g, "varian": "BENAR", "filename": g["foto_asal"].split("/")[-1], "folder": "ind_asli",
                     "hint_nama_file": g["true_variety"], "hint_terdaftar": "Y" if g["label_kind"] == "KNOWN" else "N",
                     "expected_fusion_boleh": "|".join(sorted(bn.aksi_boleh(g["label_kind"], "BENAR", True, True)))})
    pred = {}
    for f in Path(a.hasil).glob("pvt40_*/hasil_pvt40_*.csv"):
        for r in read(f):
            pred[("P01", f.parent.name, r["filename"])] = r
    for f in Path(a.hasil).glob("ind6_netral/hasil_S0*.csv"):
        for r in read(f):
            pred[(f.stem.split("_")[1], "ind6_netral", r["filename"])] = r
    for f in Path(a.ind_benar).glob("hasil_S0?.csv"):
        for r in read(f):
            pred[(f.stem.split("_")[1], "ind_asli", r["filename"])] = r

    items, hilang = [], []
    for g in gold:
        p = pred.get((g["spreadsheet"], g["folder"], g["filename"]))
        if p is None:
            hilang.append((g["spreadsheet"], g["folder"], g["filename"]))
            continue
        st, aksi = status(p), p.get("fusion_action") or ("FAILED" if p.get("status") == "FAILED" else "")
        boleh = set(g["expected_fusion_boleh"].split("|"))
        var_ok = norm(p.get("matched_variety")) == norm(g["true_variety"])
        items.append({
            "set": g["set"], "spreadsheet": g["spreadsheet"], "foto": g["foto_asal"], "varian": g["varian"],
            "filename": g["filename"], "gold": g["label_kind"], "true_variety": g["true_variety"], "hint": g["hint_nama_file"],
            "pred": st, "pred_var": p.get("matched_variety") or "", "aksi": aksi, "aksi_boleh": g["expected_fusion_boleh"],
            "aksi_ok": aksi in boleh and (aksi != "AUTO_LINK" or (g["label_kind"] == "KNOWN" and var_ok)),
            "status_ok": st == g["label_kind"] and (g["label_kind"] != "KNOWN" or var_ok),
            "auto_salah": aksi == "AUTO_LINK" and not (g["label_kind"] == "KNOWN" and var_ok),
            "ikut_nama": g["varian"] == "SALAH_TERDAFTAR" and norm(p.get("matched_variety")) == norm(g["hint_nama_file"]),
            "gagal": p.get("status") == "FAILED"})
    if hilang:
        print("PERINGATAN: prediksi tidak ada untuk", len(hilang), hilang[:3])

    sel = defaultdict(list)
    for i in items:
        sel[(i["set"], i["gold"], i["varian"])].append(i)
    frac = lambda xs, k: f"{sum(x[k] for x in xs)}/{len(xs)}"
    md = ["# Desain nama file berpasangan (D23): foto sama, nama berkas berbeda", "",
          "PVT: 40 foto kartu tertutup, registri 24 varietas P01 + deskripsi morfologi P01 (D20). Indonesia: 6 foto x "
          "spreadsheet S01-S03 (registri dan deskripsi dari sheet kanonik run bge-m3). Jalur visi = vision_hook tanpa tulis KMS.", "",
          "## 1. Per sel", "",
          "| Set | Status gold | Varian nama file | Foto | Gagal | Tindakan sesuai gold | Status visual benar | AUTO_LINK salah | "
          "Ikut nama file | Sebaran tindakan |", "|---|---|---|---|---|---|---|---|---|---|"]
    res = {"sel": {}, "berpasangan": []}
    for (s, k, v) in sorted(sel, key=lambda x: (x[0], x[1], VARIAN.index(x[2]))):
        xs = sel[(s, k, v)]
        dist = defaultdict(int)
        for x in xs:
            dist[x["aksi"] or "-"] += 1
        md.append(f"| {s} | {k} | {v} | {len(xs)} | {sum(x['gagal'] for x in xs)} | {frac(xs, 'aksi_ok')} | {frac(xs, 'status_ok')} | "
                  f"{frac(xs, 'auto_salah')} | {frac(xs, 'ikut_nama') if v == 'SALAH_TERDAFTAR' else '-'} | "
                  f"{', '.join(f'{a_} {n}' for a_, n in sorted(dist.items()))} |")
        res["sel"][f"{s}|{k}|{v}"] = {key: sum(x[key] for x in xs) for key in ("aksi_ok", "status_ok", "auto_salah", "ikut_nama", "gagal")}
        res["sel"][f"{s}|{k}|{v}"]["n"] = len(xs)

    md += ["", "## 2. Uji berpasangan (foto yang sama; selisih proporsi tindakan sesuai gold, bootstrap per foto)", "",
           "| Set | Status gold | Perbandingan | Foto berpasangan | Selisih | CI 95% |", "|---|---|---|---|---|---|"]
    by = defaultdict(dict)
    for i in items:
        by[(i["set"], i["spreadsheet"], i["foto"])][i["varian"]] = i
    rng = random.Random(SEED)
    for s in ("pvt40", "ind6"):
        for k in ("KNOWN", "OTHER"):
            for va, vb in (("BENAR", "NETRAL"), ("SALAH_TERDAFTAR", "NETRAL"), ("SALAH_TERDAFTAR", "BENAR")):
                pas = [(d[va]["aksi_ok"], d[vb]["aksi_ok"]) for key, d in by.items()
                       if key[0] == s and va in d and vb in d and d[va]["gold"] == k]
                if not pas:
                    continue
                obs = sum(x - y for x, y in pas) / len(pas)
                bs = sorted(sum(x - y for x, y in (pas[rng.randrange(len(pas))] for _ in pas)) / len(pas) for _ in range(N_BOOT))
                lo, hi = bs[int(0.025 * (N_BOOT - 1))], bs[int(0.975 * (N_BOOT - 1))]
                md.append(f"| {s} | {k} | {va} vs {vb} | {len(pas)} | {obs:+.3f} | {lo:+.3f} sampai {hi:+.3f} |")
                res["berpasangan"].append({"set": s, "gold": k, "a": va, "b": vb, "n": len(pas), "selisih": obs, "lo": lo, "hi": hi})
    tot = [i for i in items if i["set"] == "pvt40"]
    md += ["", f"Total PVT: tindakan sesuai gold {frac(tot, 'aksi_ok')}, AUTO_LINK salah {frac(tot, 'auto_salah')}.",
           "Catatan: bagian tanaman hanya memengaruhi foto berbagian tanpa baris Gambar (D21)."]
    (out / "hasil_skor.md").write_text("\n".join(md), encoding="utf-8")
    (out / "hasil_skor.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(out / "rincian.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(items[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(items)
    print("\n".join(md))


if __name__ == "__main__":
    main()
