"""Validate adjudication and export strict final gold plus immutable decision history."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.schema.canonical import CanonicalSchema
from src.schema.gold_mapping import (
    GoldMappingAnnotation,
    load_adjudication_resolutions,
    load_gold_annotations,
    merge_adjudicated_gold,
)

FINAL_COLUMNS = [
    "campaign_version", "evaluation_config_fingerprint",
    "annotation_version", "annotation_source", "mapping_item_id",
    "mapping_identity_kind", "mapping_identity_value", "source_file_name",
    "source_file_sha256", "source_sheet", "source_format", "source_attribute_id",
    "source_attribute_display", "source_attribute", "source_context", "gold_status",
    "gold_canonical_keys", "ambiguous_candidate_canonical_keys", "annotator_id",
    "annotation_round", "notes", "created_at", "calibration_eligible",
]


def _annotation_row(
    annotation: GoldMappingAnnotation, *, campaign_version: str = "",
    evaluation_config_fingerprint: str = "",
) -> dict:
    row = annotation.model_dump(mode="json")
    row["campaign_version"] = campaign_version
    row["evaluation_config_fingerprint"] = evaluation_config_fingerprint
    for column in ("gold_canonical_keys", "ambiguous_candidate_canonical_keys"):
        row[column] = "|".join(row[column])
    return row


def finalize_campaign(
    annotations_a_path: Path,
    annotations_b_path: Path,
    adjudication_path: Path,
    final_output: Path,
    history_output: Path,
    campaign_metadata_path: Path | None = None,
) -> tuple[Path, Path]:
    collisions = [path for path in (final_output, history_output) if path.exists()]
    if collisions:
        raise FileExistsError(f"refusing to overwrite final campaign artifact(s): {collisions}")
    schema = CanonicalSchema.from_template()
    annotations_a = load_gold_annotations(annotations_a_path, schema=schema)
    annotations_b = load_gold_annotations(annotations_b_path, schema=schema)
    resolutions = load_adjudication_resolutions(
        adjudication_path, annotations_a.annotations, annotations_b.annotations, schema=schema,
    )
    merged = merge_adjudicated_gold(
        annotations_a.annotations, annotations_b.annotations, resolutions,
    )
    campaign_metadata = {}
    if campaign_metadata_path is not None:
        campaign_metadata = json.loads(campaign_metadata_path.read_text(encoding="utf-8"))
    campaign_version = campaign_metadata.get("campaign_version", "")
    fingerprint = campaign_metadata.get("frozen_evaluation_config_fingerprint", "")
    frame = pd.DataFrame(
        [_annotation_row(
            record.final_annotation, campaign_version=campaign_version,
            evaluation_config_fingerprint=fingerprint,
        ) for record in merged],
        columns=FINAL_COLUMNS,
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)
    if final_output.suffix.casefold() == ".xlsx":
        frame.to_excel(final_output, index=False)
    elif final_output.suffix.casefold() == ".csv":
        frame.to_csv(final_output, index=False, lineterminator="\n")
    else:
        raise ValueError("final gold output must be .xlsx or .csv")
    history_output.parent.mkdir(parents=True, exist_ok=True)
    history_output.write_text(
        json.dumps({
            "campaign_version": campaign_version,
            "frozen_evaluation_config_fingerprint": fingerprint,
            "campaign_metadata_path": campaign_metadata_path.as_posix() if campaign_metadata_path else None,
            "records": [record.model_dump(mode="json") for record in merged],
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    load_gold_annotations(final_output, schema=schema)
    return final_output, history_output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations-a", type=Path, required=True)
    parser.add_argument("--annotations-b", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output-final", type=Path, required=True)
    parser.add_argument("--output-history", type=Path, required=True)
    parser.add_argument("--campaign-metadata", type=Path, required=True)
    args = parser.parse_args()
    for path in finalize_campaign(
        args.annotations_a, args.annotations_b, args.adjudication,
        args.output_final, args.output_history,
        args.campaign_metadata,
    ):
        print(path)


if __name__ == "__main__":
    main()
