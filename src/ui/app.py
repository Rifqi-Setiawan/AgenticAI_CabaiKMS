"""Fase 8 — Halaman 1: Input.

Upload spreadsheet (.xlsx/.csv) + URL folder Google Drive (opsional) +
tombol "Jalankan Pipeline". This is the landing page of the Streamlit app
(`streamlit run src/ui/app.py`); Progres and Hasil are the two pages under
src/ui/pages/, reachable from the sidebar Streamlit adds automatically.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))  # allow `streamlit run src/ui/app.py` from anywhere

import streamlit as st

from src.ui import state
from src.ui.pipeline_runner import run_pipeline_ui

st.set_page_config(page_title="CABAI-KMS Akuisisi", page_icon="🌶️", layout="wide")

st.title("🌶️ CABAI-KMS — Adaptive Knowledge Acquisition")
st.subheader("Halaman 1: Input")

st.markdown(
    "Unggah spreadsheet lapangan (format sesuai `data/samples/`), opsional "
    "berikan URL/ID folder Google Drive untuk citra, lalu jalankan pipeline."
)

uploaded_file = st.file_uploader("Spreadsheet sumber (.xlsx atau .csv)", type=["xlsx", "csv"])

col1, col2 = st.columns(2)
with col1:
    source_format = st.radio(
        "Format sumber",
        options=["row-oriented", "transposed"],
        help=(
            "row-oriented: satu baris = satu pengamatan, varietas ada di kolom "
            "'jenis cabai' (seperti data_input.xlsx). "
            "transposed: varietas sudah jadi header kolom (seperti "
            "sample_transposed_sintetis.xlsx)."
        ),
    )
with col2:
    drive_url = st.text_input(
        "URL atau ID folder Google Drive (opsional)",
        placeholder="https://drive.google.com/drive/folders/... atau ID folder",
        help="Jika kosong, tahap vision_classification akan dilewati.",
    )

run_clicked = st.button("▶️ Jalankan Pipeline", type="primary", disabled=state.is_running())

if run_clicked:
    if uploaded_file is None:
        st.error("Unggah spreadsheet sumber terlebih dahulu.")
    else:
        state.set_running(True)
        state.clear_log()
        state.set_last_inputs(
            filename=uploaded_file.name, source_format=source_format, drive_url=drive_url
        )

        suffix = Path(uploaded_file.name).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = Path(tmp.name)

        log_placeholder = st.empty()

        def _on_progress(message: str) -> None:
            state.append_log(message)
            log_placeholder.code("\n".join(state.get_log()), language=None)

        try:
            with st.spinner("Menjalankan pipeline..."):
                result = run_pipeline_ui(
                    tmp_path,
                    source_format=source_format,
                    drive_folder_id=drive_url,
                    on_progress=_on_progress,
                )
            state.set_result(result)
            st.success(
                "Pipeline selesai. Lihat halaman **Progres** untuk log lengkap, "
                "atau **Hasil** untuk tabel & unduhan."
            )
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user, don't crash the app
            st.error(f"Pipeline gagal: {exc}")
            state.append_log(f"FATAL: {exc}")
        finally:
            state.set_running(False)
            tmp_path.unlink(missing_ok=True)

if state.has_result():
    last = state.get_last_inputs()
    st.info(f"Hasil terakhir: berkas `{last.get('filename', '-')}` — buka halaman Progres/Hasil di sidebar.")
