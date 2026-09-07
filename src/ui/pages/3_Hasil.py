"""Fase 8 — Halaman 3: Inspektor Hasil.

Tabel keluaran terstandarisasi (persis bentuk
data/canonical/template_kanonik.xlsx — baris kanonik yang sama, kolom
varietas dari sumber yang diunggah), detail pemetaan (source attribute ->
canonical row + confidence + reasoning), alur review manusia, replay koreksi
deterministik, tombol buka debugger checkpoint, serta unduhan workbook asli
dan hasil koreksi.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from src.agents.schema_matching import review_queue
from src.orchestrator.graph import DEFAULT_CHECKPOINT_DB, _sqlite_checkpointer
from src.schema.canonical import CanonicalSchema
from src.ui import state
from src.ui.review_replay import apply_review_corrections

st.set_page_config(page_title="CABAI-KMS — Hasil", page_icon="🌶️", layout="wide")
st.title("Halaman 3: Inspektor Hasil")

if not state.has_result():
    st.info("Belum ada pipeline yang dijalankan. Buka halaman **Input** untuk memulai.")
    st.stop()

result = state.get_result()
corrected_result = state.get_corrected_result()

st.subheader("Review manusia")
schema = CanonicalSchema.from_template()
current_run_items = (
    review_queue.list_for_run(result.run_id, result.review_queue_path)
    if result.run_id and result.review_queue_path else []
)
pending_items = [item for item in current_run_items if item.status == "pending"]
if not current_run_items:
    st.success("Run ini tidak memiliki mapping berstatus REVIEW.")
else:
    st.caption(
        "Review hanya menampilkan item dari run aktif. Keputusan disimpan sebagai event "
        "append-only dan diterapkan tanpa menjalankan retrieval, reranker, verifier, atau vision lagi."
    )
    reviewer = st.text_input("Reviewer", key="review_resolved_by", placeholder="nama atau ID reviewer")
    for item in current_run_items:
        display = item.source_attribute_display or item.mapping.source_attribute
        with st.expander(f"{item.status.upper()} — {display}", expanded=item.status == "pending"):
            if item.mapping.source_context:
                st.write(f"**Konteks:** {item.mapping.source_context}")
            if item.sample_values:
                st.write(f"**Contoh nilai:** {', '.join(item.sample_values[:10])}")
            proposed = schema.row_by_key(item.proposed_canonical_key or "")
            proposed_text = (
                f"{proposed.label} ({proposed.domain})" if proposed else "Tidak ada target (NULL)"
            )
            st.write(f"**Usulan AI:** {proposed_text}")
            st.write(f"**Confidence:** {item.mapping.confidence:.2f}")
            st.write(f"**Metode:** {item.mapping_method or '-'}")
            st.write(f"**Verifier:** {item.verifier_status or '-'}")
            if item.verifier_warnings:
                st.write(f"**Peringatan:** {', '.join(item.verifier_warnings)}")
            if item.status != "pending":
                final = schema.row_by_key(item.final_canonical_key or "")
                final_text = f"{final.label} ({final.domain})" if final else "NO_MATCH"
                st.write(f"**Keputusan akhir:** {final_text}")
                st.write(f"**Diselesaikan oleh:** {item.resolved_by or '-'}")
                continue
            notes = st.text_input("Catatan (opsional)", key=f"notes_{item.item_id}")
            selected_key = st.selectbox(
                "Target kanonik pengganti",
                options=[row.canonical_key for row in schema.rows],
                format_func=lambda key: (
                    f"{schema.row_by_key(key).label} — {schema.row_by_key(key).domain} [{key}]"
                ),
                key=f"target_{item.item_id}",
            )
            approve_col, revise_col, no_match_col = st.columns(3)
            try:
                if approve_col.button(
                    "Setujui usulan", key=f"approve_{item.item_id}",
                    disabled=proposed is None,
                ):
                    review_queue.approve(
                        item.item_id, resolved_by=reviewer or None, notes=notes or None,
                        expected_run_id=result.run_id, queue_path=result.review_queue_path,
                    )
                    state.clear_corrected_result()
                    st.rerun()
                if revise_col.button("Ubah target", key=f"revise_{item.item_id}"):
                    review_queue.revise_to_canonical_key(
                        item.item_id, selected_key, schema=schema,
                        resolved_by=reviewer or None, notes=notes or None,
                        expected_run_id=result.run_id, queue_path=result.review_queue_path,
                    )
                    state.clear_corrected_result()
                    st.rerun()
                if no_match_col.button("Tandai NO_MATCH", key=f"no_match_{item.item_id}"):
                    review_queue.mark_no_match(
                        item.item_id, resolved_by=reviewer or None, notes=notes or None,
                        expected_run_id=result.run_id, queue_path=result.review_queue_path,
                    )
                    state.clear_corrected_result()
                    st.rerun()
            except Exception as exc:  # noqa: BLE001 - preserve queue and original result
                st.error(f"Keputusan review gagal disimpan: {exc}")

    if pending_items:
        st.warning(f"{len(pending_items)} item REVIEW masih PENDING.")
    else:
        if st.button("Terapkan Koreksi", type="primary"):
            try:
                corrected_result = apply_review_corrections(result)
                state.set_corrected_result(corrected_result)
                st.success("Koreksi berhasil diterapkan dari output asli tanpa menjalankan model lagi.")
            except Exception as exc:  # noqa: BLE001 - original result remains downloadable
                state.clear_corrected_result()
                st.error(f"Replay koreksi gagal; output asli tetap tersedia: {exc}")

st.subheader("Tabel keluaran terstandarisasi")
st.caption(
    "Bentuknya persis seperti data/canonical/template_kanonik.xlsx — baris "
    "kanonik yang sama (dibaca dinamis), kolom varietas dari sumber yang "
    "diunggah. Sel kosong berarti tidak ada atribut sumber yang berhasil "
    "dipetakan ke baris itu untuk varietas tersebut."
)
display_result = corrected_result or result
st.dataframe(display_result.canonical_df, width="stretch")

st.subheader("Detail pemetaan (source attribute → canonical row)")
if result.mapping_df.empty:
    st.write("(tidak ada atribut untuk dipetakan)")
else:
    st.dataframe(
        result.mapping_df[["source_attribute_display", "predicted_row", "predicted_label", "target_domain", "confidence"]]
        .rename(columns={"source_attribute_display": "source_attribute"}),
        width="stretch",
    )
    chosen = st.selectbox(
        "Lihat reasoning lengkap untuk atribut:", result.mapping_df["source_attribute_display"]
    )
    row = result.mapping_df.loc[result.mapping_df["source_attribute_display"] == chosen].iloc[0]
    with st.expander(f"Reasoning: {chosen}", expanded=True):
        if row["source_context"]:
            st.write(f"**Konteks header:** {row['source_context']}")
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
st.caption("Output asli selalu dipertahankan. Output terkoreksi dibuat ulang dari basis asli setelah semua review selesai.")

st.download_button(
    "⬇️ Unduh hasil asli",
    data=result.workbook_bytes,
    file_name="hasil_akuisisi.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
if corrected_result is not None:
    st.download_button(
        "⬇️ Unduh output terkoreksi",
        data=corrected_result.workbook_bytes,
        file_name="hasil_akuisisi_terkoreksi.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
