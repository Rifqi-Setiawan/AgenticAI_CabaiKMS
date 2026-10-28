"""Create blank human-annotation artifacts from the current production pipeline.

Predictions are observations only and are never copied into gold fields.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.pipeline_runner import PipelineRunResult, run_pipeline_ui

HUMAN_COLUMNS = [
    "gold_status", "gold_canonical_keys", "ambiguous_candidate_canonical_keys",
    "annotator_id", "annotation_round", "notes",
]
ANNOTATION_COLUMNS = [
    "annotation_version", "annotation_source", "mapping_item_id",
    "mapping_identity_kind", "mapping_identity_value", "mapping_identity_issue",
    "source_file_name", "source_file_sha256",
    "source_sheet", "source_format", "source_attribute_id", "source_attribute_display",
    "source_backend", "retrieval_backend", "retrieval_k", "schema_version",
    "template_hash", "mapping_verification_version", "embedding_model_name",
    "evaluation_config_fingerprint",
    "source_attribute", "source_context", "proposed_target_canonical_key", "predicted_row",
    "mapping_method", "confidence", "exact_name_status", "verifier_status",
    "verifier_warnings", "verifier_hard_issues", "retrieval_target_rank",
    "retrieval_target_distance", "retrieval_top1_top2_margin",
    "retrieval_target_vs_top1_gap", "acceptance_status", *HUMAN_COLUMNS,
]


def create_annotation_table(result: PipelineRunResult) -> pd.DataFrame:
    frame = result.mapping_df.copy()
    missing_identity = frame["mapping_item_id"].isna() | (frame["mapping_item_id"].astype(str).str.strip() == "")
    if missing_identity.any():
        attributes = frame.loc[missing_identity, "source_attribute_display"].astype(str).tolist()
        raise ValueError(
            "stable annotation identity unavailable for source attribute(s): "
            f"{attributes}; use source-ir-gated when exact coordinates are required "
            "for repeated logical source attributes"
        )
    if frame["mapping_item_id"].duplicated().any():
        attributes = frame.loc[
            frame["mapping_item_id"].duplicated(keep=False), "source_attribute_display"
        ].astype(str).tolist()
        raise ValueError(f"stable annotation identity collision for source attribute(s): {attributes}")
    frame.insert(0, "annotation_version", "schema-mapping-gold-v1")
    frame.insert(1, "annotation_source", "human_independent")
    if "source_attribute_id" not in frame:
        source_ids = {
            verification.mapping_item_id: verification.source_attribute_id
            for verification in result.mapping_verifications
        }
        frame["source_attribute_id"] = frame["mapping_item_id"].map(source_ids)
    frame["source_backend"] = result.source_backend
    frame["retrieval_backend"] = result.retrieval_backend
    frame["retrieval_k"] = result.retrieval_k
    frame["schema_version"] = result.schema_version
    frame["template_hash"] = result.template_hash
    frame["mapping_verification_version"] = result.mapping_verification_version
    frame["embedding_model_name"] = result.embedding_model_name
    frame["evaluation_config_fingerprint"] = result.evaluation_config_fingerprint
    for column in ("verifier_warnings", "verifier_hard_issues"):
        if column in frame:
            frame[column] = frame[column].map(
                lambda value: "|".join(value) if isinstance(value, list) else (value or "")
            )
    for column in HUMAN_COLUMNS:
        frame[column] = ""
    return frame.reindex(columns=ANNOTATION_COLUMNS)


def run_annotation_harness(
    file_path: Path | str,
    output_path: Path | str,
    *, source_format: str = "row-oriented", sheet_name: str | None = None,
    source_backend: str = "legacy", retrieval_backend: str = "chroma", k: int = 8,
    force: bool = False, pipeline_call: Callable = run_pipeline_ui,
) -> pd.DataFrame:
    output = Path(output_path)
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite annotation file without --force: {output}")
    result = pipeline_call(
        Path(file_path), source_format=source_format, sheet_name=sheet_name,
        source_backend=source_backend, retrieval_backend=retrieval_backend, k=k,
    )
    frame = create_annotation_table(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.casefold() == ".xlsx":
        frame.to_excel(output, index=False)
    elif output.suffix.casefold() == ".csv":
        frame.to_csv(output, index=False, lineterminator="\n")
    else:
        raise ValueError("annotation output must be .xlsx or .csv")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=["row-oriented", "transposed"], default="row-oriented")
    parser.add_argument("--sheet")
    parser.add_argument("--source-backend", choices=["legacy", "source-ir-gated"], default="legacy")
    parser.add_argument("--retrieval-backend", choices=["chroma", "exact"], default="chroma")
    parser.add_argument("-k", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run_annotation_harness(
        args.file, args.output, source_format=args.format, sheet_name=args.sheet,
        source_backend=args.source_backend, retrieval_backend=args.retrieval_backend,
        k=args.k, force=args.force,
    )


if __name__ == "__main__":
    main()
