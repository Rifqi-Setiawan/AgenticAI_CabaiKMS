"""Skor anotasi buta terhadap gold atribut: kesepakatan dan Cohen's kappa.

Contoh (dari folder data_evaluasi):
  ..\\.venv\\Scripts\\python.exe skrip\\skor_anotasi_buta.py ^
      --anotasi anotasi_buta\\subset_v1\\terisi_anotator1.xlsx

Beberapa berkas --anotasi boleh diberikan (mis. dua anotator); kappa antar anotator ikut dihitung.

Definisi:
  Himpunan gold G: NO_MATCH -> {NO_MATCH}; ONE_TO_ONE/COMPOSITE -> gold_canonical_keys;
                   AMBIGUOUS -> ambiguous_candidate_canonical_keys (ditambah gold_canonical_keys bila ada).
  Himpunan anotator H: NO_MATCH -> {NO_MATCH}; lainnya -> kunci_utama + kunci_lain.
  Sepakat ketat  : status sama DAN himpunan kunci sama.
  Sepakat longgar: kunci_utama anotator ada di G (NO_MATCH dianggap kunci), mengikuti cara skor sistem
                   yang menerima kandidat AMBIGUOUS.
  Kappa longgar  : kappa Cohen atas label tunggal; label anotator disamakan dengan label gold bila sepakat longgar.
  Kappa ketat    : kappa Cohen atas label lengkap (status + himpunan kunci).
  Kappa biner    : dipetakan vs NO_MATCH.
  EXCLUDE dan butir kosong tidak dihitung (dilaporkan jumlahnya).
  Estimasi seluruh gold: rata-rata tertimbang strata (prioritas 57/318, acak 261/318) dengan
  bootstrap terstratifikasi 5000 ulangan.
"""
import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

SEED = 20261102
BOOT = 5000


def split_keys(v) -> set:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return set()
    return {k.strip() for k in str(v).replace(",", "|").replace(";", "|").split("|") if k.strip()}


def gold_set(r) -> frozenset:
    if r.gold_status == "NO_MATCH":
        return frozenset({"NO_MATCH"})
    keys = split_keys(r.gold_canonical_keys)
    if r.gold_status == "AMBIGUOUS":
        keys |= split_keys(r.ambiguous_candidate_canonical_keys)
    return frozenset(keys)


def gold_label(r) -> str:
    return r.gold_status + ":" + "|".join(sorted(gold_set(r)))


def cohen_kappa(a, b) -> float:
    a, b = list(a), list(b)
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)


def tafsir(k: float) -> str:
    if np.isnan(k):
        return "-"
    for batas, teks in [(0, "buruk"), (0.2, "sangat lemah"), (0.4, "lemah"), (0.6, "sedang"), (0.8, "kuat")]:
        if k <= batas:
            return teks
    return "hampir sempurna"


def read_annotation(path: Path) -> pd.DataFrame:
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["Anotasi"]
    rows = list(ws.iter_rows(values_only=True))
    a = pd.DataFrame(rows[1:], columns=rows[0])
    a = a[a.id_butir.notna()].copy()
    a["status"] = a.status.fillna("").astype(str).str.strip().str.upper()
    a["kunci_utama"] = a.kunci_utama.fillna("").astype(str).str.strip()
    a["H"] = [
        frozenset({"NO_MATCH"}) if s == "NO_MATCH" else frozenset(({u} if u else set()) | split_keys(l))
        for s, u, l in zip(a.status, a.kunci_utama, a.kunci_lain)
    ]
    a["primer"] = ["NO_MATCH" if s == "NO_MATCH" else u for s, u in zip(a.status, a.kunci_utama)]
    a["label_ketat"] = [s + ":" + "|".join(sorted(h)) for s, h in zip(a.status, a.H)]
    nama = a.nama_anotator.dropna().astype(str)
    a.attrs["nama"] = nama.iloc[0] if len(nama) else path.stem
    return a


