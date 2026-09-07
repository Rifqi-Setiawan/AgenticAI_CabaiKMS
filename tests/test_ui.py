from __future__ import annotations

import io

import openpyxl
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.ui.pipeline_runner import PipelineRunResult
from src.agents.schema_matching import review_queue
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping
from src.ui.output_builder import CanonicalOutputBuilder, worksheet_to_dataframe
from src.ui.pipeline_runner import _deterministic_workbook_bytes

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
                "source_attribute_display": "Warna Daun",
                "source_attribute": "Warna Daun",
                "source_context": None,
                "predicted_row": "r_7",
                "predicted_label": "warna daun",
                "target_domain": "daun",
                "confidence": 0.9,
                "normalization_required": False,
                "reasoning": "cocok jelas dengan label 'warna daun'",
            },
            {
                "source_attribute_display": "Panjang Daun",
                "source_attribute": "Panjang Daun",
                "source_context": None,
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


def _real_null_review_result(tmp_path) -> tuple[PipelineRunResult, str]:
    schema = CanonicalSchema.from_template()
    queue_path = tmp_path / "review.jsonl"
    run_id = "ui-replay-run"
    source_hash = "b" * 64
    mapping = SchemaMapping(
        source_attribute="Growth habit", source_context="Vegetative",
        source_format="row-oriented", target_canonical_row=NULL_ROW,
        confidence=0.2, reasoning="no confident model proposal",
        normalization_required=True,
    )
    item = review_queue.enqueue(
        mapping, reason="needs review", queue_path=queue_path,
        run_id=run_id, mapping_item_id="mapping-ui-replay",
        source_file_name="source.xlsx", source_file_sha256=source_hash,
        source_sheet="Observations", source_format="row-oriented",
        source_attribute_display="Vegetative / Growth habit",
        schema_version=schema.schema_version, template_hash=schema.template_hash,
        proposed_canonical_key=None, mapping_method="retrieve_rerank",
        verifier_status="REVIEW", sample_values=["terna"],
        raw_values_by_variety={"Domba": ["terna"]},
    )
    builder = CanonicalOutputBuilder(schema=schema, variety_names=["Domba"])
    workbook = builder.build_workbook()
    try:
        workbook_bytes = _deterministic_workbook_bytes(workbook)
        canonical_df = worksheet_to_dataframe(workbook["Sheet1"], schema, ["Domba"])
    finally:
        workbook.close()
    mapping_df = pd.DataFrame([{
        "review_item_id": item.item_id,
        "mapping_item_id": "mapping-ui-replay",
        "source_file_sha256": source_hash,
        "source_sheet": "Observations",
        "source_format": "row-oriented",
        "source_attribute_display": "Vegetative / Growth habit",
        "source_attribute": "Growth habit",
        "source_context": "Vegetative",
        "predicted_row": NULL_ROW,
        "predicted_label": "NULL",
        "target_domain": None,
        "confidence": 0.2,
        "normalization_required": True,
        "reasoning": "no confident model proposal",
        "canonical_write": False,
        "proposed_target_canonical_key": None,
    }])
    return PipelineRunResult(
        mapping_df=mapping_df, canonical_df=canonical_df,
        workbook_bytes=workbook_bytes, vision_rows=[], run_id=run_id,
        checkpoint_thread_id=run_id, review_queue_path=str(queue_path),
        schema_version=schema.schema_version, template_hash=schema.template_hash,
    ), schema.row_by_label("habitus").canonical_key


class TestPage1Input:
    def test_header_selection_only_for_row_oriented(self):
        at = AppTest.from_file(APP_PATH, default_timeout=APP_TEST_TIMEOUT).run()
        assert at.selectbox[0].options == ["Otomatis", "1 baris", "2 baris"]
        at.selectbox[0].select("2 baris").run()
        assert not at.exception
        at.radio[0].set_value("transposed").run()
        assert not at.selectbox

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

    def test_current_run_review_item_shows_human_actions_and_canonical_selector(self, tmp_path):
        schema = CanonicalSchema.from_template()
        result = _fixture_result()
        result.run_id = "ui-current-run"
        result.schema_version = schema.schema_version
        result.template_hash = schema.template_hash
        result.review_queue_path = str(tmp_path / "review.jsonl")
        mapping = SchemaMapping(
            source_attribute="Warna Daun", source_context="Daun",
            source_format="row-oriented", target_canonical_row=schema.row_by_label("warna daun").id,
            confidence=0.2, reasoning="needs review", normalization_required=False,
        )
        item = review_queue.enqueue(
            mapping, reason="needs review", queue_path=result.review_queue_path,
            run_id=result.run_id, mapping_item_id="mapping-ui",
            source_file_name="source.xlsx", source_file_sha256="a" * 64,
            source_sheet="Sheet1", source_format="row-oriented",
            source_attribute_display="Daun / Warna Daun",
            schema_version=schema.schema_version, template_hash=schema.template_hash,
            proposed_canonical_key=schema.row_by_label("warna daun").canonical_key,
            mapping_method="retrieve_rerank", verifier_status="REVIEW",
            sample_values=["hijau"], raw_values_by_variety={"Gendot": ["hijau"]},
        )
        result.mapping_df["review_item_id"] = [item.item_id, None]
        at = AppTest.from_file(HASIL_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = result
        at.run()
        assert not at.exception
        labels = [button.label for button in at.button]
        assert "Setujui usulan" in labels
        assert "Ubah target" in labels
        assert "Tandai NO_MATCH" in labels
        assert any("warna daun" in str(option) for option in at.selectbox[0].options)

    def test_revise_and_apply_correction_end_to_end(self, tmp_path):
        result, replacement_key = _real_null_review_result(tmp_path)
        at = AppTest.from_file(HASIL_PATH, default_timeout=APP_TEST_TIMEOUT)
        at.session_state["cabai_kms_pipeline_result"] = result
        at.run()

        assert not at.exception
        assert any(
            "Vegetative / Growth habit" in expander.label
            for expander in at.expander
        )
        assert len(review_queue.list_pending(
            queue_path=result.review_queue_path, run_id=result.run_id,
        )) == 1
        at.selectbox[0].select(replacement_key).run()
        next(button for button in at.button if button.label == "Ubah target").click().run()

        assert not at.exception
        assert review_queue.list_pending(
            queue_path=result.review_queue_path, run_id=result.run_id,
        ) == []
        next(button for button in at.button if button.label == "Terapkan Koreksi").click().run()

        assert not at.exception
        corrected = at.session_state["cabai_kms_corrected_pipeline_result"]
        workbook = openpyxl.load_workbook(io.BytesIO(corrected.workbook_bytes), data_only=True)
        try:
            assert "Sheet1" in workbook.sheetnames
            assert workbook["Sheet1"]["C1"].value == "Domba"
        finally:
            workbook.close()
        habitus = corrected.canonical_df.loc[
            corrected.canonical_df["Karakter"] == "habitus", "Domba"
        ].item()
        assert habitus == "terna"
        assert any(
            button.label == "⬇️ Unduh output terkoreksi"
            for button in at.download_button
        )
