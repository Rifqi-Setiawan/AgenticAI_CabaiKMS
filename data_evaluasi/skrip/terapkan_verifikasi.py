"""Terapkan hasil verifikasi reviewer menjadi gold final.

Pemakaian (dari folder data_evaluasi):
  python skrip/terapkan_verifikasi.py --atribut verifikasi_gold/verifikasi_atribut.xlsx --foto verifikasi_gold/verifikasi_foto.xlsx

Keluaran:
  gold/final/gold_semua_dataset_final.csv        (format sama dengan gold_semua_dataset.csv, tanpa kolom bantu usulan)
  gambar/manifest/gold_gambar_manifest_final.csv (format sama dengan gold_gambar_manifest.csv)
  verifikasi_gold/LAPORAN_VERIFIKASI.md          (jumlah butir, persentase diubah, ragu, per reviewer)

Butir tanpa keputusan atau tanpa reviewer_id membuat skrip berhenti; butir RAGU tidak masuk gold final sampai diputuskan.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"ONE_TO_ONE", "NO_MATCH", "AMBIGUOUS", "COMPOSITE", "EXCLUDE"}
LABELS = {"KNOWN", "OTHER", "UNCERTAIN"}


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sheet_rows(path):
    ws = load_workbook(path, data_only=True)["Verifikasi"]
    head = [str(c.value) for c in ws[1]]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if any(v not in (None, "") for v in row):
            yield {h: ("" if v is None else str(v).strip()) for h, v in zip(head, row)}


def atribut(path):
    gold = {g["mapping_item_id"]: g for g in read(ROOT / "gold" / "gold_semua_dataset.csv")}
    fields = [k for k in next(iter(gold.values())).keys() if k not in ("confidence_usulan", "perlu_adjudikasi")]
    out, problems, changed, doubt, who = [], [], 0, 0, Counter()
    for r in sheet_rows(path):
        gid = r["mapping_item_id"]
        if gid not in gold:
            problems.append(f"id tidak dikenal: {gid[:12]}")
            continue
        g = dict(gold[gid])
        dec = r["keputusan"].upper()
        label = f"{r['dataset_id']} / {r['source_attribute_display']}"
        if dec not in {"SETUJU", "UBAH", "RAGU"}:
            problems.append(f"tanpa keputusan: {label}")
            continue
        if not r["reviewer_id"]:
            problems.append(f"tanpa reviewer_id: {label}")
            continue
        if dec == "RAGU":
            doubt += 1
            continue
        if dec == "UBAH":
            status = r["gold_status_final"].upper()
            if status not in STATUSES:
                problems.append(f"status final tidak valid: {label}")
                continue
            keys = r["gold_canonical_keys_final"]
            if status in ("ONE_TO_ONE", "COMPOSITE") and not keys:
                problems.append(f"kunci final kosong: {label}")
                continue
            if (status, keys) != (g["gold_status"], g["gold_canonical_keys"]):
                changed += 1
            g["gold_status"], g["gold_canonical_keys"] = status, keys
            g["ambiguous_candidate_canonical_keys"] = r["kandidat_ambiguous_final"]
        g["annotation_source"] = "terverifikasi_v1"
        g["annotator_id"] = ""
        g["annotation_round"] = "verifikasi"
        g["notes"] = r["catatan_reviewer"] or g["notes"]
        out.append({k: g[k] for k in fields})
        who[r["reviewer_id"]] += 1
    return out, fields, problems, changed, doubt, who


def foto(path):
    man = {m["filename"]: m for m in read(ROOT / "gambar" / "manifest" / "gold_gambar_manifest.csv")}
    out, problems, changed, doubt, excluded, who = [], [], 0, 0, 0, Counter()
    for r in sheet_rows(path):
        fn = r["filename"]
        if fn not in man:
            problems.append(f"foto tidak dikenal: {fn}")
            continue
        dec = r["keputusan"].upper()
        if dec not in {"SETUJU", "UBAH", "RAGU"}:
            problems.append(f"tanpa keputusan: {fn}")
            continue
        if not r["reviewer_id"]:
            problems.append(f"tanpa reviewer_id: {fn}")
            continue
        if dec == "RAGU":
            doubt += 1
            continue
        if r["foto_layak"].upper() == "T":
            excluded += 1
            continue
        m = dict(man[fn])
        if dec == "UBAH":
            label = r["label_final"].upper()
            if label not in LABELS:
                problems.append(f"label final tidak valid: {fn}")
                continue
            if label != m["label_kind"] or (label == "KNOWN" and r["varietas_final"] != m["true_variety"]):
                changed += 1
            m["label_kind"] = label
            m["true_variety"] = r["varietas_final"] if label == "KNOWN" else ""
        m["annotation_source"] = "terverifikasi_v1"
        m["annotator_id"] = ""
        m["catatan_tinjauan"] = r["catatan_reviewer"]
        out.append(m)
        who[r["reviewer_id"]] += 1
    return out, list(next(iter(man.values())).keys()) + ["annotation_source", "annotator_id", "catatan_tinjauan"], problems, changed, doubt, excluded, who


def write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atribut")
    ap.add_argument("--foto")
    a = ap.parse_args()
    lines = ["# Laporan verifikasi gold\n"]
    bad = False
    if a.atribut:
        rows, fields, problems, changed, doubt, who = atribut(a.atribut)
        write(ROOT / "gold" / "final" / "gold_semua_dataset_final.csv", fields, rows)
        n = len(rows)
        lines += ["## Atribut", f"- Butir masuk gold final: {n} dari 326", f"- Diubah dari usulan awal: {changed} ({changed / max(n, 1):.1%})",
                  f"- Ragu (belum masuk): {doubt}", f"- Per reviewer: {dict(who)}", f"- Masalah: {len(problems)}"]
        lines += [f"  - {p}" for p in problems[:30]]
        bad |= bool(problems)
    if a.foto:
        rows, fields, problems, changed, doubt, excluded, who = foto(a.foto)
        write(ROOT / "gambar" / "manifest" / "gold_gambar_manifest_final.csv", fields, rows)
        n = len(rows)
        lines += ["## Foto", f"- Foto masuk gold final: {n} dari 160", f"- Label diubah dari usulan: {changed} ({changed / max(n, 1):.1%})",
                  f"- Dikeluarkan (tidak layak): {excluded}", f"- Ragu (belum masuk): {doubt}", f"- Per reviewer: {dict(who)}", f"- Masalah: {len(problems)}"]
        lines += [f"  - {p}" for p in problems[:30]]
        bad |= bool(problems)
    report = ROOT / "verifikasi_gold" / "LAPORAN_VERIFIKASI.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if bad:
        print("Ada masalah; periksa lembar lalu jalankan ulang.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
