import io

import openpyxl
import pytest
from pandas.testing import assert_frame_equal

from src.agents.schema_matching.anchor import AnchorResult
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import SchemaMapping
from src.ui import pipeline_runner as runner
from src.ui.output_builder import worksheet_to_dataframe
from tests.test_source_parsing import flat_observations  # shared temporary workbook fixture


def test_flat_input_values_reach_downloaded_workbook(flat_observations, monkeypatch):
    """Run real parsing/grouping/normalization/Excel serialization, no API calls."""
    schema = CanonicalSchema.from_template()
    targets = {"Growth habit": "habitus", "Plant Height (cm)": "tinggi tanaman"}
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **kw: AnchorResult("found", "Variety", 1.0, "test"))
    monkeypatch.setattr(runner, "ensure_indexed", lambda *a, **kw: None)
    monkeypatch.setattr(runner, "retrieve", lambda *a, **kw: [])
    monkeypatch.setattr(runner, "run_pipeline", lambda *a, **kw: {})  # do not touch user checkpoints

    def mapping(profile, candidates, state, *, source_format, **kwargs):
        label = targets.get(profile.attribute_name)
        target = schema.row_by_label(label).id if label else "NULL"
        return SchemaMapping(
            source_attribute=profile.attribute_name, source_format=source_format,
            target_canonical_row=target, confidence=0.99,
            reasoning="Injected mapping: tests wiring, not model accuracy",
            normalization_required=True,
        ), {}

    monkeypatch.setattr(runner, "safe_rerank", mapping)
    result = runner.run_pipeline_ui(flat_observations)
    wb = openpyxl.load_workbook(io.BytesIO(result.workbook_bytes))
    try:
        ws = wb["Sheet1"]
        assert [ws.cell(1, c).value for c in range(3, 6)] == ["Domba", "Gendot", "Kopay"]
        row = next(c.row for c in ws["B"] if c.value == "habitus")
        assert [ws.cell(row, c).value for c in range(3, 6)] == ["terna", "perdu", "terna"]
        height_row = next(c.row for c in ws["B"] if c.value == "tinggi tanaman")
        assert ws.cell(height_row, 3).value  # first observation, previously lost
        assert ws.cell(height_row, 5).value is None
        downloaded = worksheet_to_dataframe(ws, schema, ["Domba", "Gendot", "Kopay"])
        assert_frame_equal(downloaded, result.canonical_df)
        assert "terna" not in result.mapping_df.source_attribute.tolist()
        assert result.mapping_df.source_attribute_display.tolist() == result.mapping_df.source_attribute.tolist()
    finally:
        wb.close()


def test_multilevel_duplicate_leaf_names_stay_distinct_through_export(tmp_path, monkeypatch):
    """A repeated leaf header is identified by its parent section, end to end."""
    source = tmp_path / "multilevel.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Identity", "Young Fruit", None, "Mature Fruit", None])
    ws.append(["Variety", "Fruit Length", "Position", "Fruit Length", "Position"])
    ws.append(["Domba", "3 cm", "pendant", "5 cm", "erect"])
    ws.merge_cells("B1:C1")
    ws.merge_cells("D1:E1")
    wb.save(source)
    wb.close()

    schema = CanonicalSchema.from_template()
    targets = {
        ("Young Fruit", "Fruit Length"): "panjang buah muda",
        ("Mature Fruit", "Fruit Length"): "panjang buah masak",
    }
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **kw: AnchorResult("found", "Variety", 1.0, "test"))
    monkeypatch.setattr(runner, "ensure_indexed", lambda *a, **kw: None)
    monkeypatch.setattr(runner, "retrieve", lambda *a, **kw: [])
    monkeypatch.setattr(runner, "run_pipeline", lambda *a, **kw: {})

    def mapping(profile, candidates, state, *, source_format, **kwargs):
        label = targets.get((profile.structural_context, profile.attribute_name))
        target = schema.row_by_label(label).id if label else "NULL"
        return SchemaMapping(
            source_attribute=profile.attribute_name,
            source_context=profile.structural_context,
            source_format=source_format,
            target_canonical_row=target,
            confidence=0.99,
            reasoning="Injected mapping: verifies structural context wiring",
            normalization_required=True,
        ), {}

    monkeypatch.setattr(runner, "safe_rerank", mapping)
    result = runner.run_pipeline_ui(source, header_rows=2)

    lengths = result.mapping_df[result.mapping_df.source_attribute == "Fruit Length"]
    assert lengths.source_attribute_display.tolist() == [
        "Young Fruit / Fruit Length",
        "Mature Fruit / Fruit Length",
    ]
    assert lengths.source_context.tolist() == ["Young Fruit", "Mature Fruit"]
    assert set(lengths.predicted_label) == {"panjang buah muda", "panjang buah masak"}

    exported = openpyxl.load_workbook(io.BytesIO(result.workbook_bytes))
    try:
        output = exported["Sheet1"]
        young_row = next(cell.row for cell in output["B"] if cell.value == "panjang buah muda")
        mature_row = next(cell.row for cell in output["B"] if cell.value == "panjang buah masak")
        assert output.cell(young_row, 3).value == "3 cm"
        assert output.cell(mature_row, 3).value == "5 cm"
    finally:
        exported.close()


def test_missing_anchor_stops_before_indexing_or_llm(flat_observations, monkeypatch):
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **kw: AnchorResult("escalate", None, 0.1, "test"))
    monkeypatch.setattr(runner, "ensure_indexed", lambda *a, **kw: pytest.fail("Must fail before indexing"))
    with pytest.raises(ValueError, match="Kolom varietas tidak ditemukan"):
        runner.run_pipeline_ui(flat_observations)


