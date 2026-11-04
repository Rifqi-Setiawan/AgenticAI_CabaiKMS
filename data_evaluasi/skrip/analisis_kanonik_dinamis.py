"""Analisis eksperimen F2 (skema kanonik dinamis): akuisisi, penggunaan ulang, anti duplikat, keamanan skor, stabilitas.

Dijalankan dari folder data_evaluasi setelah arsipkan_hasil.sh:
  python skrip/analisis_kanonik_dinamis.py --out hasil_eksperimen/analisis_kanonik_dinamis.md

Masukan: hasil_eksperimen/hasil_dinamis/urutan_A/rep<n>/rep1/atribut/<ID>/{mapping.csv,trace.json,meta.json,hasil_asli.xlsx},
rep<n>/rows_final.json; pembanding saklar mati: hasil_eksperimen/hasil_harness/2026-10-31/rep1/atribut/<ID>/mapping.csv
"""
import argparse
import csv
import difflib
import json
import re
from pathlib import Path

import openpyxl

ORDER = ["R01", "N07", "N09", "R02"]
BASE = Path("hasil_eksperimen/hasil_dinamis/urutan_A")  # diganti oleh --base
OFF = Path("hasil_eksperimen/hasil_harness/2026-10-31/rep1/atribut")


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", (s or "").lower())).strip()


def template_keys():
    ws = openpyxl.load_workbook("gold/gold_semua_dataset.xlsx")["Canonical Reference"]
    head = [c.value for c in ws[1]]
    i = head.index("canonical_key")
    return {r[i] for r in ws.iter_rows(min_row=2, values_only=True) if r[i]}


