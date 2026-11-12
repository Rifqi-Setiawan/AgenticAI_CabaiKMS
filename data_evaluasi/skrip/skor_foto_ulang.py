"""Skor run ulang foto dan workbook gabungan (7 Nov 2026; data bersih D19, kode D20, embedding bge-m3 D22).

Prediksi: hasil uji_visi_commons_vps.py (jalur vision_hook tanpa tulis KMS) di <hasil>/hasil_<label>.csv.
Set foto dan gold:
  commons35   35 foto Commons, registri = spreadsheet_varietas_terdaftar.xlsx (Hungarian Wax).
              Gold: gambar/manifest/gold_gambar_manifest_final.csv + gold/bagian_foto_commons/gold_bagian_commons.csv.
  S01-S03     6 foto Indonesia, registri + deskripsi dari sheet kanonik run atribut bge-m3 (I_atribut_bge-m3_39f4213).
              Gold: gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv (status per spreadsheet; dinilai = Y).
  pvt40_*     uji 40 foto PVT (kartu terlihat / tertutup), registri + deskripsi dari sheet kanonik run P01 (24 varietas).
              Gold: gambar/manifest/gold_kanonik_foto_pvt.csv (skenario P01; bagian terverifikasi).
Metrik foto (definisi sama dengan analisis_paper.py / skor_foto_grin.py): status benar, macro-F1 tiga kelas
(KNOWN/OTHER/UNCERTAIN) dan macro-F1 kelas yang ada di gold, Top-1 varietas foto KNOWN, recall OTHER, foto non-KNOWN
yang dipaksa KNOWN, AUTO_LINK benar (gold KNOWN dan varietas benar) per kondisi nama file, bagian tanaman benar
(prediksi di bagian_boleh), dan tindakan fusi sesuai gold (Commons expected_fusion; PVT fusion_boleh, REVIEW = REVIEW_*).
Workbook gabungan (definisi skor_workbook_gabungan.py): unit = sel atribut (akurasi_sel.py mode ketat) + tautan foto.
Tautan benar = foto gold KNOWN, kolom varietas benar, baris Gambar sesuai bagian yang diperbolehkan.

Jalankan dari folder data_evaluasi:
  python skrip/skor_foto_ulang.py --hasil <folder hasil run> --atribut <folder I_atribut...> --p01 <hasil_asli P01> --out <folder>
"""
import argparse
import csv
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import akurasi_sel as asl  # noqa: E402

KELAS = ("KNOWN", "OTHER", "UNCERTAIN")
BAGIAN4 = {"DAUN", "BATANG", "BUAH", "BUNGA"}
BOLEH_IND = {"TANGKAI DAUN": {"DAUN", "BATANG"}}
SEED, N_BOOT = 20261107, 5000


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def urai(teks):
    return {t.strip().upper() for t in re.split(r"[|,;]", teks or "") if t.strip()}


def butir(pred_rows, gold_by_fn):
    out = []
    for p in pred_rows:
        g = gold_by_fn.get(norm(p["filename"]))
        if g is None or not g["dinilai"]:
            continue
        st = (p.get("status") or "").upper()
        if st.startswith("CANDIDATE"):
            st = "OTHER"
        out.append({**g, "fn": p["filename"], "pred": st, "pred_var": p.get("matched_variety") or "",
                    "pred_part": (p.get("identified_part") or "").upper(), "aksi": p.get("fusion_action") or "",
                    "galat": p.get("galat") or ""})
    return out


def benar(i):
    return i["pred"] == i["gold"] and (i["gold"] != "KNOWN" or norm(i["pred_var"]) == norm(i["gold_var"]))


def macro(xs, kelas):
    f1s = []
    for c in kelas:
        tp = sum(1 for i in xs if i["gold"] == c and i["pred"] == c)
        fp = sum(1 for i in xs if i["gold"] != c and i["pred"] == c)
        fn = sum(1 for i in xs if i["gold"] == c and i["pred"] != c)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def top1(xs):
    k = [i for i in xs if i["gold"] == "KNOWN"]
    return sum(1 for i in k if i["pred"] == "KNOWN" and norm(i["pred_var"]) == norm(i["gold_var"])) / len(k) if k else None


def ci(xs, fn):
    rng = random.Random(SEED)
    v = sorted((fn([xs[rng.randrange(len(xs))] for _ in xs]) or 0.0) for _ in range(N_BOOT))
    return v[int(0.025 * (N_BOOT - 1))], v[int(0.975 * (N_BOOT - 1))]


