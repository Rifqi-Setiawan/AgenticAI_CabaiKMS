from __future__ import annotations

import io
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest

from src.ui.demo_support import (
    inspect_xlsx_upload,
    run_summary,
    safe_download_stem,
    stage_state,
    validate_drive_input,
)


def _workbook_bytes(*names: str) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.title = names[0]
    for name in names[1:]:
        workbook.create_sheet(name)
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_preflight_reads_sheet_names_without_pipeline_execution():
    report = inspect_xlsx_upload("sample.xlsx", _workbook_bytes("First", "Second"))
    assert report.ready
    assert report.sheet_names == ("First", "Second")


def test_preflight_rejects_unsupported_or_invalid_workbook():
    assert "tidak didukung" in inspect_xlsx_upload("sample.csv", b"a,b").error
    assert "tidak dapat dibuka" in inspect_xlsx_upload("sample.xlsx", b"broken").error


def test_drive_preflight_is_local_and_plausibility_only():
    assert validate_drive_input("") is None
    assert validate_drive_input("https://drive.google.com/drive/folders/abc_123?usp=sharing") is None
    assert validate_drive_input("not a folder id") is not None


def test_summary_uses_mapping_decisions_and_vision_write_flags():
    mapping = pd.DataFrame({
        "acceptance_status": ["AUTO_ACCEPT", "REVIEW", "NO_WRITE"],
        "mapping_method": ["exact_name", "retrieve_rerank", "retrieve_rerank"],
    })
    result = SimpleNamespace(
        mapping_df=mapping,
        vision_rows=[{"write_applied": True}, {"write_applied": False}],
        images_discovered=3,
        run_id="1234567890abcdef",
        checkpoint_thread_id="1234567890abcdef",
        source_backend="legacy",
        retrieval_backend="chroma",
    )
    summary = run_summary(
        result, {"filename": "source.xlsx", "sheet_name": "Data"},
        unresolved_review_count=1,
    )
    assert summary["AUTO_ACCEPT"] == 1
    assert summary["REVIEW"] == 1
    assert summary["NO_WRITE"] == 1
    assert summary["Exact-name"] == 1
    assert summary["Retrieve-rerank"] == 2
    assert summary["Vision writes"] == 1
    assert summary["Vision non-writes"] == 1
    assert summary["Images discovered"] == 3


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("selesai — 13 atribut: 13 AUTO_ACCEPT, 0 REVIEW, 0 NO_WRITE", "SUCCESS"),
        ("selesai — 12 AUTO_ACCEPT, 1 REVIEW, 0 NO_WRITE", "WARNING"),
        ("selesai — 5 citra diklasifikasi, 5 ditulis ke sel, 0 UNCERTAIN", "SUCCESS"),
        ("selesai — 5 citra diklasifikasi, 4 ditulis ke sel, 1 UNCERTAIN", "WARNING"),
        ("dilewati (tidak ada folder Drive)", "SKIPPED"),
        ("dilewati (Drive gagal)", "SKIPPED"),
        ("gagal: access denied", "FAILED"),
        ("selesai dengan peringatan provider", "WARNING"),
    ],
)
def test_stage_classification(status, expected):
    assert stage_state(status) == expected


def test_safe_download_name():
    assert safe_download_stem("field demo (final).xlsx") == "field_demo_final"
