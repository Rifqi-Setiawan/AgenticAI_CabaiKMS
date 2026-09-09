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
from src.ui.demo_support import run_summary, safe_download_stem
from src.ui.review_replay import apply_review_corrections

st.set_page_config(page_title="CABAI-KMS — Hasil", page_icon="🌶️", layout="wide")
st.title("Halaman 3: Inspektor Hasil")

if not state.has_result():
    st.info("Belum ada pipeline yang dijalankan. Buka halaman **Input** untuk memulai.")
    st.stop()

result = state.get_result()
corrected_result = state.get_corrected_result()
schema = CanonicalSchema.from_template()
current_run_items = (
    review_queue.list_for_run(result.run_id, result.review_queue_path)
    if result.run_id and result.review_queue_path else []
)
pending_items = [item for item in current_run_items if item.status == "pending"]
last_inputs = state.get_last_inputs()
summary = run_summary(result, last_inputs, unresolved_review_count=len(pending_items))

st.subheader("Ringkasan run")
st.caption(
    f"Source: {summary['Source']} · Sheet: {summary['Sheet']} · Run: {summary['Run ID']} · "
    f"Backend: {summary['Source backend']} / {summary['Retrieval backend']}"
)
summary_keys = ["Mapped attributes", "AUTO_ACCEPT", "REVIEW", "NO_WRITE", "Unresolved reviews"]
for column, key in zip(st.columns(len(summary_keys)), summary_keys):
    column.metric(key, summary[key])
method_keys = ["Exact-name", "Retrieve-rerank", "Images discovered", "Vision processed", "Vision writes", "Vision non-writes"]
for column, key in zip(st.columns(len(method_keys)), method_keys):
    column.metric(key, summary[key])

st.subheader("Review manusia")
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
            st.write(f"**Alasan REVIEW:** {item.reason}")
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
            st.write("**Pilihan tindakan manusia:** setujui usulan, ubah target, atau tandai NO_MATCH.")
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
                st.error("Keputusan review gagal disimpan. Periksa pilihan dan identitas run aktif.")

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
                st.error("Replay koreksi gagal; output asli tetap tersedia. Lihat Advanced / Debug.")

st.subheader("Tabel keluaran terstandarisasi")
st.caption(
    "Bentuknya persis seperti data/canonical/template_kanonik.xlsx — baris "
    "kanonik yang sama (dibaca dinamis), kolom varietas dari sumber yang "
    "diunggah. Sel kosong berarti tidak ada atribut sumber yang berhasil "
    "dipetakan ke baris itu untuk varietas tersebut."
)
display_result = corrected_result or result
st.dataframe(display_result.canonical_df, width="stretch")

st.subheader("Inspektor pemetaan")
st.caption("Prediksi model tidak sama dengan write yang diterima. Periksa verifier, acceptance, dan canonical_write.")
if result.mapping_df.empty:
    st.write("(tidak ada atribut untuk dipetakan)")
else:
    st.dataframe(
        result.mapping_df[[
            "source_attribute_display", "predicted_label", "proposed_target_canonical_key",
            "mapping_method", "confidence", "verifier_status", "acceptance_status", "canonical_write",
        ]].rename(columns={
            "source_attribute_display": "Source attribute",
            "predicted_label": "Proposed canonical label",
            "proposed_target_canonical_key": "Proposed canonical key",
            "mapping_method": "Mapping method",
            "confidence": "Confidence",
            "verifier_status": "Verifier status",
            "acceptance_status": "Acceptance status",
            "canonical_write": "Canonical write",
        }),
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
        st.write(f"**Verifier:** {row['verifier_status']}")
        st.write(f"**Acceptance:** {row['acceptance_status']}")
        st.write(f"**Canonical write:** {row['canonical_write']}")
        st.write(f"**Normalisasi diperlukan:** {row['normalization_required']}")
        st.write(f"**Reasoning:** {row['reasoning']}")

st.subheader("Hasil multimodal")
drive_requested = bool(last_inputs.get("drive_url", "").strip())
if not drive_requested:
    st.info("Vision skipped — no Drive folder provided")
else:
    vision = pd.DataFrame(result.vision_rows)
    classified = sum(row.get("status") != "FAILED" for row in result.vision_rows)
    uncertain = sum(row.get("status") == "UNCERTAIN" for row in result.vision_rows)
    vision_counts = {
        "Images discovered": result.images_discovered,
        "Classified": classified,
        "Written": sum(bool(row.get("write_applied")) for row in result.vision_rows),
        "UNCERTAIN": uncertain,
        "Non-written": sum(not bool(row.get("write_applied")) for row in result.vision_rows),
    }
    for column, (label, value) in zip(st.columns(5), vision_counts.items()):
        column.metric(label, value)
    if vision.empty:
        st.info("Tidak ada citra yang menghasilkan baris klasifikasi.")
    else:
        vision = vision.rename(columns={"status": "classification_status"})
        visible = [
            "filename", "classification_status", "matched_variety", "identified_part",
            "confidence", "write_applied", "write_reason",
        ]
        st.dataframe(vision.reindex(columns=visible), width="stretch")

with st.expander("Advanced / Debug"):
    st.write(f"Evaluation fingerprint: `{result.evaluation_config_fingerprint or '-'}`")
    st.write(f"Template hash: `{result.template_hash or '-'}`")
    st.write(f"Checkpoint thread ID: `{result.checkpoint_thread_id or '-'}`")
    if result.error_trace:
        st.write("**Detailed error trace**")
        for entry in result.error_trace:
            st.write(f"- {entry}")
    if result.checkpoint_thread_id is None:
        st.info("Checkpoint debugger tidak tersedia untuk run ini; output tetap berhasil dibuat.")
    elif st.button("🔍 Buka Debugger Checkpoint"):
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

download_stem = safe_download_stem(last_inputs.get("filename", "hasil.xlsx"))
if corrected_result is not None:
    st.download_button(
        "⬇️ Unduh output terkoreksi (direkomendasikan)",
        data=corrected_result.workbook_bytes,
        file_name=f"{download_stem}_cabai_kms_corrected.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
st.download_button(
    "⬇️ Unduh hasil asli",
    data=result.workbook_bytes,
    file_name=f"{download_stem}_cabai_kms.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="secondary" if corrected_result is not None else "primary",
)
