"""Ubah unduhan CSV dari UI CABAI-KMS menjadi berkas prediksi untuk hitung_metrik.py.

Struktur folder hasil UI (satu subfolder per run):

  hasil_ui/<tanggal>/
    atribut/<ID dataset>/mapping.csv          # unduhan tabel "Inspektor pemetaan" (ID: R01, R02, S01..S04, N07, N08, N09)
    gambar/<nama run>/vision.csv              # unduhan tabel "Hasil multimodal" (satu per run foto; boleh banyak run)

Pemakaian:
  python konversi_ui.py atribut --gold gold/gold_semua_dataset.csv --dir hasil_ui/2026-11-03/atribut --out pred_atribut
  python konversi_ui.py gambar  --gold gambar/manifest/gold_gambar_manifest.csv --dir hasil_ui/2026-11-03/gambar --out pred_gambar

Keluaran atribut : pred_atribut_S4.csv (sistem penuh), pred_atribut_S1.csv (hanya kecocokan nama eksak)
Keluaran gambar  : pred_gambar_V3.csv (fusi), pred_gambar_V1.csv (hanya gambar), pred_gambar_V2.csv (hanya nama file)
"""
import argparse
import csv
import re
import sys
from pathlib import Path

REGISTRY = ["Cabai Rawit", "Jalapeno", "Habanero", "Cayenne", "Paprika", "Cabai Korea", "Serrano", "Hungarian Wax"]


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def pick(row, *names):
    """Ambil nilai dari kolom pertama yang ada (UI memberi nama kolom berbeda dari nama internal)."""
    low = {k.strip().lower(): v for k, v in row.items() if k is not None}
    for n in names:
        if n.lower() in low:
            return (low[n.lower()] or "").strip()
    return ""


# ------------------------------------------------------------------ atribut
def run_attr(args):
    gold = read_csv(args.gold)
    exact_key = {(g["dataset_id"], g["source_attribute_display"].strip()): g for g in gold}
    fuzzy_key = {}
    for g in gold:
        fuzzy_key.setdefault((g["dataset_id"], norm(g["source_attribute_display"])), []).append(g)
    root = Path(args.dir)
    s4, s1, s2, seen = {}, {}, {}, set()
    problems = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        ds = sub.name
        f = sub / "mapping.csv"
        if not f.is_file():
            problems.append(f"{ds}: mapping.csv tidak ada")
            continue
        rows = read_csv(f)
        for r in rows:
            disp = pick(r, "Source attribute", "source_attribute_display")
            key = exact_key.get((ds, disp.strip()))
            if key is None:
                cand = fuzzy_key.get((ds, norm(disp)), [])
                key = cand[0] if len(cand) == 1 else None
            if key is None:
                problems.append(f"{ds}: atribut '{disp}' tidak ada di gold")
                continue
            prop = pick(r, "Proposed canonical key", "proposed_target_canonical_key")
            method = pick(r, "Mapping method", "mapping_method").lower()
            gid = key["mapping_item_id"]
            seen.add(gid)
            s4[gid] = prop
            s1[gid] = prop if method.startswith("exact") else ""
            s2[gid] = pick(r, "retrieval_s2_key")  # hanya ada pada keluaran harness L1
    ran = {p.name for p in root.iterdir() if p.is_dir()}
    missing = [g for g in gold if g["mapping_item_id"] not in seen and g["dataset_id"] in ran]
    if missing:
        problems.append(f"{len(missing)} butir gold tidak ada di keluaran UI (contoh: {missing[0]['source_attribute_display']})")
    for name, data in (("S4", s4), ("S1", s1), ("S2", s2)):
        if name == "S2" and not any(s2.values()):
            continue  # unduhan UI tidak memuat S2; hanya keluaran harness (kolom retrieval_s2_key)
        out = Path(f"{args.out}_{name}.csv")
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["mapping_item_id", "predicted_key"])
            for g in gold:
                if g["mapping_item_id"] in seen or g["dataset_id"] in ran:  # butir tak dihasilkan sistem = tanpa pemetaan (dilaporkan sebagai peringatan)
                    w.writerow([g["mapping_item_id"], data.get(g["mapping_item_id"], "")])
        print("ditulis:", out)
    scope_note = "Dataset yang belum dijalankan tidak masuk file prediksi; gunakan gold yang sama dan perhatikan jumlah butir."
    print(scope_note)
    for p in problems:
        print("PERINGATAN:", p)


# ------------------------------------------------------------------- gambar
def fusion_action(status, reason):
    status = (status or "").strip().upper()
    reason = reason or ""
    if status.startswith("FAILED_CANDIDATE"):
        return "CANDIDATE"
    if status in ("FAILED", "DISCARDED"):
        return status
    if status == "CANDIDATE" or reason.startswith("CANDIDATE"):
        return "CANDIDATE"
    if reason.startswith("PHOTO_VARIETY_MISMATCH"):
        low = reason.lower()
        if any(t in low for t in ("below threshold", "visual status uncertain", "no visual classification", "unknown classification status")):
            return "REVIEW_UNCERTAIN"
        return "REVIEW_MISMATCH"
    return "AUTO_LINK"


def filename_only(fn):
    base = norm(Path(fn).stem)
    for v in REGISTRY:
        if norm(v) in base:
            return "KNOWN", v
    return "UNCERTAIN", ""


def run_img(args):
    gold = {r["filename"]: r for r in read_csv(args.gold)}
    root = Path(args.dir)
    rows = {}
    for f in sorted(root.rglob("vision.csv")):
        for r in read_csv(f):
            fn = pick(r, "filename")
            if fn:
                rows[fn] = r
    missing = [fn for fn in gold if fn not in rows]
    v3, v1 = [], []
    for fn, g in gold.items():
        r = rows.get(fn)
        if r is None:
            continue
        status = pick(r, "classification_status", "status").upper()
        variety = pick(r, "matched_variety")
        action = fusion_action(status, pick(r, "write_reason"))
        if action == "AUTO_LINK":
            ps = "KNOWN" if status == "KNOWN" else (status or "UNCERTAIN")
        elif action == "CANDIDATE":
            ps = "OTHER"
        elif action == "REVIEW_UNCERTAIN":
            ps = "UNCERTAIN"
        elif action == "REVIEW_MISMATCH":
            ps = status if status in ("KNOWN", "OTHER", "UNCERTAIN") else "UNCERTAIN"
        else:
            ps = "UNCERTAIN"
        v3.append((fn, ps, variety if ps == "KNOWN" else "", action))
        vs = "OTHER" if status in ("CANDIDATE", "FAILED_CANDIDATE_RECORD") else (status if status in ("KNOWN", "OTHER", "UNCERTAIN") else "UNCERTAIN")
        v1.append((fn, vs, variety if vs == "KNOWN" else ""))
    v2 = [(fn,) + filename_only(fn) for fn in gold if fn in rows]
    for name, data, cols in (("V3", v3, ["filename", "predicted_status", "predicted_variety", "fusion_action"]),
                             ("V1", v1, ["filename", "predicted_status", "predicted_variety"]),
                             ("V2", v2, ["filename", "predicted_status", "predicted_variety"])):
        out = Path(f"{args.out}_{name}.csv")
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows(data)
        print("ditulis:", out, len(data), "foto")
    if missing:
        print(f"PERINGATAN: {len(missing)} foto gold tidak ada di keluaran UI (contoh: {missing[:3]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("atribut", run_attr), ("gambar", run_img)):
        p = sub.add_parser(name)
        p.add_argument("--gold", required=True)
        p.add_argument("--dir", required=True)
        p.add_argument("--out", required=True)
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)
