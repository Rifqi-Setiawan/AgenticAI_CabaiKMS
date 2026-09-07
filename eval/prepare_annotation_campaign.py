"""Create two blinded, blank annotation workbooks from one frozen validation run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.create_mapping_annotations import HUMAN_COLUMNS, create_annotation_table
from src.agents.schema_matching.indexing import EMBEDDING_MODEL_NAME
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import EvaluationRunConfig
from src.schema.evaluation_manifest import EvaluationManifest, EvaluationSplit
from src.schema.mapping_verification import MAPPING_VERIFICATION_VERSION
from src.ui.pipeline_runner import run_pipeline_ui
from src.ui import pipeline_runner

ANNOTATION_INSTRUCTIONS_VERSION = "human-schema-mapping-v1"
BLINDED_COLUMNS = [
    "mapping_item_id", "source_attribute_display", "source_attribute", "source_context",
    *HUMAN_COLUMNS, "annotation_version", "annotation_source",
    "mapping_identity_kind", "mapping_identity_value", "mapping_identity_issue",
    "source_file_name", "source_file_sha256", "source_sheet", "source_format",
    "source_attribute_id",
    "source_backend", "retrieval_backend", "retrieval_k", "schema_version",
    "template_hash", "mapping_verification_version", "embedding_model_name",
    "evaluation_config_fingerprint",
]
IMMUTABLE_COLUMNS = [
    column for column in BLINDED_COLUMNS
    if column not in HUMAN_COLUMNS
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_template(path: Path, annotations: pd.DataFrame, schema: CanonicalSchema) -> None:
    reference = pd.DataFrame([{
        "canonical_key": row.canonical_key,
        "label": row.label,
        "domain": row.domain,
        "example_values": " | ".join(row.contoh_nilai),
        "alternate_labels": " | ".join(row.alt_labels),
    } for row in schema.rows])
    with pd.ExcelWriter(path) as writer:
        annotations.to_excel(writer, sheet_name="Annotations", index=False)
        reference.to_excel(writer, sheet_name="Canonical Reference", index=False)
    workbook = load_workbook(path)
    sheet = workbook["Annotations"]
    dark_blue = PatternFill("solid", fgColor="1F4E78")
    light_blue = PatternFill("solid", fgColor="5B9BD5")
    input_fill = PatternFill("solid", fgColor="FFF2CC")
    context_fill = PatternFill("solid", fgColor="F3F4F6")
    provenance_fill = PatternFill("solid", fgColor="F8FAFC")
    for cell in sheet[1]:
        cell.fill = dark_blue
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 42
    for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row):
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="1F2937")
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column <= 10)
            cell.fill = (
                context_fill if cell.column <= 4
                else input_fill if cell.column <= 10
                else provenance_fill
            )
            if 5 <= cell.column <= 10:
                cell.protection = Protection(locked=False)
    widths = [
        16, 42, 25, 32, 18, 28, 32, 18, 12, 34, 24, 20, 24, 42,
        18, 20, 16, 18, 16, 20, 16, 16, 10, 24, 16, 25, 36, 16,
    ]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
    status_validation = DataValidation(
        type="list", formula1='"ONE_TO_ONE,NO_MATCH,AMBIGUOUS,COMPOSITE,EXCLUDE"',
    )
    round_validation = DataValidation(type="whole", operator="equal", formula1="1")
    sheet.add_data_validation(status_validation)
    sheet.add_data_validation(round_validation)
    status_validation.add(f"E2:E{sheet.max_row}")
    round_validation.add(f"I2:I{sheet.max_row}")
    sheet.freeze_panes = "E2"
    sheet.sheet_view.showGridLines = False
    sheet.auto_filter.ref = sheet.dimensions
    sheet.protection.sheet = True

    reference_sheet = workbook["Canonical Reference"]
    for cell in reference_sheet[1]:
        cell.fill = light_blue
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in reference_sheet.iter_rows(min_row=2, max_row=reference_sheet.max_row):
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="1F2937")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for index, width in enumerate([28, 34, 16, 42, 38], start=1):
        reference_sheet.column_dimensions[reference_sheet.cell(1, index).column_letter].width = width
    reference_sheet.freeze_panes = "A2"
    reference_sheet.sheet_view.showGridLines = False
    reference_sheet.auto_filter.ref = reference_sheet.dimensions
    reference_sheet.protection.sheet = True
    workbook.save(path)


def prepare_campaign(
    manifest_path: Path,
    input_dir: Path,
    output_dir: Path,
    *,
    source_backend: str = "legacy",
    retrieval_backend: str = "exact",
    retrieval_k: int = 8,
    annotation_round: int = 1,
    pipeline_call: Callable = run_pipeline_ui,
) -> tuple[Path, Path, Path]:
    manifest = EvaluationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    validation = [item for item in manifest.workbooks if item.split is EvaluationSplit.VALIDATION]
    if not validation:
        raise ValueError("evaluation manifest contains no validation workbooks")
    output_a = output_dir / "annotations_A.xlsx"
    output_b = output_dir / "annotations_B.xlsx"
    metadata_path = output_dir / "campaign_metadata.json"
    collisions = [path for path in (output_a, output_b, metadata_path) if path.exists()]
    if collisions:
        raise FileExistsError(f"refusing to overwrite campaign artifact(s): {collisions}")

    schema = CanonicalSchema.from_template()
    expected_config = EvaluationRunConfig(
        source_backend=source_backend,
        retrieval_backend=retrieval_backend,
        retrieval_k=retrieval_k,
        canonical_schema_version=schema.schema_version,
        canonical_template_hash=schema.template_hash,
        mapping_verification_version=MAPPING_VERIFICATION_VERSION,
        embedding_model_name=EMBEDDING_MODEL_NAME,
    )
    frames = []
    workbook_metadata = []
    original_orchestrator_call = pipeline_runner.run_pipeline
    with tempfile.TemporaryDirectory(prefix="cabai-kms-annotation-") as temporary:
        if pipeline_call is run_pipeline_ui:
            isolated_db = Path(temporary) / "orchestrator.sqlite"

            def isolated_orchestrator(*args, **kwargs):
                return original_orchestrator_call(*args, db_path=isolated_db, **kwargs)

            pipeline_runner.run_pipeline = isolated_orchestrator
        try:
            for entry in validation:
                source = input_dir / entry.source_file_name
                actual_hash = _sha256(source)
                if actual_hash != entry.source_file_sha256.lower():
                    raise ValueError(f"validation workbook hash mismatch: {source}")
                result = pipeline_call(
                    source,
                    source_format=entry.source_format,
                    sheet_name=entry.sheet,
                    source_backend=source_backend,
                    retrieval_backend=retrieval_backend,
                    k=retrieval_k,
                )
                if result.evaluation_config_fingerprint != expected_config.fingerprint:
                    raise ValueError(f"evaluation configuration mismatch for {source}")
                frame = create_annotation_table(result).reindex(columns=BLINDED_COLUMNS)
                frames.append(frame)
                workbook_metadata.append({
                    "source_file_name": entry.source_file_name,
                    "source_file_sha256": actual_hash,
                    "source_sheet": entry.sheet,
                    "source_format": entry.source_format,
                    "annotatable_items": len(frame),
                })
        finally:
            pipeline_runner.run_pipeline = original_orchestrator_call

    combined = pd.concat(frames, ignore_index=True)
    if combined["mapping_item_id"].duplicated().any():
        raise ValueError("validation campaign contains duplicate mapping_item_id values")
    if combined[IMMUTABLE_COLUMNS].isna().all(axis=1).any():
        raise ValueError("campaign contains an empty immutable provenance row")
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_template(output_a, combined, schema)
    _write_template(output_b, combined.copy(deep=True), schema)
    metadata = {
        "campaign_version": "schema-mapping-human-campaign-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "annotation_round": annotation_round,
        "annotation_instructions_version": ANNOTATION_INSTRUCTIONS_VERSION,
        "gold_annotation_version": "schema-mapping-gold-v1",
        "evaluation_manifest_version": manifest.manifest_version,
        "evaluation_manifest_path": manifest_path.as_posix(),
        "canonical_schema_version": schema.schema_version,
        "canonical_template_hash": schema.template_hash,
        "evaluation_config_fingerprint": expected_config.fingerprint,
        "source_backend": source_backend,
        "retrieval_backend": retrieval_backend,
        "retrieval_k": retrieval_k,
        "mapping_verification_version": MAPPING_VERIFICATION_VERSION,
        "embedding_model_name": EMBEDDING_MODEL_NAME,
        "prediction_blinded": True,
        "workbooks": workbook_metadata,
        "annotatable_item_count": len(combined),
        "unavailable_identity_count": 0,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_a, output_b, metadata_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, default=Path("data/samples"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--annotation-round", type=int, default=1)
    parser.add_argument("--source-backend", choices=["legacy", "source-ir-gated"], default="legacy")
    parser.add_argument("--retrieval-backend", choices=["chroma", "exact"], default="exact")
    parser.add_argument("-k", type=int, default=8)
    args = parser.parse_args()
    paths = prepare_campaign(
        args.manifest, args.input_dir, args.output_dir,
        source_backend=args.source_backend, retrieval_backend=args.retrieval_backend,
        retrieval_k=args.k, annotation_round=args.annotation_round,
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
