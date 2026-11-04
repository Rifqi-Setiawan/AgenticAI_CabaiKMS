"""Uji 40 foto Berita Resmi PVT dengan jalur vision yang dideploy (vision_hook), dua kondisi: kartu terlihat / tertutup.
Sama dengan vision_hook: registry = varietas spreadsheet run + varietas DB KMS (GET /varieties), VisionSession(run_scope_varieties=registry),
photo signal dari nama file, lalu fuse_photo_signals. Beda: tidak menulis ke KMS (tanpa /assets, /candidates), gambar dibaca dari disk
sebagai turunan WebP q80 (sama dengan profil CAS), dan kegagalan provider dicatat FAILED (tanpa fallback mock).

Cara menjalankan (3 Nov 2026, commit ac4f2e4): salin ke VPS /tmp/visi40 bersama uji_visi_40/ (sampel.csv, varietas_terdaftar.txt)
dan img/{terlihat,tertutup}/IMG_41xx.webp, lalu sebagai user hermes dari folder layanan:
  set -a; . ./.env; . ./.env.kms.d/runtime.env; set +a; ./.venv-kms/bin/python /tmp/visi40/run_visi40.py
Keluaran: /tmp/visi40/hasil.csv dan meta.json (diarsipkan ke data_evaluasi/pilot_foto_pvt/uji_visi_40/)."""
import csv, json, sys, time, datetime, traceback
from pathlib import Path
sys.path.insert(0, "/srv/hermes-control/services/agentic-ai-cabai-kms")
from src.integrations.client import KmsClient
from src.storage.config import get_settings
from src.agents import vision_classification as vc
from src.agents.signal_fusion import fuse_photo_signals
from src.agents.variety_registry import VarietyRegistry
from src.schema.contracts import ImageMetadata

BASE = Path("/tmp/visi40")
REG = [l.strip() for l in (BASE / "uji_visi_40/varietas_terdaftar.txt").read_text().splitlines() if l.strip()]
rows = list(csv.DictReader(open(BASE / "uji_visi_40/sampel.csv")))

def strict_call(*, response_model=None, messages=None, **kw):
    return vc.call_vision(response_model=response_model, messages=messages or [], max_retries=2)

client = KmsClient(get_settings())
res = client.request("GET", "/varieties")
db = [x for x in ((res.get("items", res) if isinstance(res, dict) else res) or []) if x]
registry = VarietyRegistry.build(spreadsheet_varieties=REG, db_varieties=db)
options = registry.get_canonical_names()
session = vc.VisionSession(run_scope_varieties=options, lvm_call=strict_call)
meta = {"run_scope": REG, "db_varieties": db, "options": options, "mulai": datetime.datetime.now().isoformat()}
out = open(BASE / "hasil.csv", "w", newline="")
cols = ["id", "kondisi", "status", "matched_variety", "identified_part", "confidence", "visual_confidence", "signals_consistent",
        "fusion_action", "fusion_reason", "visual_evidence", "detik", "galat"]
w = csv.DictWriter(out, fieldnames=cols); w.writeheader()
for kondisi in ("terlihat", "tertutup"):
    for r in rows:
        fn = f"{r['id']}.jpg"
        b = (BASE / "img" / kondisi / f"{r['id']}.webp").read_bytes()
        img = ImageMetadata(file_id=f"{r['id']}-{kondisi}", filename=fn, mime_type="image/webp", size=len(b),
                            created_time=datetime.datetime(2026, 11, 3))
        sig = vc.extract_photo_context_signal(fn, known_varieties=REG, registry=registry)
        rec = {"id": r["id"], "kondisi": kondisi}
        t = time.time()
        for attempt in (1, 2):
            try:
                out_r = session.classify(img, image_bytes=b, photo_signal=sig)
                oc = fuse_photo_signals(filename_match=sig.suggested_variety_hint, registry_known=registry, visual_result=out_r,
                                        is_exact_hint=getattr(sig, "is_exact_hint", True), raw_filename=fn)
                rec.update(status=out_r.classification_status, matched_variety=out_r.matched_variety, identified_part=out_r.identified_part,
                           confidence=out_r.confidence, visual_confidence=getattr(out_r, "visual_confidence", ""),
                           signals_consistent=getattr(out_r, "signals_consistent", ""), fusion_action=getattr(oc.action, "value", oc.action),
                           fusion_reason=oc.reason, visual_evidence=(out_r.visual_evidence or "")[:400], galat="")
                break
            except Exception as e:
                rec.update(status="FAILED", galat=f"{type(e).__name__}: {str(e)[:200]}")
                if attempt == 1: time.sleep(15)
        rec["detik"] = round(time.time() - t, 1)
        w.writerow(rec); out.flush()
        print(kondisi, r["id"], rec.get("status"), rec.get("matched_variety"), rec.get("fusion_action"), rec["detik"], flush=True)
meta["selesai"] = datetime.datetime.now().isoformat()
(BASE / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
