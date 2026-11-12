"""Ablasi fusi D24: jawaban visual dua tahap yang SAMA, digabung ulang dengan aturan fusi lama atau baru.

Run dua tahap menyimpan jawaban visual per foto (status, varietas, visual_confidence) di hasil_<label>.csv.
Fusi bersifat deterministik, jadi skrip ini menghitung ulang fusion_action tanpa memanggil model:
  --fusi baru  fuse_photo_signals(independent_signals=True)   (harus sama persis dengan yang tercatat; uji kewarasan)
  --fusi lama  fuse_photo_signals(independent_signals=False)  (aturan <= D23)
Registri dan petunjuk nama berkas dibangun ulang dari meta_<label>.json (run_scope + db_varieties), sama dengan run.
Keluaran: salinan struktur folder --hasil di --out dengan kolom fusion_action/fusion_reason diganti, siap diskor dengan
skor_foto_ulang.py dan skor_nama_file_berpasangan.py.

  python skrip/ablasi_fusi_m2.py --hasil /tmp/visi_m2 --fusi lama --out /tmp/visi_m2_fusi_lama
"""
import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/srv/hermes-control/services/agentic-ai-cabai-kms")
from src.agents import vision_classification as vc  # noqa: E402
from src.agents.signal_fusion import fuse_photo_signals  # noqa: E402
from src.agents.variety_registry import VarietyRegistry  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasil", required=True)
    ap.add_argument("--fusi", choices=("lama", "baru"), required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    src, dst = Path(a.hasil), Path(a.out)
    berubah = beda_dari_catatan = total = 0
    for hasil in sorted(src.glob("*/hasil_*.csv")):
        label = hasil.stem[len("hasil_"):]
        meta = json.loads((hasil.parent / f"meta_{label}.json").read_text(encoding="utf-8"))
        reg = meta["run_scope"]
        registry = VarietyRegistry.build(spreadsheet_varieties=reg, db_varieties=meta.get("db_varieties") or [])
        with open(hasil, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
            cols = list(rows[0]) if rows else []
        for r in rows:
            if r.get("status") not in ("KNOWN", "OTHER", "UNCERTAIN"):
                continue
            total += 1
            sig = vc.extract_photo_context_signal(r["filename"], known_varieties=reg, registry=registry)
            visual = {"classification_status": r["status"], "matched_variety": r["matched_variety"] or None,
                      "visual_confidence": float(r["visual_confidence"] or r["confidence"] or 0.0)}
            oc = fuse_photo_signals(filename_match=sig.suggested_variety_hint, registry_known=registry, visual_result=visual,
                                    is_exact_hint=getattr(sig, "is_exact_hint", True), raw_filename=r["filename"],
                                    independent_signals=(a.fusi == "baru"))
            aksi = getattr(oc.action, "value", oc.action)
            if aksi != r["fusion_action"]:
                berubah += 1
                if a.fusi == "baru":
                    beda_dari_catatan += 1
                    print("BEDA dari catatan:", hasil.parent.name, label, r["filename"], r["fusion_action"], "->", aksi)
            r["fusion_action"], r["fusion_reason"] = aksi, oc.reason
        out_dir = dst / hasil.parent.name
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / hasil.name, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        shutil.copy(hasil.parent / f"meta_{label}.json", out_dir)
        if (hasil.parent / "daftar_foto.csv").exists():
            shutil.copy(hasil.parent / "daftar_foto.csv", out_dir)
    print(f"fusi {a.fusi}: {total} foto, fusion_action berubah {berubah}; beda dari catatan run {beda_dari_catatan}")


if __name__ == "__main__":
    main()