def ringkas(xs):
    ada = sorted({i["gold"] for i in xs})
    nonk = [i for i in xs if i["gold"] != "KNOWN"]
    oth = [i for i in xs if i["gold"] == "OTHER"]
    al = [i for i in xs if i["aksi"] == "AUTO_LINK"]
    bag = [i for i in xs if i["boleh"] & BAGIAN4]
    fus = [i for i in xs if i.get("fusi_boleh")]
    r = {"n": len(xs), "gagal": sum(1 for i in xs if i["pred"] == "FAILED"),
         "status_benar": sum(benar(i) for i in xs),
         "macro_f1_3": macro(xs, KELAS), "macro_f1_ada": macro(xs, ada), "kelas_gold": ada,
         "mf1_ci": ci(xs, lambda s: macro(s, ada)),
         "n_known": sum(i["gold"] == "KNOWN" for i in xs), "top1": top1(xs),
         "top1_ci": ci(xs, top1) if any(i["gold"] == "KNOWN" for i in xs) else None,
         "other_recall": (sum(i["pred"] == "OTHER" for i in oth), len(oth)),
         "dipaksa_known": (sum(i["pred"] == "KNOWN" for i in nonk), len(nonk)),
         "auto_link": (sum(1 for i in al if i["gold"] == "KNOWN" and benar(i)), len(al)),
         "bagian": (sum(1 for i in bag if i["pred_part"] in i["boleh"]), len(bag)),
         "fusi": (sum(1 for i in fus if i["aksi"] in i["fusi_boleh"]), len(fus)),
         "aksi": {a: sum(1 for i in xs if i["aksi"] == a) for a in sorted({i["aksi"] for i in xs})}}
    r["auto_per_kondisi"] = {}
    for c in sorted({i.get("kondisi", "") for i in xs}):
        s = [i for i in al if i.get("kondisi", "") == c]
        r["auto_per_kondisi"][c] = (sum(1 for i in s if i["gold"] == "KNOWN" and benar(i)), len(s))
    return r


# ------------------------------------------------------------------------------------------------- gold
def gold_commons():
    bag = {norm(r["filename"]): r for r in read("gold/bagian_foto_commons/gold_bagian_commons.csv")}
    out = {}
    for g in read("gambar/manifest/gold_gambar_manifest_final.csv"):
        b = bag.get(norm(g["filename"]), {})
        out[norm(g["filename"])] = {"gold": g["label_kind"], "gold_var": g["true_variety"] if g["label_kind"] == "KNOWN" else "",
                                    "var": g["true_variety"], "kondisi": g["filename_condition"], "dinilai": True,
                                    "boleh": urai(b.get("bagian_boleh") or b.get("bagian_utama")),
                                    "fusi_boleh": {g["expected_fusion"]} if g["expected_fusion"] else set()}
    return out


def gold_indonesia(run):
    out = {}
    for g in read("gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv"):
        if g["spreadsheet"] != run:
            continue
        boleh = urai(g.get("bagian_boleh")) or BOLEH_IND.get(g["bagian"], {g["bagian"]})
        out[norm(g["filename"])] = {"gold": g["expected_status"], "gold_var": g.get("expected_variety") or "",
                                    "var": g["varietas_atau_jenis"], "kondisi": "INDONESIA", "dinilai": g["dinilai"] == "Y",
                                    "boleh": boleh, "fusi_boleh": set()}
    return out


def gold_pvt(pembagian):
    kan = {r["berkas"].split("/")[-1]: r for r in read("gambar/manifest/gold_kanonik_foto_pvt.csv")}
    out = {}
    for p in read(pembagian):
        g = kan[p["berkas_sumber"].split("/")[-1]]
        fus = set()
        for a in g["fusion_boleh"].split("|"):
            fus |= {"REVIEW_UNCERTAIN", "REVIEW_MISMATCH"} if a == "REVIEW" else {a}
        out[norm(p["filename"].rsplit(".", 1)[0])] = {
            "gold": g["label_kind_skenario_P01"], "gold_var": g["true_variety"] if g["label_kind_skenario_P01"] == "KNOWN" else "",
            "var": g["true_variety"], "kondisi": "NETRAL", "dinilai": g["dinilai_kanonik"] == "Y",
            "boleh": urai(g["bagian_boleh"]), "fusi_boleh": fus, "sumber_bagian": g["annotation_source_part"]}
    return out