def score(a: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    d = a.merge(ref, on="id_butir", how="left", validate="one_to_one")
    assert d.mapping_item_id.notna().all(), "id_butir tidak ada di kunci"
    d["G"] = [gold_set(r) for r in d.itertuples()]
    d["label_gold"] = [gold_label(r) for r in d.itertuples()]
    d["sepakat_ketat"] = [(s == g) and (h == gs) for s, g, h, gs in zip(d.status, d.gold_status, d.H, d.G)]
    d["sepakat_longgar"] = [p in gs for p, gs in zip(d.primer, d.G)]
    d["biner_anotator"] = np.where(d.status == "NO_MATCH", "NO_MATCH", "PETAKAN")
    d["biner_gold"] = np.where(d.gold_status == "NO_MATCH", "NO_MATCH", "PETAKAN")
    d["label_anotator_longgar"] = np.where(d.sepakat_longgar, d.label_gold, "ANOT:" + d.primer)
    return d


def boot_weighted(d: pd.DataFrame, col: str, w: dict) -> tuple:
    rng = np.random.default_rng(SEED)
    parts = {s: d.loc[d.stratum == s, col].to_numpy(dtype=float) for s in w}
    est = sum(w[s] * parts[s].mean() for s in w if len(parts[s]))
    sims = []
    for _ in range(BOOT):
        sims.append(sum(w[s] * rng.choice(parts[s], len(parts[s])).mean() for s in w if len(parts[s])))
    lo, hi = np.percentile(sims, [2.5, 97.5])
    return est, lo, hi


def metrics_row(nama: str, d: pd.DataFrame) -> list:
    kl = cohen_kappa(d.label_anotator_longgar, d.label_gold)
    kk = cohen_kappa(d.label_ketat, d.label_gold)
    kb = cohen_kappa(d.biner_anotator, d.biner_gold)
    return [nama, len(d), f"{d.sepakat_longgar.mean():.3f}", f"{d.sepakat_ketat.mean():.3f}",
            f"{kl:.3f} ({tafsir(kl)})", f"{kk:.3f}", f"{kb:.3f} ({tafsir(kb)})"]


def md(rows, head) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anotasi", nargs="+", required=True)
    ap.add_argument("--kunci", default="anotasi_buta/subset_v1/kunci_subset.csv")
    ap.add_argument("--gold", default="gold/final/gold_semua_dataset_final.csv")
    ap.add_argument("--bobot-prioritas", type=float, default=57 / 318)
    ap.add_argument("--out", default="anotasi_buta/subset_v1/hasil")
    args = ap.parse_args()

    kunci = pd.read_csv(args.kunci)
    gold = pd.read_csv(args.gold)
    ref = kunci.merge(
        gold[["mapping_item_id", "source_attribute_display", "contoh_nilai_sumber", "gold_status",
              "gold_canonical_keys", "ambiguous_candidate_canonical_keys"]],
        on="mapping_item_id", how="left", validate="one_to_one")
    w = {"prioritas": args.bobot_prioritas, "acak": 1 - args.bobot_prioritas}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    lines = ["# Hasil anotasi buta terhadap gold atribut", "",
             "Gold = `ai_assisted_human_verified_v1`. Definisi metrik ada di docstring `skrip/skor_anotasi_buta.py`.", ""]
    head = ["Himpunan", "n", "Sepakat longgar", "Sepakat ketat", "Kappa longgar", "Kappa ketat", "Kappa biner"]
    scored = {}
    for p in args.anotasi:
        a = read_annotation(Path(p))
        nama = a.attrs["nama"]
        kosong = int((a.status == "").sum())
        excl = int((a.status == "EXCLUDE").sum())
        d = score(a[(a.status != "") & (a.status != "EXCLUDE")], ref)
        scored[nama] = d
        rows = [metrics_row("Semua subset", d)]
        for s in ["prioritas", "acak"]:
            rows.append(metrics_row(s.capitalize(), d[d.stratum == s]))
        est, lo, hi = boot_weighted(d, "sepakat_longgar", w)
        estk, lok, hik = boot_weighted(d, "sepakat_ketat", w)
        lines += [f"## Anotator: {nama}", "",
                  f"Berkas `{p}`. Kosong: {kosong}; EXCLUDE: {excl}; dinilai: {len(d)}.", "",
                  md(rows, head), "",
                  f"**Estimasi kesepakatan untuk seluruh gold (318 butir, tertimbang strata):** "
                  f"longgar {est:.3f} (CI 95% {lo:.3f} sampai {hi:.3f}); ketat {estk:.3f} ({lok:.3f} sampai {hik:.3f}).", ""]
        if d.yakin.notna().any():
            yk = d.groupby(d.yakin.fillna("-"))["sepakat_longgar"].agg(["size", "mean"])
            lines += ["Kesepakatan longgar menurut keyakinan anotator:", "",
                      md([[i, int(r["size"]), f"{r['mean']:.3f}"] for i, r in yk.iterrows()], ["yakin", "n", "sepakat"]), ""]
        cm = pd.crosstab(d.biner_gold, d.biner_anotator)
        lines += ["Matriks biner (baris gold, kolom anotator):", "",
                  md([[i, *r] for i, r in zip(cm.index, cm.values)], ["gold \\ anotator", *cm.columns]), ""]

        beda = d[~d.sepakat_longgar | ~d.sepakat_ketat].copy()
        beda["jenis"] = np.where(~beda.sepakat_longgar, "beda", "beda status/kunci tambahan saja")
        cols = ["id_butir", "dataset_id", "stratum", "jenis", "source_attribute_display", "contoh_nilai_sumber",
                "gold_status", "gold_canonical_keys", "ambiguous_candidate_canonical_keys",
                "status", "kunci_utama", "kunci_lain", "yakin", "catatan"]
        beda[cols].sort_values(["jenis", "id_butir"]).assign(keputusan_adjudikasi="", alasan="").to_excel(
            out / f"ketidaksepakatan_{nama.replace(' ', '_')}.xlsx", index=False)

    if len(scored) >= 2:
        names = list(scored)
        lines += ["## Antar anotator", ""]
        rows = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                x = scored[names[i]][["id_butir", "primer", "label_ketat", "biner_anotator"]]
                y = scored[names[j]][["id_butir", "primer", "label_ketat", "biner_anotator"]]
                m = x.merge(y, on="id_butir")
                rows.append([f"{names[i]} vs {names[j]}", len(m),
                             f"{(m.primer_x == m.primer_y).mean():.3f}",
                             f"{cohen_kappa(m.primer_x, m.primer_y):.3f}",
                             f"{cohen_kappa(m.label_ketat_x, m.label_ketat_y):.3f}",
                             f"{cohen_kappa(m.biner_anotator_x, m.biner_anotator_y):.3f}"])
        lines += [md(rows, ["Pasangan", "n", "Sepakat label utama", "Kappa label utama", "Kappa ketat", "Kappa biner"]), ""]

    lines += ["Catatan: strata prioritas berisi butir yang sengaja sulit, jadi kesepakatannya diharapkan lebih rendah;",
              "angka untuk seluruh gold memakai bobot populasi, bukan rata-rata subset.",
              "Kappa: <=0,20 sangat lemah, 0,21-0,40 lemah, 0,41-0,60 sedang, 0,61-0,80 kuat, >0,80 hampir sempurna (Landis & Koch)."]
    (out / "laporan_kappa.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
