"""Fase 8 — Halaman 3: Inspektor Hasil.

Tabel keluaran terstandarisasi (persis bentuk
data/canonical/template_kanonik.xlsx — baris kanonik yang sama, kolom
varietas dari sumber yang diunggah), detail pemetaan (source attribute ->
canonical row + confidence + reasoning), tombol buka debugger checkpoint,
dan unduh hasil akhir sebagai Excel (workbook aslinya, bukan yang dibangun
ulang — lihat src/ui/output_builder.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from src.orchestrator.graph import DEFAULT_CHECKPOINT_DB, _sqlite_checkpointer
from src.ui import state

st.set_page_config(page_title="CABAI-KMS — Hasil", page_icon="🌶️", layout="wide")
st.title("Halaman 3: Inspektor Hasil")

if not state.has_result():
    st.info("Belum ada pipeline yang dijalankan. Buka halaman **Input** untuk memulai.")
    st.stop()

result = state.get_result()

st.subheader("Tabel keluaran terstandarisasi")
st.caption(
    "Bentuknya persis seperti data/canonical/template_kanonik.xlsx — baris "
    "kanonik yang sama (dibaca dinamis), kolom varietas dari sumber yang "
    "diunggah. Sel kosong berarti tidak ada atribut sumber yang berhasil "
    "dipetakan ke baris itu untuk varietas tersebut."
)
st.dataframe(result.canonical_df, width="stretch")

st.subheader("Detail pemetaan (source attribute → canonical row)")
if result.mapping_df.empty:
    st.write("(tidak ada atribut untuk dipetakan)")
else:
    st.dataframe(
        result.mapping_df[["source_attribute", "predicted_row", "predicted_label", "target_domain", "confidence"]],
        width="stretch",
    )
    chosen = st.selectbox("Lihat reasoning lengkap untuk atribut:", result.mapping_df["source_attribute"])
    row = result.mapping_df.loc[result.mapping_df["source_attribute"] == chosen].iloc[0]
    with st.expander(f"Reasoning: {chosen}", expanded=True):
        st.write(f"**Target baris kanonik:** {row['predicted_row']} ({row['predicted_label']})")
        st.write(f"**Domain:** {row['target_domain']}")
        st.write(f"**Confidence:** {row['confidence']:.2f}")
        st.write(f"**Normalisasi diperlukan:** {row['normalization_required']}")
        st.write(f"**Reasoning:** {row['reasoning']}")

if result.vision_rows:
    st.subheader("Hasil klasifikasi citra")
    st.dataframe(pd.DataFrame(result.vision_rows), width="stretch")

st.subheader("Debugger checkpoint")
if st.button("🔍 Buka Debugger Checkpoint"):
    with _sqlite_checkpointer(DEFAULT_CHECKPOINT_DB) as checkpointer:
        checkpoints = list(
            checkpointer.list({"configurable": {"thread_id": result.checkpoint_thread_id}})
        )
    st.write(f"Thread ID: `{result.checkpoint_thread_id}` — {len(checkpoints)} checkpoint tersimpan.")
    for i, cp in enumerate(checkpoints):
        with st.expander(f"Checkpoint #{i + 1} — {cp.checkpoint.get('ts', '?')}"):
            st.json(
                {
                    "channel_values_keys": list(cp.checkpoint.get("channel_values", {}).keys()),
                    "config": cp.config,
                }
            )

st.subheader("Unduh hasil akhir")
st.caption("Berkas .xlsx ini adalah workbook aslinya — instans nyata dari template_kanonik.xlsx.")

st.download_button(
    "⬇️ Unduh hasil sebagai Excel",
    data=result.workbook_bytes,
    file_name="hasil_akuisisi.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