# --------------------------------------------------------------------------------------------- gabungan
def sel(ds, path):
    lab2key = asl.kunci_baris()
    gold = list(csv.DictReader(open(asl.GOLD, encoding="utf-8-sig")))
    if ds == "P01":
        gold = list(csv.DictReader(open("gold/gold_P01_P02_pvt.csv", encoding="utf-8-sig")))
    kunci = asl.bangun_kunci(gold)[ds]
    r, _ = asl.nilai(ds, kunci, asl.baca_keluaran(path, lab2key))
    return r["ketat"]


def tautan(xs):
    """Tautan foto dari baris AUTO_LINK (sama dengan link yang ditulis vision_hook ke baris Gambar)."""
    b = s = 0
    ok_fn = set()
    for i in xs:
        if i["aksi"] != "AUTO_LINK":
            continue
        if i["gold"] == "KNOWN" and norm(i["pred_var"]) == norm(i["gold_var"]) and i["pred_part"] in i["boleh"]:
            b += 1
            ok_fn.add(norm(i["fn"]))
        else:
            s += 1
    harap = [i for i in xs if i["gold"] == "KNOWN" and i["boleh"] & BAGIAN4]
    return {"benar": b, "salah_tulis": s, "harapan": len(harap), "terlewat": sum(1 for i in harap if norm(i["fn"]) not in ok_fn)}


