"""Dump kandidat retrieval produksi per atribut (tanpa LLM, tanpa foto, tanpa gold).

Untuk baseline S2+tau dan Hit@k. Parser, exact-name, dan _retrieve_with_header_fallback memakai kode produksi;
safe_rerank diganti stub yang selalu mengembalikan NULL agar tidak ada panggilan model.
Jalankan dari root repo:
  sudo -u hermes .venv-kms/bin/python -B /srv/hermes-control/eval/cabai-ui-experiment/dump_retrieval.py \
      --inputs /srv/hermes-control/eval/cabai-ui-experiment/inputs --out /srv/hermes-control/eval/cabai-ui-experiment/hasil_retrieval/<tgl>
"""
import argparse, csv, importlib.util, json, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("-k", type=int, default=8)
    a = ap.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    spec = importlib.util.spec_from_file_location("harness_vps", HERE / "harness_vps.py")
    hv = importlib.util.module_from_spec(spec); spec.loader.exec_module(hv)

    import src.ui.pipeline_runner as pr
    from src.schema.canonical import CanonicalSchema
    from src.schema.contracts import SchemaMapping, NULL_ROW

    schema = CanonicalSchema.from_template()
    key_of = lambda rid: (schema.row_by_id(rid).canonical_key if schema.row_by_id(rid) else "")
    rows_out, current = [], {}
    original = pr._retrieve_with_header_fallback

    def recording(profile, **kw):
        hits = original(profile, **kw)
        for rank, h in enumerate(hits, 1):
            rows_out.append({**current, "source_attribute": profile.attribute_name,
                             "source_context": profile.structural_context or "", "rank": rank,
                             "row_id": h.row_id, "canonical_key": key_of(h.row_id), "distance": round(float(h.distance), 6)})
        return hits

    def stub_rerank(profile, candidates, state, *, source_format, **kw):
        return SchemaMapping(source_attribute=profile.attribute_name, source_context=profile.structural_context,
                             source_format=source_format, target_canonical_row=NULL_ROW, confidence=0.0,
                             reasoning="stub retrieval dump", normalization_required=False), {}

    pr._retrieve_with_header_fallback = recording
    pr.safe_rerank = stub_rerank
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    meta = []
    for kind, rid, fname, sheet, fmt, header, drive, maxi in hv.RUNS:
        current = {"dataset": rid if kind != "atribut_n08var" else "N08VAR", "file": fname}
        t0 = time.time()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                res = pr.run_pipeline_ui(Path(a.inputs) / fname, source_format=fmt, sheet_name=sheet, header_rows=header,
                                         drive_folder_id=None, k=a.k, max_images=1,
                                         review_queue_path=Path(tmp) / "q.jsonl", checkpoint_db_path=Path(tmp) / "c.sqlite")
            m = res.mapping_df
            for _, r in m.iterrows():
                if str(r["mapping_method"]).startswith("exact"):
                    rows_out.append({**current, "source_attribute": r["source_attribute"],
                                     "source_context": r["source_context"] if isinstance(r["source_context"], str) else "",
                                     "rank": 0, "row_id": "", "canonical_key": r["proposed_target_canonical_key"] or "",
                                     "distance": ""})
            meta.append({**current, "status": "ok", "n_mapping": len(m), "detik": round(time.time() - t0, 1)})
        except Exception as exc:
            meta.append({**current, "status": "gagal", "galat": repr(exc)[:300], "detik": round(time.time() - t0, 1)})
        print(meta[-1], flush=True)
    with open(out / "retrieval_dump.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "file", "source_attribute", "source_context", "rank", "row_id", "canonical_key", "distance"])
        w.writeheader(); w.writerows(rows_out)
    commit = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    (out / "meta.json").write_text(json.dumps({"commit": commit, "k": a.k, "runs": meta}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
