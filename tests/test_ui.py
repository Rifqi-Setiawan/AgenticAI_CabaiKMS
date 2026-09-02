from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ui.pipeline_runner import PipelineRunResult

APP_PATH = "src/ui/app.py"
PROGRESS_PATH = "src/ui/pages/2_Progress.py"
HASIL_PATH = "src/ui/pages/3_Hasil.py"

# app.py's import chain now pulls in the full pipeline stack (torch,
# transformers, langgraph, chromadb, google api client, ...) — the
# default 3s AppTest timeout is comfortably enough once warm, but a
# cold run reliably exceeds it.
APP_TEST_TIMEOUT = 30


def _fixture_result(with_issues: bool = False) -> PipelineRunResult:
    mapping_df = pd.DataFrame(
        [
            {
                "source_attribute": "Warna Daun",
                "predicted_row": "r_7",
                "predicted_label": "warna daun",
                "target_domain": "daun",
                "confidence": 0.9,
                "normalization_required": False,
                "reasoning": "cocok jelas dengan label 'warna daun'",
            },
            {
                "source_attribute": "Panjang Daun",
                "predicted_row": "r_8",
                "predicted_label": "panjang daun",
                "target_domain": "daun",
                "confidence": 0.85,
                "normalization_required": True,
                "reasoning": "cocok dengan tipe data numerik",
            },
        ]
    )
    canonical_df = pd.DataFrame(
        [
            {"Nomor": 1, "Karakter": "habitus", "Gendot": "perdu", "Kopay": "terna"},
            {"Nomor": 7, "Karakter": "warna daun", "Gendot": "green group 137 A", "Kopay": ""},
            {"Nomor": 8, "Karakter": "panjang daun", "Gendot": "10--12 cm", "Kopay": "8--10 cm"},
        ]
    )
    vision_rows = [
        {
            "filename": "daun1.jpg", "status": "KNOWN", "matched_variety": "Gendot",
            "identified_part": "DAUN", "confidence": 0.9, "visual_evidence": "ok",
        }
    ]
    error_trace = ["contoh entri error_trace"] if with_issues else []
    return PipelineRunResult(
        mapping_df=mapping_df,
        canonical_df=canonical_df,
        workbook_bytes=b"fake-xlsx-bytes-for-ui-tests",
        vision_rows=vision_rows,
        agent_status={
            "schema_matching": "selesai — 2 dipetakan, 0 review",
            "vision_classification": "selesai — 1 citra diklasifikasi, 0 UNCERTAIN",
            "orchestrator": "checkpoint tersimpan (thread_id=test-thread-fixture)",
        },
        checkpoint_thread_id="test-thread-fixture-nonexistent",
        error_trace=error_trace,
    )


class TestPage1Input:
    def test_renders_without_exception(self):
        at = AppTest.from_file(APP_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.run()
        assert not at.exception

    def test_has_upload_and_drive_inputs_and_run_button(self):
        at = AppTest.from_file(APP_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.run()
        assert len(at.text_input) >= 1
        assert len(at.radio) >= 1
        assert any("Jalankan Pipeline" in b.label for b in at.button)

    def test_run_without_file_shows_error(self):
        at = AppTest.from_file(APP_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.run()
        run_button = next(b for b in at.button if "Jalankan Pipeline" in b.label)
        run_button.click().run()
        assert not at.exception
        assert any("Unggah spreadsheet" in e.value for e in at.error)

    def test_shows_last_result_hint_when_result_exists(self):
        at = AppTest.from_file(APP_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result()
        at.session_state["cabai_kms_inputs"] = {"filename": "contoh.xlsx"}
        at.run()
        assert not at.exception
        assert any("contoh.xlsx" in i.value for i in at.info)


class TestPage2Progress:
    def test_empty_state_shows_info(self):
        at = AppTest.from_file(PROGRESS_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.run()
        assert not at.exception
        assert any("Belum ada pipeline" in i.value for i in at.info)

    def test_with_result_shows_agent_metrics_and_log(self):
        at = AppTest.from_file(PROGRESS_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result()
        at.session_state["cabai_kms_log"] = ["mulai...", "schema_matching: ...", "selesai."]
        at.run()
        assert not at.exception
        metric_labels = [m.label for m in at.metric]
        assert "schema_matching" in metric_labels
        assert "vision_classification" in metric_labels
        assert any("selesai." in c.value for c in at.code)

    def test_no_issues_shows_success(self):
        at = AppTest.from_file(PROGRESS_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result(with_issues=False)
        at.run()
        assert not at.exception
        assert any("Tidak ada" in s.value for s in at.success)

    def test_with_issues_shows_warning(self):
        at = AppTest.from_file(PROGRESS_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result(with_issues=True)
        at.run()
        assert not at.exception
        assert any("ditandai untuk manual_review" in w.value for w in at.warning)


class TestPage3Hasil:
    def test_empty_state_shows_info_and_stops(self):
        at = AppTest.from_file(HASIL_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.run()
        assert not at.exception
        assert any("Belum ada pipeline" in i.value for i in at.info)
        assert len(at.dataframe) == 0  # st.stop() reached, nothing below rendered

    def test_with_result_shows_tables_and_download_button(self):
        at = AppTest.from_file(HASIL_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result()
        at.run()
        assert not at.exception
        assert len(at.dataframe) >= 2  # canonical + mapping (+ vision)
        assert any("Unduh hasil" in b.label for b in list(at.button) + list(at.download_button))

    def test_reasoning_selectbox_shows_full_reasoning_on_selection(self):
        at = AppTest.from_file(HASIL_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result()
        at.run()
        select = at.selectbox[0]
        select.select("Panjang Daun").run()
        assert not at.exception
        assert any("cocok dengan tipe data numerik" in md.value for md in at.markdown)

    def test_checkpoint_debugger_button_does_not_crash_on_unknown_thread(self):
        at = AppTest.from_file(HASIL_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = _fixture_result()
        at.run()
        debugger_button = next(b for b in at.button if "Debugger Checkpoint" in b.label)
        debugger_button.click().run()
        assert not at.exception
        assert any("checkpoint tersimpan" in w.value for w in list(at.markdown) + list(at.text))
