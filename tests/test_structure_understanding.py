import openpyxl

from src.ingestion.structure_evidence import MAX_INITIAL_CELLS, build_initial_evidence
from src.ingestion.structure_understanding import MAX_EVIDENCE_ROUNDS, understand_sheet_structure
from src.ingestion.workbook_profiler import profile_workbook
from src.schema.structure import StructureProposal


def _sheet(tmp_path, *, rows=5, columns=4):
    path = tmp_path / "agent.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in range(1, rows + 1):
        ws.append([f"r{row}c{column}" for column in range(1, columns + 1)])
    wb.save(path)
    wb.close()
    return profile_workbook(path).sheets[0]


def _resolved_row():
    return StructureProposal(
        status="RESOLVED",
        orientation="row-oriented",
        row_oriented={
            "table_range": "A1:D5",
            "header_rows": [1],
            "data_start_row": 2,
            "data_end_row": 5,
            "attribute_columns": ["A", "B", "C", "D"],
            "header_bindings": [
                {"column_letter": column, "header_cells": [f"{column}1"]}
                for column in "ABCD"
            ],
        },
        confidence=0.8,
        evidence_summary="First row is header.",
    )


class QueueLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_resolved_proposal_is_verified(tmp_path):
    llm = QueueLLM(_resolved_row())
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=llm)
    assert result.verified_structure is not None
    assert result.verification and result.verification.valid
    assert len(llm.calls) == 1
    assert llm.calls[0]["response_model"] is StructureProposal


def test_resolved_transposed_proposal_is_verified(tmp_path):
    proposal = StructureProposal(
        status="RESOLVED",
        orientation="transposed",
        transposed={
            "table_range": "A1:D5",
            "header_row": 1,
            "label_column": "A",
            "data_columns": ["B", "C", "D"],
            "attribute_start_row": 2,
            "attribute_end_row": 5,
        },
        confidence=0.7,
        evidence_summary="Columns B-D are entities.",
    )
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=QueueLLM(proposal))
    assert result.verified_structure is not None
    assert result.verification and result.verification.verified_orientation == "transposed"


def test_targeted_evidence_then_resolution(tmp_path):
    need = StructureProposal(
        status="NEED_MORE_EVIDENCE",
        requested_ranges=["A1:D5"],
        confidence=0.4,
        evidence_summary="Need the table grid.",
    )
    llm = QueueLLM(need, _resolved_row())
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=llm)
    assert result.verified_structure is not None
    assert result.evidence_rounds == 1
    assert result.requested_ranges_history == [["A1:D5"]]
    assert '"is_blank"' in llm.calls[1]["messages"][1]["content"]


def test_targeted_evidence_accumulates_with_round_labels(tmp_path):
    first = StructureProposal(
        status="NEED_MORE_EVIDENCE",
        requested_ranges=["A1:B3"],
        confidence=0.3,
        evidence_summary="Need the left block.",
    )
    second = StructureProposal(
        status="NEED_MORE_EVIDENCE",
        requested_ranges=["D1:E3"],
        confidence=0.5,
        evidence_summary="Need the right edge.",
    )
    llm = QueueLLM(first, second, _resolved_row())
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=llm)
    assert result.verified_structure is not None
    third_prompt = llm.calls[2]["messages"][1]["content"]
    assert "Targeted evidence round 1:" in third_prompt
    assert "Targeted evidence round 2:" in third_prompt
    assert '"normalized_range":"A1:B3"' in third_prompt
    assert '"normalized_range":"D1:E3"' in third_prompt


def test_duplicate_targeted_range_fails_closed_without_third_call(tmp_path):
    need = lambda: StructureProposal(
        status="NEED_MORE_EVIDENCE",
        requested_ranges=["A1:B3"],
        confidence=0.3,
        evidence_summary="Need this range.",
    )
    llm = QueueLLM(need(), need())
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=llm)
    assert result.final_proposal.status.value == "AMBIGUOUS"
    assert "DUPLICATE_EVIDENCE_REQUEST" in result.final_proposal.reason_codes
    assert len(llm.calls) == 2


def test_cumulative_targeted_cell_budget_fails_closed(tmp_path):
    first = StructureProposal(
        status="NEED_MORE_EVIDENCE",
        requested_ranges=["A1:T25", "A26:T50"],
        confidence=0.2,
        evidence_summary="Need first half.",
    )
    second = StructureProposal(
        status="NEED_MORE_EVIDENCE",
        requested_ranges=["A51:T75", "A76:T100"],
        confidence=0.2,
        evidence_summary="Need second half.",
    )
    llm = QueueLLM(first, second)
    result = understand_sheet_structure(
        _sheet(tmp_path, rows=100, columns=20), llm_call=llm
    )
    assert result.final_proposal.status.value == "AMBIGUOUS"
    assert "EVIDENCE_BUDGET_EXCEEDED" in result.final_proposal.reason_codes
    assert len(llm.calls) == 2


def test_ambiguous_and_unsupported_abstain(tmp_path):
    sheet = _sheet(tmp_path)
    for status in ("AMBIGUOUS", "UNSUPPORTED"):
        proposal = StructureProposal(status=status, confidence=0.2, evidence_summary="Abstain.")
        result = understand_sheet_structure(sheet, llm_call=QueueLLM(proposal))
        assert result.verified_structure is None
        assert result.verification is None


def test_invalid_resolved_coordinates_do_not_verify(tmp_path):
    bad = _resolved_row().model_copy(deep=True)
    bad.row_oriented.header_bindings[0].header_cells = ["Z999"]
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=QueueLLM(bad))
    assert result.verification and not result.verification.valid
    assert result.verified_structure is None


def test_oversized_or_outside_evidence_request_fails_closed(tmp_path):
    sheet = _sheet(tmp_path)
    for requested in (["A1:Z100"], ["Z100:Z101"]):
        need = StructureProposal(
            status="NEED_MORE_EVIDENCE",
            requested_ranges=requested,
            confidence=0.3,
            evidence_summary="Need more.",
        )
        llm = QueueLLM(need)
        result = understand_sheet_structure(sheet, llm_call=llm)
        assert result.final_proposal.status.value == "AMBIGUOUS"
        assert "INVALID_EVIDENCE_REQUEST" in result.final_proposal.reason_codes
        assert len(llm.calls) == 1


def test_evidence_loop_is_bounded(tmp_path):
    def need(requested_range):
        return StructureProposal(
            status="NEED_MORE_EVIDENCE",
            requested_ranges=[requested_range],
            confidence=0.2,
            evidence_summary="Still unclear.",
        )

    llm = QueueLLM(need("A1:B2"), need("C1:D2"), need("A3:B4"))
    result = understand_sheet_structure(_sheet(tmp_path), llm_call=llm)
    assert result.final_proposal.status.value == "AMBIGUOUS"
    assert result.evidence_rounds == MAX_EVIDENCE_ROUNDS
    assert len(llm.calls) == 1 + MAX_EVIDENCE_ROUNDS


def test_initial_evidence_is_bounded_and_discloses_omissions(tmp_path):
    evidence = build_initial_evidence(_sheet(tmp_path, rows=100, columns=10))
    assert len(evidence.cells) <= MAX_INITIAL_CELLS
    assert evidence.omitted_cell_count > 0
    assert evidence.truncated
    assert any("request specific bounded ranges" in item for item in evidence.omissions)
