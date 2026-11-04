"""Run pasangan spreadsheet asli (GRIN) + 160 foto Commons di VPS tanpa menulis ke KMS (4 Nov 2026).

Tahap:
  hitung  : jumlah baris setiap tabel skema kms (dipanggil sebelum dan sesudah run untuk membuktikan tidak ada tulisan).
  sheet   : proses G01/G02 lewat fungsi execute() harness produksi (eval/cabai-ui-experiment/harness_vps.py), sama dengan run
            atribut paper; antrean review dan checkpoint di folder sementara. KMS_DYNAMIC_SCHEMA harus 0 di environment.
Klasifikasi foto dijalankan terpisah dengan uji_visi_commons_vps.py --kanonik <hasil_asli.xlsx>.

Pemakaian (sebagai hermes, dari folder layanan, environment layanan dimuat, lalu KMS_DYNAMIC_SCHEMA=0):
  .venv-kms/bin/python grin_run_vps.py hitung <keluaran.json>
  .venv-kms/bin/python grin_run_vps.py sheet <folder_input> <folder_keluaran>
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/srv/hermes-control/services/agentic-ai-cabai-kms")
RUNS = [
    ("grin", "G01", "G01_grin_8_varietas_terdaftar.xlsx", "GRIN Capsicum", "row-oriented", 1, None, 5),
    ("grin", "G02", "G02_grin_11_varietas.xlsx", "GRIN Capsicum", "row-oriented", 1, None, 5),
]


def hitung(path):
    import sqlalchemy as sa
    e = sa.create_engine(os.environ["DATABASE_URL"])
    out = {}
    with e.connect() as c:
        for (t,) in c.execute(sa.text("select table_name from information_schema.tables where table_schema='kms' order by 1")):
            out[t] = c.execute(sa.text(f'select count(*) from kms."{t}"')).scalar()
    Path(path).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(path, sum(out.values()), "baris di", len(out), "tabel")


def sheet(inputs, out):
    if os.environ.get("KMS_DYNAMIC_SCHEMA", "").strip().lower() not in ("0", "false", "no", ""):
        raise SystemExit("KMS_DYNAMIC_SCHEMA harus 0 agar tidak membuat baris kanonik di KMS.")
    spec = importlib.util.spec_from_file_location("harness_vps", "/srv/hermes-control/eval/cabai-ui-experiment/harness_vps.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    for run in RUNS:
        h.execute(run, inputs, out, 1, 8)


if __name__ == "__main__":
    {"hitung": lambda: hitung(sys.argv[2]), "sheet": lambda: sheet(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
