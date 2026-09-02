"""Fase 3 checkpoint — Schema Matching Agent end-to-end review harness.

Loads one file from data/samples/, runs the real Fase 3a-3f pipeline
(indexing -> anchor detection -> retrieval -> reranking -> normalization)
over every non-anchor source attribute in it, and writes a human-reviewable
table to data/gold/schema_matching_review.xlsx (sorted lowest-confidence
first, so the doubtful cases are on top). The reviewer fills in gold_row /
is_correct / catatan by hand afterward — this script leaves them blank and
never writes to them.

This is a REVIEW HARNESS ONLY: it imports and calls the Fase 3a-3f modules
exactly as they are. It does not modify, wrap, or reimplement any agent
logic.

Usage:
    python eval/review_schema_matching.py
    python eval/review_schema_matching.py --file data/samples/sample_transposed_sintetis.xlsx --format transposed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))  # allow `python eval/review_schema_matching.py`

import openpyxl
import pandas as pd

from src.agents.schema_matching.anchor import AnchorCandidate, detect_anchor
from src.agents.schema_matching.indexing import ensure_indexed
from src.agents.schema_matching.normalize import normalize
from src.agents.schema_matching.reranking import rerank
from src.agents.schema_matching.retrieval import DEFAULT_K, SourceAttributeProfile, retrieve
from src.agents.schema_matching.source_parsing import load_row_oriented_columns, load_transposed_rows
from src.llm.providers import LLMCallError
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW

DEFAULT_SAMPLE = PROJECT_ROOT / "data" / "samples" / "data_input.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "gold" / "schema_matching_review.xlsx"

REVIEW_COLUMNS = [
    "source_attribute",
    "source_format",
    "predicted_row",
    "predicted_label",
    "target_domain",
    "confidence",
    "normalization_required",
    "reasoning",
    "gold_row",
    "is_correct",
    "catatan",
]


def run_review(
    file_path: Path,
    source_format: str,
    sheet_name: str | None,
    k: int,
) -> tuple[pd.DataFrame, dict]:
    wb = openpyxl.load_workbook(file_path, read_only=True)
    sheet_name = sheet_name or wb.sheetnames[0]
    wb.close()

    if source_format == "row-oriented":
        parsed = load_row_oriented_columns(file_path, sheet_name)
        candidates = [AnchorCandidate(p.attribute_name, p.sample_values) for p in parsed]
        anchor_result = detect_anchor(candidates, source_format="row-oriented")
        attributes = [p for p in parsed if p.attribute_name != anchor_result.column_name]
    else:
        parsed, _variety_names = load_transposed_rows(file_path, sheet_name)
        anchor_result = detect_anchor([], source_format="transposed")
        attributes = parsed

    print(f"File: {file_path}  (sheet: {sheet_name!r}, format: {source_format})")
    print(
        f"Anchor detection: status={anchor_result.status!r} "
        f"column={anchor_result.column_name!r} similarity={anchor_result.similarity}"
    )
    print(f"  reason: {anchor_result.reason}")
    print(f"Atribut untuk schema matching: {len(attributes)}\n")

    schema = CanonicalSchema.from_template()
    print("Memastikan indeks ChromaDB (idempoten, akan re-embed hanya bila perlu)...")
    ensure_indexed(schema)

    rows_out: list[dict] = []
    llm_failures: list[str] = []
    normalization_notes: list[str] = []

    for attr in attributes:
        profile = SourceAttributeProfile(
            attribute_name=attr.attribute_name,
            structural_context=attr.structural_context,
            sample_values=attr.sample_values,
        )
        retrieved = retrieve(profile, k=k, schema=schema)

        try:
            mapping = rerank(profile, retrieved, source_format=source_format, schema=schema)
        except LLMCallError as exc:
            llm_failures.append(f'"{attr.attribute_name}": {exc}')
            print(f"  [LLM ERROR] {attr.attribute_name}: {exc}", file=sys.stderr)
            continue

        target_row = None
        if mapping.target_canonical_row != NULL_ROW:
            target_row = schema.row_by_id(mapping.target_canonical_row)
            for value in attr.sample_values:
                note = normalize(value, target_row).note
                if note:
                    normalization_notes.append(note)

        rows_out.append(
            {
                "source_attribute": attr.attribute_name,
                "source_format": source_format,
                "predicted_row": mapping.target_canonical_row,
                "predicted_label": target_row.label if target_row else None,
                "target_domain": mapping.target_domain,
                "confidence": mapping.confidence,
                "normalization_required": mapping.normalization_required,
                "reasoning": mapping.reasoning,
                "gold_row": None,
                "is_correct": None,
                "catatan": None,
            }
        )

    df = pd.DataFrame(rows_out, columns=REVIEW_COLUMNS)
    if not df.empty:
        df = df.sort_values("confidence", ascending=True, kind="stable").reset_index(drop=True)

    diagnostics = {
        "n_attributes": len(attributes),
        "n_mapped": len(rows_out),
        "n_llm_failures": len(llm_failures),
        "llm_failures": llm_failures,
        "normalization_notes": normalization_notes,
        "anchor_result": anchor_result,
    }
    return df, diagnostics


def print_summary(df: pd.DataFrame, diagnostics: dict, output_path: Path) -> None:
    print("\n=== Ringkasan ===")
    print(f"Total atribut dievaluasi: {diagnostics['n_attributes']}")
    print(f"Berhasil dipetakan (termasuk NULL): {diagnostics['n_mapped']}")
    if diagnostics["n_llm_failures"]:
        print(f"Gagal (LLM error, dilewati): {diagnostics['n_llm_failures']}")
        for msg in diagnostics["llm_failures"]:
            print(f"  - {msg}")

    if df.empty:
        print("\nTidak ada baris untuk ditulis.")
        return

    n_null = int((df["predicted_row"] == NULL_ROW).sum())
    print(f"Dipetakan ke NULL: {n_null} / {len(df)}")

    print("\nDistribusi confidence:")
    print(df["confidence"].describe().to_string())

    if diagnostics["normalization_notes"]:
        print(f"\nCatatan normalisasi ({len(diagnostics['normalization_notes'])} nilai contoh tidak bisa dinormalisasi dengan yakin):")
        for note in diagnostics["normalization_notes"]:
            print(f"  - {note}")

    print(f"\nDitulis ke: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_SAMPLE, help="file di data/samples/ untuk dievaluasi")
    parser.add_argument(
        "--format",
        dest="source_format",
        choices=["row-oriented", "transposed"],
        default="row-oriented",
        help="variant sumber (default: row-oriented, cocok untuk data_input.xlsx)",
    )
    parser.add_argument("--sheet", default=None, help="nama sheet (default: sheet pertama)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    args = parser.parse_args()

    if not args.file.exists():
        parser.error(f"file tidak ditemukan: {args.file}")

    df, diagnostics = run_review(args.file, args.source_format, args.sheet, args.k)

    if not df.empty:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(args.output, index=False)

    print_summary(df, diagnostics, args.output)


if __name__ == "__main__":
    main()
