"""Rekap beberapa ulangan run foto D24: rerata, simpangan baku, rentang, dan kestabilan jawaban per foto.

Masukan per ulangan = folder keluaran skor.sh (berisi foto/ dan berpasangan/ dari skor_foto_ulang.py dan
skor_nama_file_berpasangan.py). Pembanding opsional = skor D23 (satu run) dengan struktur yang sama.

  python skrip/rekap_ulangan_m2.py --ulangan skorA skorB skorC --pembanding-foto <D23 foto skor> \
      --pembanding-berpasangan <D23 berpasangan skor> --out <folder>
"""
import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def muat(d):
    d = Path(d)
    foto = json.loads((d / "foto" / "hasil_skor.json").read_text(encoding="utf-8")) if (d / "foto").exists() else \
        json.loads((d / "hasil_skor.json").read_text(encoding="utf-8"))
    return foto


def muat_bp(d):
    return json.loads((Path(d) / "hasil_skor.json").read_text(encoding="utf-8"))


def gab_indonesia(g):
    b = sum(g[k]["gabungan"]["benar"] for k in ("S01", "S02", "S03"))
    s = sum(g[k]["gabungan"]["salah_tulis"] for k in ("S01", "S02", "S03"))
    t = sum(g[k]["gabungan"]["terlewat"] for k in ("S01", "S02", "S03"))
    p, r = b / (b + s), b / (b + t)
    return 2 * p * r / (p + r)


def metrik_foto(f):
    m = {}
    for s, lab in (("commons35", "Commons"), ("indonesia_S01-S03", "Indonesia S01-S03"),
                   ("pvt40_terlihat", "PVT kartu terlihat"), ("pvt40_tertutup", "PVT kartu tertutup")):
        x = f["foto"][s]
        m[f"{lab}: status benar (dari {x['n']})"] = x["status_benar"]
        m[f"{lab}: Top-1 KNOWN"] = x["top1"]
        m[f"{lab}: macro-F1 kelas gold"] = x["macro_f1_ada"]
        al = x["auto_link"]
        m[f"{lab}: AUTO_LINK benar / total"] = f"{al[0]}/{al[1]}"
        m[f"{lab}: AUTO_LINK salah"] = al[1] - al[0]
    m["Workbook gabungan Indonesia F1"] = gab_indonesia(f["gabungan"])
    m["Workbook P01+PVT terlihat F1"] = f["gabungan"]["P01+pvt40_terlihat"]["gabungan"]["f1"]
    m["Workbook P01+PVT tertutup F1"] = f["gabungan"]["P01+pvt40_tertutup"]["gabungan"]["f1"]
    return m


def metrik_bp(b):
    c = b["sel"]
    m = {}
    sal = [c["pvt40|KNOWN|SALAH_TERDAFTAR"], c["pvt40|OTHER|SALAH_TERDAFTAR"]]
    m["PVT nama salah: ikut nama berkas (dari 40)"] = sum(x["ikut_nama"] for x in sal)
    m["PVT nama salah: tindakan sesuai gold / REVIEW_MISMATCH benar (dari 40)"] = sum(x["aksi_ok"] for x in sal)
    m["PVT nama salah: AUTO_LINK salah"] = sum(x["auto_salah"] for x in sal)
    pvt = [v for k, v in c.items() if k.startswith("pvt40|")]
    m["PVT berpasangan: tindakan sesuai gold (dari 120)"] = sum(x["aksi_ok"] for x in pvt)
    m["PVT berpasangan: AUTO_LINK salah (dari 120)"] = sum(x["auto_salah"] for x in pvt)
    for k in ("pvt40|KNOWN|NETRAL", "pvt40|KNOWN|BENAR", "pvt40|OTHER|BENAR"):
        m[f"{k.replace('pvt40|', 'PVT ').replace('|', ' ')}: status benar (dari {c[k]['n']})"] = c[k]["status_ok"]
        m[f"{k.replace('pvt40|', 'PVT ').replace('|', ' ')}: tindakan sesuai gold"] = c[k]["aksi_ok"]
    return m


