"""Uji fungsional fitur atribut baru jadi kanonik (E-A1 sampai E-A3), pada database uji terpisah.

Dijalankan di VPS dengan interpreter repo, memakai kode repo yang sama dengan produksi tetapi database `cabai_kms_eval`:
  cd /srv/hermes-control/services/agentic-ai-cabai-kms
  sudo -u hermes .venv-kms/bin/python -B <path>/eval_atribut_baru.py --out <folder keluaran>

Masukan sintetis: data_input.xlsx (R01, format Resume Data) ditambah kolom atribut baru. Ini uji fungsi, bukan uji generalisasi.
Kurator disimulasikan oleh aturan tetap di bawah (kunci jawaban dibuat sebelum run).
"""
import argparse
import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import openpyxl
from sqlalchemy import text

REPO = Path("/srv/hermes-control/services/agentic-ai-cabai-kms")
sys.path.insert(0, str(REPO))

from src.storage.config import Settings  # noqa: E402
from src.storage.db import make_engine  # noqa: E402
from src.storage.document_contracts import KnowledgeDocument  # noqa: E402
from src.storage.document_planner import DocumentPlanner  # noqa: E402
from src.storage.document_repository import DocumentRepository  # noqa: E402
from src.storage.errors import Conflict  # noqa: E402
from src.storage.migrate import migrate  # noqa: E402

DB_NAME = "cabai_kms_eval"
URL = f"postgresql+psycopg://hermes@/{DB_NAME}?host=/tmp&port=5432"
PSQL = "/srv/apps/hermes/opt/postgresql/usr/lib/postgresql/16/bin"
SRC_WB = Path("/srv/hermes-control/eval/cabai-ui-experiment/inputs/data_input.xlsx")

# Kunci jawaban kurator (ditetapkan sebelum run): label -> keputusan
KEY = {
    "Kadar Capsaicin (ppm)": {"action": "REGISTER_NEW", "organ": "buah", "value_type": "number", "unit": "ppm"},
    "Kandungan Vitamin C (mg/100g)": {"action": "REGISTER_NEW", "organ": "buah", "value_type": "number", "unit": "mg/100g"},
    "Aroma Buah": {"action": "REGISTER_NEW", "organ": "buah", "value_type": "text", "unit": None},
    "Tinggi Tanaman Dewasa": {"action": "MAP_TO_EXISTING", "attribute_id": "attr_tinggi_tanaman"},
    "Catatan Surveyor": {"action": "REJECT"},
}
NEW_LABEL_RUN2 = "Ketebalan Daging Buah (mm)"   # belum pernah dilihat pada run 1
NEAR_DUP_RUN2 = "Kadar Capsaicin Total"          # mirip label terdaftar; kurator memetakan sebagai alias


def values_for(label: str, n: int) -> list[object]:
    base = {
        "Kadar Capsaicin (ppm)": [1500 + 25 * i for i in range(n)],
        "Kandungan Vitamin C (mg/100g)": [110 + i for i in range(n)],
        "Aroma Buah": ["harum", "tajam", "ringan"] * n,
        "Tinggi Tanaman Dewasa": [82.5 + i for i in range(n)],
        "Catatan Surveyor": [f"catatan lapangan {i}" for i in range(n)],
        NEW_LABEL_RUN2: [3.0 + 0.1 * i for i in range(n)],
        NEAR_DUP_RUN2: [1600 + 10 * i for i in range(n)],
    }[label]
    return base[:n]


def build_workbook(path: Path, labels: list[str], n_rows: int) -> None:
    wb = openpyxl.load_workbook(SRC_WB)
    ws = wb["Resume Data"]
    col0 = 15
    for k, label in enumerate(labels):
        ws.cell(row=2, column=col0 + k, value=label)
        for i, v in enumerate(values_for(label, n_rows)):
            ws.cell(row=3 + i, column=col0 + k, value=v)
    wb.save(path)


def psql(sql: str, db: str = "postgres") -> str:
    return subprocess.run(["sudo", "-u", "hermes", f"{PSQL}/psql", "-h", "/tmp", "-p", "5432", "-d", db, "-tAc", sql],
                          capture_output=True, text=True, check=True).stdout.strip()