def prf(b, s, t):
    p = b / (b + s) if b + s else 0.0
    r = b / (b + t) if b + t else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasil", required=True)
    ap.add_argument("--atribut", required=True, help="folder I_atribut_bge-m3_* (S0x_*/hasil_kanonik.xlsx)")
    ap.add_argument("--p01", required=True, help="hasil_asli.xlsx run atribut P01")
    ap.add_argument("--pembagian-pvt", default="../dataset_eksperimen/2_input_foto/pvt_uji_40/pembagian_uji_40.csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    H, out = Path(a.hasil), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    asl.SUMBER.pop("R01", None)  # R01 dikeluarkan (D19)
    asl.SUMBER["P01"] = ("P01_pvt_hasil_pemuliaan_24.xlsx", "Deskripsi Varietas", "row", 1, 0)
    asl.SRC = Path("inputs").resolve()

    sets = {"commons35": (H / "commons" / "hasil_commons35.csv", gold_commons())}
    for run in ("S01", "S02", "S03"):
        sets[run] = (H / "indonesia" / f"hasil_{run}.csv", gold_indonesia(run))
    gp = gold_pvt(a.pembagian_pvt)
    for k in ("terlihat", "tertutup"):
        sets[f"pvt40_{k}"] = (H / f"pvt_{k}" / f"hasil_pvt40_{k}.csv", {f: dict(v) for f, v in gp.items()})
    res, rinci = {}, []
    for lab, (pred, gold) in sets.items():
        rows = read(pred)
        if lab.startswith("pvt40"):
            for r in rows:
                r["filename"] = r["filename"].rsplit(".", 1)[0]
        xs = butir(rows, gold)
        res[lab] = ringkas(xs)
        rinci += [{"set": lab, "foto": i["fn"], "gold": i["gold"], "varietas_gold": i["var"], "pred": i["pred"],
                   "pred_varietas": i["pred_var"], "pred_bagian": i["pred_part"], "bagian_boleh": "|".join(sorted(i["boleh"])),
                   "aksi": i["aksi"], "aksi_boleh": "|".join(sorted(i["fusi_boleh"])), "status_benar": benar(i)} for i in xs]
        res[lab]["_xs"] = xs
    ind = [i for r in ("S01", "S02", "S03") for i in res[r]["_xs"]]
    res["indonesia_S01-S03"] = ringkas(ind)

    # workbook gabungan
    gab = {}
    for run, d in (("S01", "S01_D01_transposed"), ("S02", "S02_D02_english"), ("S03", "S03_D03_bertingkat")):
        c = sel(run, Path(a.atribut) / d / "hasil_kanonik.xlsx")
        t = tautan(res[run]["_xs"])
        gab[run] = {"sel": c, "foto": t}
    c = sel("P01", Path(a.p01))
    for k in ("terlihat", "tertutup"):
        gab[f"P01+pvt40_{k}"] = {"sel": c, "foto": tautan(res[f"pvt40_{k}"]["_xs"])}

    f3 = lambda v: "-" if v is None else f"{v:.3f}"
    frac = lambda t: f"{t[0]}/{t[1]}" + (f" = {t[0] / t[1]:.3f}" if t[1] else "")
    md = ["# Run ulang foto dan workbook gabungan (7 Nov 2026)", "",
          "Data bersih D19, kode visi D20 (deskripsi varietas dari sheet kanonik run), embedding bge-m3 (D22). Jalur visi = "
          "vision_hook tanpa tulis KMS (uji_visi_commons_vps.py). Definisi metrik: docstring skrip/skor_foto_ulang.py.", "",
          "## 1. Klasifikasi foto", "",
          "| Set | Foto dinilai | Gagal | Status benar | Macro-F1 kelas gold (CI 95%) | Macro-F1 3 kelas | Top-1 KNOWN (CI 95%) | "
          "Recall OTHER | Non-KNOWN dipaksa KNOWN | AUTO_LINK benar | Bagian benar | Tindakan fusi sesuai gold |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for lab, r in res.items():
        tci = "-" if r["top1_ci"] is None else f"{r['top1_ci'][0]:.3f}-{r['top1_ci'][1]:.3f}"
        md.append(f"| {lab} | {r['n']} | {r['gagal']} | {r['status_benar']}/{r['n']} | {f3(r['macro_f1_ada'])} "
                  f"({r['mf1_ci'][0]:.3f}-{r['mf1_ci'][1]:.3f}) | {f3(r['macro_f1_3'])} | {f3(r['top1'])} ({tci}) | "
                  f"{frac(r['other_recall'])} | {frac(r['dipaksa_known'])} | {frac(r['auto_link'])} | {frac(r['bagian'])} | "
                  f"{frac(r['fusi']) if r['fusi'][1] else '-'} |")
    md += ["", "Tindakan fusi per set: " + "; ".join(f"{k}: {r['aksi']}" for k, r in res.items()), "",
           "AUTO_LINK benar per kondisi nama file (Commons): " +
           ", ".join(f"{c} {frac(v)}" for c, v in res["commons35"]["auto_per_kondisi"].items()), "",
           "## 2. Workbook gabungan (sel atribut + tautan foto)", "",
           "| Run | Sel P / R / F1 | Tautan foto benar / salah / terlewat (harapan) | Gabungan P / R / F1 |", "|---|---|---|---|"]
    for run, g in gab.items():
        c, t = g["sel"], g["foto"]
        pc = prf(c["benar"], c["salah_tulis"], c["terlewat"])
        b, s_, tl = c["benar"] + t["benar"], c["salah_tulis"] + t["salah_tulis"], c["terlewat"] + t["terlewat"]
        pg = prf(b, s_, tl)
        g["gabungan"] = {"benar": b, "salah_tulis": s_, "terlewat": tl, "precision": pg[0], "recall": pg[1], "f1": pg[2]}
        md.append(f"| {run} | {pc[0]:.3f} / {pc[1]:.3f} / {pc[2]:.3f} | {t['benar']} / {t['salah_tulis']} / {t['terlewat']} "
                  f"({t['harapan']}) | {pg[0]:.3f} / {pg[1]:.3f} / {pg[2]:.3f} |")
    tot = {k: sum(gab[r]["gabungan"][k] for r in ("S01", "S02", "S03")) for k in ("benar", "salah_tulis", "terlewat")}
    pt = prf(tot["benar"], tot["salah_tulis"], tot["terlewat"])
    md += [f"| Indonesia S01-S03 total | | | {pt[0]:.3f} / {pt[1]:.3f} / {pt[2]:.3f} |", "",
           "Catatan: gold atribut dan kunci sel P01 belum diverifikasi. Commons hanya punya 7 foto KNOWN (registri 1 varietas)."]
    for r in res.values():
        r.pop("_xs", None)
    (out / "hasil_skor.md").write_text("\n".join(md), encoding="utf-8")
    (out / "hasil_skor.json").write_text(json.dumps({"foto": res, "gabungan": gab}, indent=1, ensure_ascii=False, default=list),
                                         encoding="utf-8")
    with open(out / "rincian_foto.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rinci[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rinci)
    print("\n".join(md))


if __name__ == "__main__":
    main()
