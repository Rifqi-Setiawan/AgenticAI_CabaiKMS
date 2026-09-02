"""Fase 8 — Halaman 2: Progres.

Status tiap agen, streaming log (dari run terakhir), dan status validasi
(berapa atribut/citra yang gagal kontrak atau ditandai untuk manual_review).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.ui import state

st.set_page_config(page_title="CABAI-KMS — Progres", page_icon="🌶️", layout="wide")
st.title("Halaman 2: Progres")

if state.is_running():
    st.warning("Pipeline sedang berjalan — halaman ini akan menunjukkan hasil setelah selesai.")

if not state.has_result():
    st.info("Belum ada pipeline yang dijalankan. Buka halaman **Input** untuk memulai.")
else:
    result = state.get_result()

    st.subheader("Status tiap agen")
    cols = st.columns(max(len(result.agent_status), 1))
    for col, (agent_name, status) in zip(cols, result.agent_status.items()):
        col.metric(agent_name, "OK" if "gagal" not in status.lower() else "GAGAL")
        col.caption(status)

    st.subheader("Status validasi")
    n_issues = len(result.error_trace)
    if n_issues == 0:
        st.success("Tidak ada atribut/citra yang ditandai untuk manual_review.")
    else:
        st.warning(f"{n_issues} entri ditandai untuk manual_review (lihat detail di bawah).")
        with st.expander("Detail error_trace"):
            for entry in result.error_trace:
                st.write(f"- {entry}")

    st.subheader("Log streaming")
    st.code("\n".join(state.get_log()) or "(log kosong)", language=None)
