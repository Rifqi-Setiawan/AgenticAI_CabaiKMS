"""Fase 8 — Halaman 1: Input.

Upload workbook .xlsx + URL folder Google Drive (opsional) +
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
from src.ui.demo_support import (
    inspect_xlsx_upload,
    runtime_readiness,
    user_error_message,
    validate_drive_input,
)
from src.ui.pipeline_runner import run_pipeline_ui

st.set_page_config(page_title="CABAI-KMS Akuisisi", page_icon="🌶️", layout="wide")

st.title("🌶️ CABAI-KMS — Adaptive Knowledge Acquisition")
st.subheader("Halaman 1: Input")

st.markdown(
    "Unggah spreadsheet lapangan (format sesuai `data/samples/`), opsional "
    "berikan URL/ID folder Google Drive untuk citra, lalu jalankan pipeline."
)

uploaded_file = st.file_uploader("Workbook sumber (.xlsx)", type=["xlsx"])
uploaded_bytes = uploaded_file.getvalue() if uploaded_file is not None else b""
preflight = inspect_xlsx_upload(uploaded_file.name, uploaded_bytes) if uploaded_file is not None else None
selected_sheet = None
if preflight is not None:
    if preflight.error:
        st.error(preflight.error)
    elif len(preflight.sheet_names) > 1:
        selected_sheet = st.selectbox(
            "Worksheet yang diproses",
            options=list(preflight.sheet_names),
            index=0,
            help="Pemeriksaan ini hanya membaca daftar worksheet; schema matching belum dijalankan.",
        )
    else:
        selected_sheet = preflight.sheet_names[0]
        st.caption(f"Worksheet: `{selected_sheet}`")

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

max_images = st.number_input(
    "Maximum images to process",
    min_value=1,
    max_value=20,
    value=5,
    step=1,
    help="Batas ini diabaikan bila folder Drive dikosongkan.",
)
if not drive_url.strip():
    st.caption("Drive kosong: batas gambar diabaikan dan vision akan dilewati.")
drive_error = validate_drive_input(drive_url)
if drive_error:
    st.error(drive_error)

header_rows = None
if source_format == "row-oriented":
    header_choice = st.selectbox(
        "Jumlah baris header", ["Otomatis", "1 baris", "2 baris"],
        help=("Otomatis: header datar satu baris atau header bertingkat dengan merged cells. "
              "Pilih 2 baris secara manual untuk header bertingkat tanpa merged cells."),
    )
    header_rows = {"Otomatis": None, "1 baris": 1, "2 baris": 2}[header_choice]

st.subheader("Runtime readiness")
readiness = runtime_readiness(drive_requested=bool(drive_url.strip()))
ready_cols = st.columns(3)
for column, (label, value) in zip(ready_cols, readiness.items()):
    column.markdown(f"**{label}**")
    column.caption(value)
st.caption("Status konfigurasi saja; tidak ada network health check otomatis.")

preflight_ready = preflight is not None and preflight.ready and selected_sheet in preflight.sheet_names
run_clicked = st.button(
    "▶️ Jalankan Pipeline",
    type="primary",
    disabled=state.is_running() or not preflight_ready or drive_error is not None,
)

if run_clicked:
    if uploaded_file is None:
        st.error("Unggah spreadsheet sumber terlebih dahulu.")
    else:
        state.set_running(True)
        state.clear_log()
        state.clear_result()  # never offer an old/empty workbook after a failed new run
        state.set_last_inputs(
            filename=uploaded_file.name, source_format=source_format, drive_url=drive_url,
            header_rows=header_rows, sheet_name=selected_sheet, max_images=int(max_images),
        )

        suffix = Path(uploaded_file.name).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded_bytes)
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
                    sheet_name=selected_sheet,
                    header_rows=header_rows,
                    drive_folder_id=drive_url,
                    max_images=int(max_images),
                    on_progress=_on_progress,
                )
            state.set_result(result)
            st.success(
                "Pipeline selesai. Lihat halaman **Progres** untuk log lengkap, "
                "atau **Hasil** untuk tabel & unduhan."
            )
        except Exception as exc:  # noqa: BLE001 - normalize failures at the UI boundary
            safe_message = user_error_message(exc)
            st.error(safe_message)
            state.append_log(f"FATAL [{type(exc).__name__}]: {safe_message}")
        finally:
            state.set_running(False)
            tmp_path.unlink(missing_ok=True)

if state.has_result():
    last = state.get_last_inputs()
    st.info(f"Hasil terakhir: berkas `{last.get('filename', '-')}` — buka halaman Progres/Hasil di sidebar.")
