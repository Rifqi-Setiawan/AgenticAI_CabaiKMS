"""The KMS document draft must come from the workbook of the current run (no sample fallback, no stale cache)."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest

from src.integrations import streamlit_commit as sc
from src.storage.attribute_policy import CatalogExtensions

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "samples" / "data_input.xlsx"


class _Run:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id


def _call(session: dict, run_id: str, source: bytes | None, filename: str = "x.xlsx"):
    last = {"filename": filename}
    if source is not None:
        last["source_bytes"] = source
    with patch("streamlit.session_state", session), \
            patch.object(sc, "fetch_catalog_extensions", return_value=CatalogExtensions()):
        return sc.get_or_create_draft(_Run(run_id), None, [], last)


def _sample_with_column(label: str) -> bytes:
    wb = openpyxl.load_workbook(SAMPLE)
    ws = wb["Resume Data"]
    ws.cell(row=2, column=15, value=label)
    for r in range(3, 8):
        ws.cell(row=r, column=15, value=100 + r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_missing_source_bytes_is_reported_not_faked():
    with pytest.raises(sc.DraftUnavailable):
        _call({}, "run_a", None)


def test_unsupported_layout_is_reported_not_replaced_by_sample():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Karakter", "Gendot", "Kopay"])
    ws.append(["habitus", "perdu", "tegak"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(sc.DraftUnavailable) as err:
        _call({}, "run_b", buf.getvalue())
    assert "belum didukung" in str(err.value)


def test_draft_comes_from_uploaded_workbook_and_cache_is_per_run():
    session: dict = {}
    source_c = _sample_with_column("Aroma Buah Segar")  # saved once: openpyxl embeds timestamps
    first = _call(session, "run_c", source_c)
    labels = {r.source_label for r in first.reviews if r.category == "NEW_ATTRIBUTE"}
    assert labels == {"Aroma Buah Segar"}
    assert _call(session, "run_c", source_c) is first  # same run and file: cached
    second = _call(session, "run_d", _sample_with_column("Kadar Gula Buah"))
    assert second is not first
    assert {r.source_label for r in second.reviews if r.category == "NEW_ATTRIBUTE"} == {"Kadar Gula Buah"}