def fresh_db() -> None:
    psql(f"DROP DATABASE IF EXISTS {DB_NAME}")
    psql(f"CREATE DATABASE {DB_NAME}")
    migrate(URL)


def stage(repo, draft, run_id):
    sha = uuid.uuid4().hex + uuid.uuid4().hex
    repo.register_source(sha, f"cas:///sources/{run_id}.xlsx", 1000, actor="curator-sim")
    draft.source_uri, draft.file_sha256 = f"cas:///sources/{run_id}.xlsx", sha
    draft.base_versions = {k: ((repo.get_document(k) or {}).get("version") or 0) for k in draft.documents}
    return repo.stage(draft, expected_revision=0, actor="curator-sim")


def current_docs(repo, keys):
    out = {}
    for k in keys:
        raw = repo.get_document(k)
        if raw:
            raw = copy.deepcopy(raw)
            raw.pop("id", None)
            out[k] = KnowledgeDocument.model_validate(raw)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fresh_db()
    engine = make_engine(Settings(_env_file=None, database_url=URL))
    repo = DocumentRepository(engine)
    report: dict = {"db": DB_NAME, "kunci_jawaban": KEY}

    # ---------------------------------------------------------------- baseline: dokumen awal tanpa atribut baru
    base_path = out / "run0_baseline.xlsx"
    build_workbook(base_path, [], 0)
    planner = DocumentPlanner(extensions=repo.get_catalog_extensions())
    d0 = planner.plan_workbook(base_path, run_id="run0")
    pending0 = [r for r in d0.reviews if r.status == "pending"]
    report["baseline"] = {"dokumen": len(d0.documents), "review_pending": len(pending0),
                          "kategori": {c: sum(r.category == c for r in d0.reviews) for c in {r.category for r in d0.reviews}}}

    # ---------------------------------------------------------------- E-A1: akuisisi pada run 1
    n_rows = 6
    labels1 = list(KEY)
    wb1 = out / "run1_atribut_baru.xlsx"
    build_workbook(wb1, labels1, n_rows)
    d1 = DocumentPlanner(extensions=repo.get_catalog_extensions()).plan_workbook(wb1, run_id="run1")
    new1 = [r for r in d1.reviews if r.category == "NEW_ATTRIBUTE"]
    other1 = [r for r in d1.reviews if r.category != "NEW_ATTRIBUTE"]
    stage(repo, d1, "run1")
    by_label = {}
    for r in new1:
        by_label.setdefault(r.source_label, []).append(r)
    ea1 = {"label_baru_terdeteksi": sorted(by_label), "sel_review_baru": len(new1),
           "label_di_kunci": sorted(KEY), "terdeteksi_tepat": sorted(set(by_label) == set(KEY)) if False else set(by_label) == set(KEY)}
    # review non-NEW_ATTRIBUTE harus diselesaikan agar commit bisa; dibiarkan jika tidak ada
    ea1["review_lain_pending"] = len(other1)
    decisions = {}
    for label, items in by_label.items():
        dec = dict(KEY[label])
        dec["reason"] = "Keputusan kurator simulasi sesuai kunci jawaban"
        if dec["action"] == "REGISTER_NEW":
            dec["label"] = label
        res = repo.resolve_review("run1", items[0].item_id, dec, actor="curator-sim", actor_role="curator")
        decisions[label] = res["status"]
    ea1["status_item_pertama"] = decisions
    run1 = repo.get_run("run1")
    stat = {}
    for r in run1["draft"]["reviews"]:
        if r["category"] == "NEW_ATTRIBUTE":
            stat[r["status"]] = stat.get(r["status"], 0) + 1
    ea1["status_semua_sel"] = stat
    pending_left = [r for r in run1["draft"]["reviews"] if r["status"] == "pending"]
    ea1["review_lain_per_kategori"] = {c: sum(r["category"] == c for r in pending_left) for c in {r["category"] for r in pending_left}}
    # review di luar fitur (konflik antar baris pada data asli) ditutup netral agar commit dapat diuji; tidak menulis nilai
    for r in pending_left:
        repo.resolve_review("run1", r["item_id"], {"status": "rejected", "notes": "ditutup netral untuk uji fitur"},
                            actor="curator-sim", actor_role="curator")
    run1 = repo.get_run("run1")
    ea1["pending_sisa_sebelum_commit"] = sum(r["status"] == "pending" for r in run1["draft"]["reviews"])
    try:
        receipt = repo.commit("run1", run1["revision"], run1["payload_sha256"], actor="curator-sim")
        ea1["commit"] = {"dokumen_dibuat": receipt.documents_created, "atribut": receipt.attributes_committed}
    except Conflict as e:
        ea1["commit"] = f"DITOLAK: {e}"
    report["E-A1"] = ea1
    print("E-A1:", json.dumps(ea1, ensure_ascii=False, default=str), flush=True)

    # ---------------------------------------------------------------- E-A3: keutuhan setelah run 1
    ext = repo.get_catalog_extensions()
    ea3 = {"katalog_atribut_baru": [x.label for x in ext.attributes], "alias": ext.aliases, "ditolak": ext.rejected}
    doc_keys = list(d1.documents)
    sample = repo.get_document(doc_keys[0])
    attrs = sample["attributes"]
    ea3["atribut_asli_per_dokumen_baseline"] = {k: len(d0.documents[k].attributes) for k in d0.documents if k in d0.documents}
    ea3["atribut_total_per_dokumen_sesudah"] = {k: len(repo.get_document(k)["attributes"]) for k in doc_keys}
    ea3["atribut_baru_resolusi"] = sorted({v["resolution"] for k, v in attrs.items() if k.startswith(("attr_kadar_capsaicin", "attr_kandungan_vitamin", "attr_aroma_buah"))})
    ea3["alias_menulis_ke_atribut_tinggi"] = "attr_tinggi_tanaman" in attrs
    ea3["catatan_surveyor_tidak_tersimpan"] = not any("catatan" in k for k in attrs)
    with engine.connect() as c:
        ea3["baris_katalog"] = c.execute(text("SELECT count(*) FROM kms.attribute_catalog_ext")).scalar()
    try:
        with engine.begin() as c:
            c.execute(text("DELETE FROM kms.attribute_catalog_ext"))
        ea3["hapus_katalog_ditolak"] = False
    except Exception:
        ea3["hapus_katalog_ditolak"] = True
    replay = repo.commit("run1", run1["revision"], run1["payload_sha256"], actor="curator-sim")
    ea3["commit_ulang_idempoten"] = bool(replay.replayed)

    # ---------------------------------------------------------------- E-A2: penggunaan ulang pada run 2
    labels2 = labels1 + [NEAR_DUP_RUN2, NEW_LABEL_RUN2]
    wb2 = out / "run2_penggunaan_ulang.xlsx"
    build_workbook(wb2, labels2, n_rows)
    cd = current_docs(repo, doc_keys)
    d2 = DocumentPlanner(extensions=repo.get_catalog_extensions()).plan_workbook(wb2, run_id="run2", current_documents=cd)
    new2 = [r for r in d2.reviews if r.category == "NEW_ATTRIBUTE"]
    lab2 = sorted({r.source_label for r in new2})
    dec_labels = [l for l in KEY]
    reused = [l for l in dec_labels if l not in lab2]
    ea2 = {"label_diputuskan_run1": dec_labels, "label_ditanyakan_lagi_run2": lab2,
           "label_dikenali_otomatis": reused,
           "tingkat_penggunaan_ulang": round(len(reused) / len(dec_labels), 3),
           "review_baru_run2_sel": len(new2),
           "review_baru_run1_sel": len(new1)}
    near = next((r for r in new2 if r.source_label == NEAR_DUP_RUN2), None)
    ea2["label_mirip_terdeteksi_pada_item"] = (near.payload.get("similar_attributes") if near else None)
    attrs2 = {}
    for k, doc in d2.documents.items():
        for aid, av in doc.attributes.items():
            if aid.startswith(("attr_kadar_capsaicin", "attr_kandungan_vitamin", "attr_aroma_buah")):
                attrs2[aid] = av.resolution
    ea2["atribut_baru_tertulis_run2_resolusi"] = sorted(set(attrs2.values()))
    report["E-A2"] = ea2
    report["E-A3"] = ea3

    (out / "hasil_atribut_baru.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