def fmt(v):
    return f"{v:.3f}".replace(".", ",") if isinstance(v, float) else str(v)


def ringkas(vals):
    if isinstance(vals[0], str):
        return "-", "-", "-"
    mean = st.mean(vals)
    sd = st.stdev(vals) if len(vals) > 1 else 0.0
    d = 3 if isinstance(vals[0], float) else 2
    return f"{mean:.{d}f}".replace(".", ","), f"{sd:.{d}f}".replace(".", ","), \
        f"{fmt(min(vals))}-{fmt(max(vals))}"


def kestabilan(dirs, rel, key_cols, val_cols):
    per = defaultdict(list)
    for d in dirs:
        with open(Path(d) / rel, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                per[tuple(r[c] for c in key_cols)].append(tuple(r[c] for c in val_cols))
    lengkap = [v for v in per.values() if len(v) == len(dirs)]
    sama = sum(1 for v in lengkap if len(set(v)) == 1)
    return sama, len(lengkap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ulangan", nargs="+", required=True)
    ap.add_argument("--pembanding-foto")
    ap.add_argument("--pembanding-berpasangan")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    reps = a.ulangan
    mf = [metrik_foto(muat(d)) for d in reps]
    mb = [metrik_bp(muat_bp(Path(d) / "berpasangan")) for d in reps]
    pf = metrik_foto(muat(a.pembanding_foto)) if a.pembanding_foto else {}
    pb = metrik_bp(muat_bp(a.pembanding_berpasangan)) if a.pembanding_berpasangan else {}

    lines = [f"# Ulangan run foto D24 (visi dua tahap): {len(reps)} ulangan", "",
             "Input, registri, deskripsi varietas, kanonik, dan varietas DB sama di semua ulangan; skrip skor sama. "
             "Kolom D23 = satu run 7 Nov (nama berkas di prompt). Rerata dan SB dihitung antar ulangan "
             "(variasi model, bukan ketidakpastian sampel).", ""]
    rows_json = {}
    for title, ms, pv in (("Nama file berpasangan (PVT kartu tertutup, 40 foto x 3 nama)", mb, pb),
                          ("Foto dan workbook gabungan", mf, pf)):
        lines += [f"## {title}", "", "| Metrik | " + " | ".join(f"Ulangan {i+1}" for i in range(len(reps))) +
                  " | Rerata | SB | Rentang | D23 |", "|---|" + "---|" * (len(reps) + 4)]
        for k in ms[0]:
            vals = [m[k] for m in ms]
            mean, sd, rng = ringkas(vals)
            lines.append(f"| {k} | " + " | ".join(fmt(v) for v in vals) + f" | {mean} | {sd} | {rng} | {fmt(pv[k]) if k in pv else '-'} |")
            rows_json[k] = {"ulangan": vals, "d23": pv.get(k)}
        lines.append("")

    s1, n1 = kestabilan(reps, "foto/rincian_foto.csv", ("set", "foto"), ("pred", "pred_varietas", "aksi"))
    s2, n2 = kestabilan(reps, "berpasangan/rincian.csv", ("set", "spreadsheet", "foto", "varian"), ("pred", "pred_var", "aksi"))
    lines += ["## Kestabilan jawaban per foto", "",
              f"- Foto ulang (Commons, Indonesia, PVT 2 kondisi): status, varietas, dan tindakan sama di semua ulangan pada "
              f"{s1}/{n1} keputusan ({100 * s1 / n1:.1f}%).".replace(".", ",", 1),
              f"- Nama file berpasangan: sama di semua ulangan pada {s2}/{n2} keputusan ({100 * s2 / n2:.1f}%).".replace(".", ",", 1), ""]
    (out / "rekap_ulangan.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "rekap_ulangan.json").write_text(json.dumps({"ulangan": reps, "metrik": rows_json,
                                                        "kestabilan": {"foto": [s1, n1], "berpasangan": [s2, n2]}},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
