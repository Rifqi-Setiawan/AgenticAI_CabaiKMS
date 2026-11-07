"""Harness L1: jalankan pipeline produksi (kode dan model yang sama dengan UI) tanpa UI, simpan CSV per run.

Dijalankan di VPS dengan interpreter repo, DARI LUAR repo (tidak mengubah commit):
  cd /srv/hermes-control/services/agentic-ai-cabai-kms
  sudo -u hermes .venv-kms/bin/python -B /srv/hermes-control/eval/cabai-ui-experiment/harness_vps.py \
      --inputs /srv/hermes-control/eval/cabai-ui-experiment/inputs \
      --out /srv/hermes-control/eval/cabai-ui-experiment/hasil_harness/2026-11-xx --reps 3 --only A

Keluaran per run: <out>/rep<r>/<jenis>/<ID>/{mapping.csv, vision.csv, meta.json}
 mapping.csv memuat kolom UI ditambah retrieval_top1_key (kunci kanonik baris retrieval top-1; dasar varian S2).
Antrean review ditulis ke berkas sementara agar antrean produksi tidak tercemar. Tidak ada Commit ke KMS.
"""
import argparse
import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DRIVE1 = "1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g"
# (jenis, ID, berkas, sheet, format, header_rows, drive, max_images)
RUNS = [
    ("atribut", "R01", "data_input.xlsx", "Resume Data", "row-oriented", None, None, 5),
    ("atribut", "R02", "input_cabai_kms.xlsx", "Data Varietas", "row-oriented", 1, None, 5),
    ("atribut", "N07", "E07_kementan_deskripsi_ext.xlsx", "Deskripsi Varietas", "row-oriented", 1, None, 5),
    ("atribut", "N08", "E08_zenodo_capsicum_en.xlsx", "Observed85_readable", "row-oriented", 1, None, 5),
    ("atribut", "N09", "dataset_cabai_deskripsi_varietas.xlsx", "transposed", "transposed", None, None, 5),
    ("atribut_n08var", "N08", "E08_zenodo_capsicum_en_variety.xlsx", "Observed85_readable", "row-oriented", 1, None, 5),  # deviasi D4: hanya kolom A1 diganti "Variety"
    ("kombinasi", "S01", "D01_transposed_indonesia_mixed.xlsx", "Data_Transposed", "transposed", None, DRIVE1, 12),
    ("kombinasi", "S02", "D02_row_flat_english_semantic.xlsx", "English_Flat_Data", "row-oriented", 1, DRIVE1, 12),
    ("kombinasi", "S03", "D03_row_multilevel_indonesia.xlsx", "Data_Bertingkat", "row-oriented", None, DRIVE1, 12),
    ("kombinasi", "S04", "D04_varietas_kosong_invalid.xlsx", "Data_Invalid", "row-oriented", 1, DRIVE1, 12),
]
# Run foto Commons: folder Drive F1..F8 diberikan lewat --commons-folders (file JSON {"F1": "<id>", ...})


S3 = False


