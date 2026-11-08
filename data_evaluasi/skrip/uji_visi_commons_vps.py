"""Run foto Commons (160 foto) lewat jalur vision produksi di VPS, dengan daftar varietas terdaftar yang bisa diatur.

Dipakai untuk run pelengkap "tanpa OTHER" (17 varietas terdaftar, semua varietas foto ada di spreadsheet) dan run
pembanding "dengan OTHER" (8 varietas, konfigurasi asli run UI 1 Nov 2026) dengan skrip dan commit yang sama.

Sama dengan node vision (src/integrations/vision_hook.py): registry = varietas spreadsheet run + GET /varieties KMS,
VisionSession(run_scope_varieties=registry), extract_photo_context_signal dari NAMA FILE ASLI (kondisi informatif/netral/
menyesatkan dipertahankan), lalu fuse_photo_signals. Gambar diubah ke turunan WebP persis seperti ImageStorage CAS
(exif_transpose, RGB/RGBA, info dihapus, maks 2560 px, WEBP q80 method 6).
Sejak 7 Nov 2026 (D20): dengan --kanonik, deskripsi morfologi varietas run juga dibaca dari sheet kanonik run
(variety_descriptions_from_worksheet), persis seperti vision_hook. Skrip ini dipakai untuk semua set foto (folder bebas).
Beda: tidak menulis ke KMS (tanpa /assets, /candidates), tidak lewat Google Drive, dan kegagalan provider dicatat FAILED
(tidak diganti mock).

Pemakaian di VPS sebagai user hermes, dari folder layanan (environment layanan dimuat lebih dulu):
  set -a; . ./.env; . ./.env.kms.d/runtime.env; set +a
  ./.venv-kms/bin/python uji_visi_commons_vps.py --dasar /tmp/visi160 --varietas varietas_17.txt --label tanpa_other
Keluaran: <dasar>/hasil_<label>.csv dan <dasar>/meta_<label>.json
"""
import argparse
import csv
import datetime
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, "/srv/hermes-control/services/agentic-ai-cabai-kms")
from src.agents import vision_classification as vc  # noqa: E402
from src.agents.signal_fusion import fuse_photo_signals  # noqa: E402
from src.agents.variety_registry import VarietyRegistry  # noqa: E402
from src.integrations.client import KmsClient  # noqa: E402
from src.schema.contracts import ImageMetadata  # noqa: E402
from src.storage.config import get_settings  # noqa: E402


def turunan_cas(payload: bytes) -> bytes:
    with Image.open(io.BytesIO(payload)) as original:
        oriented = ImageOps.exif_transpose(original)
        mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
        clean = oriented.convert(mode)
        clean.info.clear()
        clean.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        clean.save(out, format="WEBP", quality=80, method=6, exif=b"", icc_profile=b"", xmp=b"")
        return out.getvalue()


def strict_call(*, response_model=None, messages=None, **kw):
    return vc.call_vision(response_model=response_model, messages=messages or [], max_retries=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dasar", required=True)
    ap.add_argument("--varietas", help="berkas teks daftar varietas terdaftar (satu per baris)")
    ap.add_argument("--kanonik", help="workbook kanonik hasil pipeline spreadsheet; varietas run diambil persis seperti vision_hook")
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    base = Path(a.dasar)
    run_descriptions = None
    if a.kanonik:
        import openpyxl
        from src.integrations.vision_hook import extract_run_scope_varieties
        from src.ui.pipeline_runner import SHEET_NAME
        wb = openpyxl.load_workbook(a.kanonik)
        reg = list(extract_run_scope_varieties(wb))
        # D20, sama dengan vision_hook: deskripsi varietas run dibaca dari sheet kanonik run.
        if SHEET_NAME in wb.sheetnames:
            run_descriptions = vc.variety_descriptions_from_worksheet(wb[SHEET_NAME])
    else:
        reg = [l.strip() for l in (base / a.varietas).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = list(csv.DictReader(open(base / "daftar_foto.csv", encoding="utf-8")))

    client = KmsClient(get_settings())
    res = client.request("GET", "/varieties")
    db = [x for x in ((res.get("items", res) if isinstance(res, dict) else res) or []) if x]
    registry = VarietyRegistry.build(spreadsheet_varieties=reg, db_varieties=db)
    options = registry.get_canonical_names()
    session = vc.VisionSession(run_scope_varieties=options, run_descriptions=run_descriptions, lvm_call=strict_call)
    deskripsi = {d.name: sum(1 for v in d.characteristics.values() if v) for d in (run_descriptions or [])}
    meta = {"label": a.label, "kanonik": a.kanonik, "run_scope": reg, "db_varieties": db, "options": options,
            "deskripsi_run_jumlah_karakter": deskripsi,
            "mulai": datetime.datetime.now().isoformat()}

    cols = ["filename", "folder", "status", "matched_variety", "identified_part", "confidence", "visual_confidence",
            "signals_consistent", "filename_hint", "fusion_action", "fusion_reason", "visual_evidence", "detik", "galat"]
    out = open(base / f"hasil_{a.label}.csv", "w", newline="", encoding="utf-8")
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for i, r in enumerate(rows, 1):
        fn = r["filename"]
        rec = {"filename": fn, "folder": r["folder"]}
        t = time.time()
        try:
            b = turunan_cas((base / "foto" / r["folder"] / fn).read_bytes())
        except Exception as e:
            rec.update(status="FAILED", galat=f"media: {type(e).__name__}: {str(e)[:200]}", detik=0)
            w.writerow(rec); out.flush(); print(a.label, i, fn, "MEDIA_FAILED", flush=True)
            continue
        img = ImageMetadata(file_id=f"{a.label}-{fn}", filename=fn, mime_type="image/webp", size=len(b),
                            created_time=datetime.datetime(2026, 11, 3))
        sig = vc.extract_photo_context_signal(fn, known_varieties=reg, registry=registry)
        for attempt in (1, 2):
            try:
                o = session.classify(img, image_bytes=b, photo_signal=sig)
                oc = fuse_photo_signals(filename_match=sig.suggested_variety_hint, registry_known=registry, visual_result=o,
                                        is_exact_hint=getattr(sig, "is_exact_hint", True), raw_filename=fn)
                rec.update(status=o.classification_status, matched_variety=o.matched_variety, identified_part=o.identified_part,
                           confidence=o.confidence, visual_confidence=getattr(o, "visual_confidence", ""),
                           signals_consistent=getattr(o, "signals_consistent", ""), filename_hint=sig.suggested_variety_hint or "",
                           fusion_action=getattr(oc.action, "value", oc.action), fusion_reason=oc.reason,
                           visual_evidence=(o.visual_evidence or "")[:400], galat="")
                break
            except Exception as e:
                rec.update(status="FAILED", galat=f"{type(e).__name__}: {str(e)[:200]}")
                if attempt == 1:
                    time.sleep(15)
        rec["detik"] = round(time.time() - t, 1)
        w.writerow(rec)
        out.flush()
        print(a.label, i, fn, rec.get("status"), rec.get("matched_variety"), rec.get("fusion_action"), rec["detik"], flush=True)
    meta["selesai"] = datetime.datetime.now().isoformat()
    (base / f"meta_{a.label}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