def f1_parts(items):
    target = [i for i in items if i["gold_status"] == "ONE_TO_ONE"]
    keyed = [i for i in items if i["gold_status"] in ("ONE_TO_ONE", "NO_MATCH") and i["pred"]]
    tp = sum(1 for i in target if i["pred"] == i["gold_key"])
    p = tp / len(keyed) if keyed else 0.0
    r = tp / len(target) if target else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="hasil_eksperimen/hasil_dinamis/urutan_A")
    a = ap.parse_args()
    global BASE
    BASE = Path(a.base)
    tkeys = template_keys()
    gold = {}
    for g in read("gold/gold_semua_dataset.csv"):
        gold.setdefault(g["dataset_id"], {})[g["source_attribute_display"].strip()] = g
    reps = sorted(p for p in BASE.glob("rep*") if (p / "rows_final.json").exists())
    out = ["# Eksperimen F2: skema kanonik dinamis (sementara; gold pra-anotasi AI)\n",
           f"Urutan run per pengulangan: {', '.join(ORDER)}; database kosong di awal tiap pengulangan; {len(reps)} pengulangan.\n"]

    # ------------------------------------------------------------ F2-1 dan F2-2 per pengulangan
    out.append("## F2-1 akuisisi dan F2-2 penggunaan ulang (per pengulangan dan dataset)\n")
    out.append("| Rep | Dataset | Atribut | Kandidat dinilai | Baris baru | Duplikat (tak ditulis) | Digabung ke baris ada | Bukan karakter | Gagal | Dipetakan ke baris akuisisi lama | Baris Excel |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    summaries = {}
    for rep in reps:
        known_ext: set[str] = set()
        for ds in ORDER:
            d = rep / "rep1" / "atribut" / ds
            if not (d / "mapping.csv").exists():
                continue
            rows = read(d / "mapping.csv")
            status = [r.get("acquisition_status", "") for r in rows]
            count = lambda k: sum(s.startswith(k) for s in status)
            reuse = sum(1 for r in rows if r["proposed_target_canonical_key"] in known_ext and not r.get("acquisition_status"))
            ws = openpyxl.load_workbook(d / "hasil_asli.xlsx").active
            new_keys = {r["proposed_target_canonical_key"] for r in rows if r.get("acquisition_status") == "NEW_ROW"}
            out.append(f"| {rep.name} | {ds} | {len(rows)} | {sum(bool(s) for s in status)} | {count('NEW_ROW')} | {count('DUPLICATE_OF')} | {count('MERGED_TO')} | "
                       f"{count('NOT_CHARACTERISTIC')} | {count('FAILED')} | {reuse} | {ws.max_row} |")
            summaries[(rep.name, ds)] = {"new": count("NEW_ROW"), "cand": sum(bool(s) for s in status), "reuse": reuse}
            known_ext |= new_keys
    out.append("")

    # ------------------------------------------------------------ F2-4 keamanan skor
    out.append("## F2-4 pengaruh pada pemetaan template (Mapping F1 terhadap gold)\n")
    out.append("Prediksi pada baris akuisisi dihitung (a) sebagai prediksi berkunci (ketat: butir NO_MATCH yang diakuisisi menjadi salah positif) dan (b) diabaikan (tampilan hanya template). Pembanding: saklar mati, pengulangan 1.\n")
    out.append("| Dataset | F1 saklar mati | F1 saklar hidup (hanya template) | selisih | F1 saklar hidup (ketat) |")
    out.append("|---|---|---|---|---|")
    for ds in ORDER:
        base_path = OFF / ds / "mapping.csv"
        if not base_path.exists():
            continue
        def items(path, only_template):
            res = []
            for r in read(path):
                g = gold.get(ds, {}).get(r["source_attribute_display"].strip())
                if not g or g["gold_status"] not in ("ONE_TO_ONE", "NO_MATCH"):
                    continue
                key = (r["proposed_target_canonical_key"] or "").strip()
                if only_template and key and key not in tkeys:
                    key = ""
                res.append({"gold_status": g["gold_status"], "gold_key": g["gold_canonical_keys"], "pred": key})
            return res
        f_off = f1_parts(items(base_path, False))[2]
        on = [f1_parts(items(rep / "rep1" / "atribut" / ds / "mapping.csv", True))[2] for rep in reps if (rep / "rep1" / "atribut" / ds / "mapping.csv").exists()]
        strict = [f1_parts(items(rep / "rep1" / "atribut" / ds / "mapping.csv", False))[2] for rep in reps if (rep / "rep1" / "atribut" / ds / "mapping.csv").exists()]
        if on:
            m_on, m_strict = sum(on) / len(on), sum(strict) / len(strict)
            out.append(f"| {ds} | {f_off:.3f} | {m_on:.3f} | {m_on - f_off:+.3f} | {m_strict:.3f} |")
    out.append("")

    # ------------------------------------------------------------ F2-3 anti duplikat
    out.append("## F2-3 anti duplikat\n")
    for rep in reps:
        rows = json.load(open(rep / "rows_final.json"))["rows"]
        labels = [r["label"] for r in rows]
        pairs = []
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                ratio = difflib.SequenceMatcher(None, norm(labels[i]), norm(labels[j])).ratio()
                if ratio >= 0.78:
                    pairs.append((round(ratio, 2), labels[i], labels[j]))
        cand = sum(v["cand"] for (r, _), v in summaries.items() if r == rep.name)
        out.append(f"- {rep.name}: {len(rows)} baris akuisisi dari {cand} kandidat atribut (tanpa penyatuan seharusnya sampai {cand} baris); pasangan label sangat mirip: {len(pairs)}")
        for p in sorted(pairs, reverse=True)[:8]:
            out.append(f"  - {p[0]}: `{p[1]}` | `{p[2]}`")
    out.append("")

    # ------------------------------------------------------------ F2-5 stabilitas
    out.append("## F2-5 stabilitas antar pengulangan\n")
    sets = []
    for rep in reps:
        rows = json.load(open(rep / "rows_final.json"))["rows"]
        sets.append({norm(r["label"]) for r in rows})
        out.append(f"- {rep.name}: {len(rows)} baris")
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            inter, union = len(sets[i] & sets[j]), len(sets[i] | sets[j])
            out.append(f"- Kemiripan label rep{i + 1} vs rep{j + 1}: Jaccard {inter / union:.2f} ({inter} dari {union})" if union else "")
    out.append("\n## Daftar baris akuisisi (pengulangan 1) untuk tinjauan kurator\n")
    if reps:
        for r in json.load(open(reps[0] / "rows_final.json"))["rows"]:
            out.append(f"- `{r['canonical_key']}` | {r['label']} | {r['domain']} | sumber: {r.get('source_label')} | run: {r.get('created_from_run', '')[:8]}")
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
