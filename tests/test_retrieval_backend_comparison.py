from pathlib import Path

from eval import retrieval_backend_comparison as comparison
from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile
from src.schema.canonical import CanonicalRow, CanonicalSchema


def test_comparison_reports_overlap_and_optional_gold_without_becoming_a_gate(monkeypatch):
    schema = CanonicalSchema(
        rows=[
            CanonicalRow(f"r_{i}", key, key, "test")
            for i, key in enumerate(("a", "b", "c", "d", "e"), start=1)
        ],
        template_hash="test",
        template_path=Path("test.xlsx"),
    )
    results = {
        "chroma": ["r_1", "r_2", "r_3", "r_4", "r_5"],
        "exact": ["r_1", "r_3", "r_4", "r_5", "r_2"],
    }

    def fake_retrieve(profile, *, backend, **kwargs):
        return [
            RetrievalHit(row_id, row_id, "test", float(rank))
            for rank, row_id in enumerate(results[backend])
        ]

    monkeypatch.setattr(comparison, "retrieve", fake_retrieve)
    report = comparison.compare_retrieval_backends(
        SourceAttributeProfile("query"),
        schema=schema,
        k=5,
        exact_index=object(),
        expected_row_id="r_2",
    )
    assert report.intersection_count == 5
    assert report.overlap_at_k == 1.0
    assert report.same_top1 is True
    assert report.chroma_ranks["r_2"] == 2
    assert report.exact_ranks["r_2"] == 5
    assert report.chroma_expected_hit_at_k is True
    assert report.exact_expected_hit_at_k is True