def commit():
    try:
        return subprocess.check_output(["git", "-C", str(Path.cwd()), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def execute(run, inputs, out, rep, k):
    from src.schema.canonical import CanonicalSchema
    import src.ui.pipeline_runner as pr
    from src.ui.pipeline_runner import run_pipeline_ui

    # Perekam S2: bungkus fungsi retrieval produksi, catat hit teratas per atribut, hasil retrieval tidak diubah.
    top1 = {}
    original = pr._retrieve_with_header_fallback

    def recording(profile, **kw):
        hits = original(profile, **kw)
        top1[(profile.attribute_name, profile.structural_context or "")] = hits[0].row_id if hits else ""
        return hits

    pr._retrieve_with_header_fallback = recording
    if S3:
        # Baseline S3: LLM tanpa retrieval. Penilai melihat SELURUH baris kanonik dalam urutan template (tanpa peringkat kemiripan).
        from src.agents.schema_matching.retrieval import RetrievalHit

        def all_rows(profile, *, k, schema, **kw):
            hits = [RetrievalHit(row_id=r.id, label=r.label, domain=r.domain, distance=0.0) for r in schema.rows]
            top1[(profile.attribute_name, profile.structural_context or "")] = ""
            return hits

        pr._retrieve_with_header_fallback = all_rows

    kind, rid, fname, sheet, fmt, header, drive, maxi = run
    dest = Path(out) / f"rep{rep}" / kind / rid
    if (dest / "meta.json").exists():
        print("lewati (sudah ada):", dest)
        return
    dest.mkdir(parents=True, exist_ok=True)
    schema = CanonicalSchema.from_template()
    t0 = time.time()
    meta = {"run": rid, "kind": kind, "rep": rep, "file": fname, "sheet": sheet, "format": fmt, "header_rows": header,
            "drive": drive, "max_images": maxi, "k": k, "commit": commit(),
            "sha256_berkas": __import__("hashlib").sha256((Path(inputs) / fname).read_bytes()).hexdigest(), "start": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            res = run_pipeline_ui(Path(inputs) / fname, source_format=fmt, sheet_name=sheet, header_rows=header,
                                  drive_folder_id=drive, k=k, max_images=maxi,
                                  review_queue_path=Path(tmp) / "queue.jsonl",
                                  checkpoint_db_path=Path(tmp) / "ckpt.sqlite")
        import pandas as pd
        m = res.mapping_df.copy()

        def key_of(row_id):
            r = schema.row_by_id(row_id) if isinstance(row_id, str) and row_id else None
            return r.canonical_key if r else ""

        m["retrieval_top1_key"] = m["retrieval_top1_row"].map(key_of)
        # S2: kunci baris retrieval teratas untuk SEMUA atribut yang melalui retrieval; atribut exact_name memakai kunci exact
        def s2(row):
            if str(row["mapping_method"]).startswith("exact"):
                return row["proposed_target_canonical_key"] or ""
            return key_of(top1.get((row["source_attribute"], row["source_context"] if isinstance(row["source_context"], str) else ""), ""))

        m["retrieval_s2_key"] = m.apply(s2, axis=1)
        for c in ("exact_name_candidates", "verifier_hard_issues", "verifier_warnings"):
            if c in m:
                m[c] = m[c].map(lambda v: "|".join(v) if isinstance(v, (list, tuple)) else v)
        m.to_csv(dest / "mapping.csv", index=False, encoding="utf-8-sig")
        (dest / "hasil_asli.xlsx").write_bytes(res.workbook_bytes)
        res.canonical_df.to_csv(dest / "canonical.csv", index=False, encoding="utf-8-sig")
        (dest / "trace.json").write_text(json.dumps(
            {"error_trace": res.error_trace, "agent_status": res.agent_status, "provider_trace": res.provider_trace,
             "retrieval_backend": res.retrieval_backend, "retrieval_k": res.retrieval_k, "schema_version": res.schema_version,
             "template_hash": res.template_hash, "embedding_model_name": res.embedding_model_name, "run_id": res.run_id},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        pd.DataFrame(res.vision_rows).to_csv(dest / "vision.csv", index=False, encoding="utf-8-sig")
        meta.update(s2_keys=[list(k) + [v] for k, v in top1.items()], images_discovered=res.images_discovered, n_mapping=len(m), n_vision=len(res.vision_rows),
                    fingerprint=res.evaluation_config_fingerprint, errors=res.error_trace[-5:], status="ok")
    except Exception as exc:  # galat dicatat apa adanya; tidak diulang kecuali galat jaringan
        import traceback
        meta.update(status="gagal", galat=repr(exc), traceback=traceback.format_exc())
    pr._retrieve_with_header_fallback = original
    meta["detik"] = round(time.time() - t0, 1)
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    import csv as _csv
    log = Path(out) / "RUNLOG_harness.csv"
    new = not log.exists()
    with open(log, "a", newline="", encoding="utf-8-sig") as fh:
        w = _csv.writer(fh)
        if new:
            w.writerow(["waktu_mulai", "rep", "jenis", "run", "berkas", "sha256_berkas", "commit", "drive", "max_foto", "n_mapping",
                        "images_discovered", "n_vision", "fingerprint", "status", "detik", "galat"])
        w.writerow([meta["start"], rep, kind, rid, fname, meta.get("sha256_berkas", ""), meta["commit"], drive or "", maxi,
                    meta.get("n_mapping", ""), meta.get("images_discovered", ""), meta.get("n_vision", ""), meta.get("fingerprint", ""),
                    meta["status"], meta["detik"], meta.get("galat", "")])
    print(rid, "rep", rep, meta["status"], meta["detik"], "s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--only", choices=["A", "B", "C", "ALL"], default="ALL", help="A=atribut, B=kombinasi, C=foto Commons")
    ap.add_argument("--commons-folders", help="JSON {\"F1\": \"<id folder>\", ...}")
    ap.add_argument("--ids", help="batasi ke ID tertentu, mis. R01,S01 (untuk uji asap)")
    ap.add_argument("--ordered", action="store_true", help="jalankan sesuai urutan --ids (tanpa pengacakan)")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261031)
    ap.add_argument("--s3", action="store_true", help="baseline S3: seluruh baris kanonik diberikan ke penilai tanpa retrieval")
    ap.add_argument("--tanpa-foto", action="store_true",
                    help="run kombinasi tanpa folder Drive (pemetaan atribut saja; tidak ada panggilan visi atau kandidat foto ke KMS)")
    a = ap.parse_args()
    global S3
    S3 = a.s3
    sys.path.insert(0, str(Path.cwd()))  # dijalankan dari root repo
    runs = []
    if a.only in ("A", "ALL"):
        runs += [r for r in RUNS if r[0].startswith("atribut")]
    if a.only in ("B", "ALL"):
        runs += [r for r in RUNS if r[0] == "kombinasi"]
    if a.only in ("C", "ALL") and a.commons_folders:
        for fid, gid in json.loads(Path(a.commons_folders).read_text()).items():
            runs.append(("gambar", fid, "spreadsheet_varietas_terdaftar.xlsx", "Data Varietas", "row-oriented", None, gid, 20))
    if a.ids:
        runs = [r for r in runs if r[1] in a.ids.split(",")]
    if a.tanpa_foto:
        runs = [(*r[:6], None, r[7]) if r[0] == "kombinasi" else r for r in runs]
    for rep in range(1, a.reps + 1):
        order = list(runs)
        if a.ordered and a.ids:
            wanted = a.ids.split(",")
            order.sort(key=lambda r: wanted.index(r[1]))
        else:
            random.Random(a.seed + rep).shuffle(order)
        for run in order:
            execute(run, a.inputs, a.out, rep, a.k)
    write_checksums(a.out)


def write_checksums(out):
    import hashlib
    lines = []
    for f in sorted(Path(out).rglob("*")):
        if f.is_file() and f.name != "SHA256SUMS.txt":
            lines.append(hashlib.sha256(f.read_bytes()).hexdigest() + "  " + str(f.relative_to(out)))
    nl = chr(10)
    (Path(out) / "SHA256SUMS.txt").write_text(nl.join(lines) + nl, encoding="utf-8")


if __name__ == "__main__":
    main()