def test_missing_variety_value_stops_instead_of_losing_observation(flat_observations, monkeypatch):
    wb = openpyxl.load_workbook(flat_observations)
    wb.active["B2"] = " "
    wb.save(flat_observations)
    wb.close()
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **kw: AnchorResult("found", "Variety", 1.0, "test"))
    monkeypatch.setattr(runner, "ensure_indexed", lambda *a, **kw: pytest.fail("Must fail before indexing"))
    with pytest.raises(ValueError, match="Varietas kosong pada observasi ke-1"):
        runner.run_pipeline_ui(flat_observations)


def _isolate_pipeline(monkeypatch):
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **kw: AnchorResult("found", "Variety", 1.0, "test"))
    monkeypatch.setattr(runner, "ensure_indexed", lambda *a, **kw: None)
    monkeypatch.setattr(runner, "retrieve", lambda *a, **kw: [])
    monkeypatch.setattr(runner, "run_pipeline", lambda *a, **kw: {})


def _mapping(schema, attribute, row_id, confidence=0.99):
    return SchemaMapping(
        source_attribute=attribute,
        source_format="row-oriented",
        target_canonical_row=row_id,
        confidence=confidence,
        reasoning="pipeline safety-gate fixture",
        normalization_required=True,
    )


def test_review_mapping_never_normalizes_or_writes_but_later_attributes_do(
    flat_observations, monkeypatch,
):
    """Mixed workbook regression: ACCEPT, REVIEW, ACCEPT stay independent."""
    _isolate_pipeline(monkeypatch)
    schema = CanonicalSchema.from_template()
    accepted_rows = {
        "Sample_ID": schema.row_by_label("Lokasi").id,
        "Plant Height (cm)": schema.row_by_label("tinggi tanaman").id,
    }
    review_row = schema.row_by_label("habitus").id

    def safe_mapping(profile, candidates, state, *, source_format, **kwargs):
        if profile.attribute_name == "Growth habit":
            mapping = _mapping(schema, profile.attribute_name, review_row, confidence=0.1)
            return mapping, {"error_trace": ["confidence 0.10 di bawah ambang 0.6"]}
        return _mapping(schema, profile.attribute_name, accepted_rows[profile.attribute_name]), {}

    real_normalize = runner.normalize
    normalized_raw_values = []

    def normalize_spy(raw_value, target_row):
        normalized_raw_values.append(raw_value)
        return real_normalize(raw_value, target_row)

    monkeypatch.setattr(runner, "safe_rerank", safe_mapping)
    monkeypatch.setattr(runner, "normalize", normalize_spy)
    result = runner.run_pipeline_ui(flat_observations)

    review = result.mapping_df[result.mapping_df.source_attribute == "Growth habit"].iloc[0]
    later = result.mapping_df[result.mapping_df.source_attribute == "Plant Height (cm)"].iloc[0]
    assert review.acceptance_status == "REVIEW"
    assert review.canonical_write == False  # noqa: E712 - numpy bool comparison is intentional
    assert "confidence" in review.acceptance_reason
    assert not any("terna" in str(value) or "perdu" in str(value) for value in normalized_raw_values)
    assert result.canonical_df.loc[result.canonical_df.Karakter == "habitus", "Domba"].item() == ""
    assert later.acceptance_status == "AUTO_ACCEPT"
    assert later.canonical_write == True  # noqa: E712
    assert result.canonical_df.loc[result.canonical_df.Karakter == "tinggi tanaman", "Domba"].item() == "50--77 cm"


def test_structurally_invalid_result_is_observable_and_does_not_block_next_attribute(
    flat_observations, monkeypatch,
):
    _isolate_pipeline(monkeypatch)
    schema = CanonicalSchema.from_template()
    habitus_id = schema.row_by_label("habitus").id
    height_id = schema.row_by_label("tinggi tanaman").id

    def safe_mapping(profile, candidates, state, *, source_format, **kwargs):
        if profile.attribute_name == "Sample_ID":
            return None, {"error_trace": ["format invalid; diarahkan ke manual_review"]}
        target = habitus_id if profile.attribute_name == "Growth habit" else height_id
        return _mapping(schema, profile.attribute_name, target), {}

    monkeypatch.setattr(runner, "safe_rerank", safe_mapping)
    result = runner.run_pipeline_ui(flat_observations)

    invalid = result.mapping_df[result.mapping_df.source_attribute == "Sample_ID"].iloc[0]
    following = result.mapping_df[result.mapping_df.source_attribute == "Growth habit"].iloc[0]
    assert invalid.acceptance_status == "NO_WRITE"
    assert invalid.canonical_write == False  # noqa: E712
    assert "format invalid" in invalid.acceptance_reason
    assert following.acceptance_status == "AUTO_ACCEPT"
    assert following.canonical_write == True  # noqa: E712
    assert result.canonical_df.loc[result.canonical_df.Karakter == "habitus", "Domba"].item() == "terna"


def test_exact_alias_shortcut_still_writes_without_review(tmp_path, monkeypatch):
    source = tmp_path / "exact-alias.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variety", "Seeds per mature fruit"])
    ws.append(["Domba", "42"])
    wb.save(source)
    wb.close()

    _isolate_pipeline(monkeypatch)
    result = runner.run_pipeline_ui(source)

    row = result.mapping_df.iloc[0]
    assert row.acceptance_status == "AUTO_ACCEPT"
    assert row.canonical_write == True  # noqa: E712
    assert row.confidence == 1.0
    assert result.canonical_df.loc[
        result.canonical_df.Karakter == "jumlah biji/buah masak", "Domba"
    ].item() == "42"
