"""Fase 8 — Halaman 2: Progres.

Status tiap tahap, streaming log (dari run terakhir), dan catatan runtime
non-fatal seperti normalisasi, provider, atau alasan vision non-write.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.ui import state
from src.ui.demo_support import stage_state

st.set_page_config(page_title="CABAI-KMS — Progres", page_icon="🌶️", layout="wide")
st.title("Halaman 2: Progres")

if state.is_running():
    st.warning("Pipeline sedang berjalan — halaman ini akan menunjukkan hasil setelah selesai.")

if not state.has_result():
    st.info("Belum ada pipeline yang dijalankan. Buka halaman **Input** untuk memulai.")
else:
    result = state.get_result()

    st.subheader("Status tahap runtime")
    stages = [
        ("source_ingestion", "source_ingestion"),
        ("schema_matching/tabular", "schema_matching"),
        ("drive_crawler", "drive_crawler"),
        ("vision_classification", "vision_classification"),
        ("orchestrator/finalization", "orchestrator"),
    ]
    cols = st.columns(len(stages))
    for col, (label, key) in zip(cols, stages):
        status = result.agent_status.get(key, "dilewati (tidak ada status)")
        col.metric(label, stage_state(status))
        col.caption(status)

    st.subheader("Catatan runtime / peringatan")
    n_issues = len(result.error_trace)
    if n_issues == 0:
        st.success("Tidak ada catatan runtime atau peringatan tambahan.")
    else:
        st.warning(f"{n_issues} catatan runtime/peringatan tersedia di Advanced / Debug.")
        with st.expander("Advanced / Debug — error_trace"):
            for entry in result.error_trace:
                st.write(f"- {entry}")

    st.subheader("Log streaming")
    st.code("\n".join(state.get_log()) or "(log kosong)", language=None)
