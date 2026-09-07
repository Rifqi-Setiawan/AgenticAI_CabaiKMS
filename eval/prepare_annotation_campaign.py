"""Build a fail-closed, frozen human-annotation campaign from one manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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

from eval.create_mapping_annotations import ANNOTATION_COLUMNS, HUMAN_COLUMNS, create_annotation_table
from src.ingestion.runtime_source import prepare_legacy_runtime_source
from src.schema.canonical import CanonicalSchema
from src.schema.evaluation_config import EvaluationRunConfig
from src.schema.gold_mapping import MappingIdentityKind, build_mapping_item_identities
from src.ui.pipeline_runner import run_pipeline_ui
from src.ui import pipeline_runner

CAMPAIGN_VERSION = "schema-mapping-pilot-v1"
GUIDELINE_VERSION = "annotation-guidelines-v1"
SUPPORTED_FORMATS = {"row-oriented", "transposed"}
PREDICTION_COLUMNS = {
    "proposed_target_canonical_key", "predicted_row", "mapping_method", "confidence",
    "exact_name_status", "verifier_status", "verifier_warnings", "verifier_hard_issues",
    "retrieval_target_rank", "retrieval_target_distance", "retrieval_top1_top2_margin",
    "retrieval_target_vs_top1_gap", "acceptance_status",
}
BLINDED_COLUMNS = [
    "mapping_item_id", "source_attribute_display", "source_attribute", "source_context",
    *HUMAN_COLUMNS, "annotation_version", "annotation_source",
    "mapping_identity_kind", "mapping_identity_value", "mapping_identity_issue",
    "source_file_name", "source_file_sha256", "source_sheet", "source_format",
    "source_attribute_id", "source_backend", "retrieval_backend", "retrieval_k",
    "schema_version", "template_hash", "mapping_verification_version",
    "embedding_model_name", "evaluation_config_fingerprint",
]
IMMUTABLE_COLUMNS = [column for column in BLINDED_COLUMNS if column not in HUMAN_COLUMNS]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _manifest_config(manifest: dict) -> EvaluationRunConfig:
    return EvaluationRunConfig(
        source_backend=manifest["source_backend"], retrieval_backend=manifest["retrieval_backend"],
        retrieval_k=manifest["retrieval_k"],
        canonical_schema_version=manifest["canonical_schema_version"],
        canonical_template_hash=manifest["canonical_template_hash"],
        mapping_verification_version=manifest["mapping_verification_version"],
        embedding_model_name=manifest["embedding_model_name"],
    )


def assess_campaign_readiness(
    manifest_path: Path, *, project_root: Path = PROJECT_ROOT,
    source_loader: Callable = prepare_legacy_runtime_source,
) -> dict:
    """Inspect actual inputs and return a deterministic, fail-closed report."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = CanonicalSchema.from_template()
    blockers: list[str] = []
    expected_config = _manifest_config(manifest)
    declared_fingerprint = manifest.get("frozen_evaluation_config_fingerprint", "")
    if declared_fingerprint != expected_config.fingerprint:
        blockers.append("FROZEN_EVALUATION_CONFIG_FINGERPRINT_MISMATCH")
    if manifest.get("canonical_schema_version") != schema.schema_version:
        blockers.append("CANONICAL_SCHEMA_VERSION_MISMATCH")
    if manifest.get("canonical_template_hash") != schema.template_hash:
        blockers.append("CANONICAL_TEMPLATE_HASH_MISMATCH")

    campaign_type = manifest.get("campaign_type")
    if campaign_type not in {"pilot", "final_validation"}:
        blockers.append(f"INVALID_CAMPAIGN_TYPE:{campaign_type}")
    validation_entries = [item for item in manifest.get("validation_workbooks", []) if item.get("part_of_validation") is True]
    if not validation_entries:
        blockers.append("NO_VALIDATION_WORKBOOKS")
    counts = {
        "validation_workbook_count": len(validation_entries), "validation_sheet_count": 0,
        "total_source_attribute_count": 0, "annotatable_item_count": 0,
        "stable_identity_count": 0, "unavailable_identity_count": 0,
    }
    item_ids: list[str] = []
    source_formats: list[str] = []
    variation_tags: list[str] = []
    seen_entry_ids: set[str] = set()
    for entry in validation_entries:
        entry_id = str(entry.get("entry_id", "")).strip()
        if not entry_id or entry_id in seen_entry_ids:
            blockers.append(f"INVALID_OR_DUPLICATE_ENTRY_ID:{entry_id or '<blank>'}")
        seen_entry_ids.add(entry_id)
        if (entry.get("source_backend"), entry.get("retrieval_backend"), entry.get("retrieval_k")) != (
            manifest.get("source_backend"), manifest.get("retrieval_backend"), manifest.get("retrieval_k")
        ):
            blockers.append(f"MIXED_EVALUATION_CONFIGURATION:{entry_id}")
        source_format = entry.get("source_format")
        source_formats.append(str(source_format))
        variation_tags.extend(str(tag) for tag in entry.get("variation_tags", []))
        if source_format not in SUPPORTED_FORMATS:
            blockers.append(f"UNSUPPORTED_SOURCE_FORMAT:{entry_id}:{source_format}")
            continue
        source = project_root / entry.get("path", "")
        if not source.is_file():
            blockers.append(f"VALIDATION_FILE_MISSING:{entry_id}:{entry.get('path', '')}")
            continue
        actual_hash = _sha256(source)
        if actual_hash != str(entry.get("sha256", "")).lower():
            blockers.append(f"WORKBOOK_HASH_MISMATCH:{entry_id}")
            continue
        try:
            available_sheets = set(pd.ExcelFile(source).sheet_names)
        except Exception as exc:
            blockers.append(f"WORKBOOK_UNREADABLE:{entry_id}:{type(exc).__name__}")
            continue
        sheets = entry.get("sheets", [])
        missing_sheets = sorted(set(sheets) - available_sheets)
        if missing_sheets:
            blockers.append(f"REQUIRED_SHEET_MISSING:{entry_id}:{'|'.join(missing_sheets)}")
            continue
        entry_counts = {"annotatable_attributes": 0, "stable_mapping_identities": 0, "unavailable_identities": 0}
        for sheet in sheets:
            counts["validation_sheet_count"] += 1
            try:
                bundle = source_loader(source, sheet, source_format=source_format)
                counts["total_source_attribute_count"] += len(bundle.all_attributes)
                identities = build_mapping_item_identities(
                    source_file_sha256=actual_hash, source_sheet=sheet, source_format=source_format,
                    source_items=[(attribute.source_attribute_id, attribute.display_name) for attribute in bundle.schema_attributes],
                )
            except Exception as exc:
                blockers.append(f"SOURCE_PARSE_FAILED:{entry_id}:{sheet}:{type(exc).__name__}")
                continue
            stable = [item.mapping_item_id for item in identities if item.identity_kind is not MappingIdentityKind.UNAVAILABLE]
            unavailable = sum(item.identity_kind is MappingIdentityKind.UNAVAILABLE for item in identities)
            entry_counts["annotatable_attributes"] += len(identities)
            entry_counts["stable_mapping_identities"] += len(stable)
            entry_counts["unavailable_identities"] += unavailable
            counts["annotatable_item_count"] += len(identities)
            counts["stable_identity_count"] += len(stable)
            counts["unavailable_identity_count"] += unavailable
            item_ids.extend(item_id for item_id in stable if item_id)
            if unavailable:
                blockers.append(f"IDENTITY_UNAVAILABLE:{entry_id}:{sheet}:{unavailable}")
        for name, actual in entry_counts.items():
            if entry.get("counts", {}).get(name) != actual:
                blockers.append(f"DECLARED_COUNT_MISMATCH:{entry_id}:{name}")

    duplicate_count = len(item_ids) - len(set(item_ids))
    if duplicate_count:
        blockers.append(f"DUPLICATE_MAPPING_ITEM_ID:{duplicate_count}")
    source_format_distribution = dict(sorted(__import__("collections").Counter(source_formats).items()))
    variation_tag_distribution = dict(sorted(__import__("collections").Counter(variation_tags).items()))
    integrity_blockers = sorted(set(blockers))
    coverage_blockers: list[str] = []
    requirements = manifest.get("readiness_requirements", {})
    if campaign_type == "final_validation":
        minimum_workbooks = requirements.get("minimum_independent_workbooks")
        if minimum_workbooks is None:
            coverage_blockers.append("FINAL_MINIMUM_WORKBOOK_COUNT_UNDEFINED")
        elif counts["validation_workbook_count"] < minimum_workbooks:
            coverage_blockers.append(
                f"FINAL_DATASET_INSUFFICIENT: contains only {counts['validation_workbook_count']} real workbook / "
                f"{counts['annotatable_item_count']} attributes; additional real heterogeneous evaluation workbooks are required."
            )
        minimum_formats = requirements.get("minimum_distinct_source_formats")
        if minimum_formats is None:
            coverage_blockers.append("FINAL_MINIMUM_SOURCE_FORMAT_DIVERSITY_UNDEFINED")
        elif len(source_format_distribution) < minimum_formats:
            coverage_blockers.append(
                f"FINAL_SOURCE_FORMAT_DIVERSITY_INSUFFICIENT:{len(source_format_distribution)}<{minimum_formats}"
            )
        minimum_variations = requirements.get("minimum_distinct_variation_tags")
        if minimum_variations is None:
            coverage_blockers.append("FINAL_MINIMUM_STRUCTURE_DIVERSITY_UNDEFINED")
        elif len(variation_tag_distribution) < minimum_variations:
            coverage_blockers.append(
                f"FINAL_STRUCTURE_DIVERSITY_INSUFFICIENT:{len(variation_tag_distribution)}<{minimum_variations}"
            )
        minimum_items = requirements.get("minimum_annotatable_item_count")
        if minimum_items is None:
            coverage_blockers.append("FINAL_MINIMUM_ANNOTATABLE_ITEM_COUNT_NOT_DEFINED_BY_METHODOLOGY")
        elif counts["annotatable_item_count"] < minimum_items:
            coverage_blockers.append(
                f"FINAL_ANNOTATABLE_ITEM_COUNT_INSUFFICIENT:{counts['annotatable_item_count']}<{minimum_items}"
            )
    all_blockers = sorted(set([*integrity_blockers, *coverage_blockers]))
    pilot_ready = campaign_type == "pilot" and not integrity_blockers
    final_ready = campaign_type == "final_validation" and not all_blockers
    return {
        "campaign_version": manifest.get("campaign_version"), "campaign_type": campaign_type, **counts,
        "duplicate_mapping_item_id_count": duplicate_count,
        "source_format_distribution": source_format_distribution,
        "variation_tag_distribution": variation_tag_distribution,
        "evaluation_config_fingerprint": declared_fingerprint,
        "frozen_evaluation_config_fingerprint": declared_fingerprint,
        "canonical_schema_version": manifest.get("canonical_schema_version"),
        "canonical_template_hash": manifest.get("canonical_template_hash"),
        "campaign_ready": pilot_ready if campaign_type == "pilot" else final_ready,
        "pilot_ready": pilot_ready,
        "final_campaign_ready": final_ready,
        "blockers": integrity_blockers if campaign_type == "pilot" else all_blockers,
        "final_campaign_blockers": coverage_blockers,
    }


def summarize_observation_identities(frame: pd.DataFrame) -> dict[str, int]:
    """Count stable/unavailable identities from generated observation fields."""
    text = lambda column: frame.get(column, pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    unavailable = (
        text("mapping_identity_kind").str.casefold().eq(MappingIdentityKind.UNAVAILABLE.value)
        | text("mapping_item_id").eq("")
        | text("mapping_identity_value").eq("")
        | text("mapping_identity_issue").str.contains("STABLE_MAPPING_IDENTITY_UNAVAILABLE", regex=False)
    )
    nonblank_ids = text("mapping_item_id").loc[~text("mapping_item_id").eq("")]
    return {
        "stable_identity_count": int((~unavailable).sum()),
        "unavailable_identity_count": int(unavailable.sum()),
        "duplicate_mapping_item_id_count": int(nonblank_ids.duplicated().sum()),
    }


def verify_master_blinded_integrity(master: pd.DataFrame, annotations_a: pd.DataFrame, annotations_b: pd.DataFrame) -> None:
    """Verify A/B derive from master by ID, independent of row position."""
    frames = {"master": master, "A": annotations_a, "B": annotations_b}
    indexes = {}
    for name, frame in frames.items():
        ids = frame["mapping_item_id"].fillna("").astype(str).str.strip()
        if ids.eq("").any() or ids.duplicated().any():
            raise ValueError(f"{name} contains missing or duplicate mapping_item_id")
        indexes[name] = frame.assign(mapping_item_id=ids).set_index("mapping_item_id")
    if set(indexes["master"].index) != set(indexes["A"].index) or set(indexes["A"].index) != set(indexes["B"].index):
        raise ValueError("master/A/B mapping_item_id universes differ")
    immutable = [column for column in IMMUTABLE_COLUMNS if column != "mapping_item_id"]
    order = sorted(indexes["master"].index)
    for name in ("A", "B"):
        left = indexes["master"].loc[order, immutable].fillna("").astype(str)
        right = indexes[name].loc[order, immutable].fillna("").astype(str)
        if not left.equals(right):
            raise ValueError(f"master/{name} immutable provenance differs")


def verify_frozen_artifacts(metadata_path: Path, *, project_root: Path = PROJECT_ROOT) -> list[str]:
    """Return deterministic hash-integrity blockers for every frozen artifact."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    records = [
        metadata["campaign_manifest"], metadata["readiness"], metadata["canonical_template"],
        metadata["annotation_guideline"], metadata["master_artifact"],
        metadata["annotator_A_template"], metadata["annotator_B_template"],
        *metadata["validation_workbooks"],
    ]
    blockers = []
    for record in records:
        path = Path(record["path"])
        resolved = path if path.is_absolute() else project_root / path
        label = record.get("entry_id", record["path"])
        if not resolved.is_file():
            blockers.append(f"FROZEN_ARTIFACT_MISSING:{label}")
        elif _sha256(resolved) != record["sha256"]:
            blockers.append(f"FROZEN_ARTIFACT_HASH_MISMATCH:{label}")
    return sorted(blockers)


def _reference_frame(schema: CanonicalSchema) -> pd.DataFrame:
    return pd.DataFrame([{
        "canonical_key": row.canonical_key, "label": row.label, "domain": row.domain,
        "example_values": " | ".join(row.contoh_nilai), "alternate_labels": " | ".join(row.alt_labels),
    } for row in schema.rows])


def _style_workbook(path: Path, *, blinded: bool) -> None:
    workbook = load_workbook(path)
    sheet = workbook["Annotations"]
    headers = {cell.value: cell.column for cell in sheet[1]}
    human_indexes = {headers[column] for column in HUMAN_COLUMNS if column in headers}
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 42
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial", size=10, color="1F2937")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            editable = blinded and cell.column in human_indexes
            cell.fill = PatternFill("solid", fgColor="FFF2CC" if editable else "F3F4F6")
            cell.protection = Protection(locked=not editable)
    for cell in sheet[1]:
        sheet.column_dimensions[cell.column_letter].width = 18
    for name in ("source_attribute_display", "source_context", "notes"):
        if name in headers:
            sheet.column_dimensions[sheet.cell(1, headers[name]).column_letter].width = 34
    if blinded:
        status = DataValidation(type="list", formula1='"ONE_TO_ONE,NO_MATCH,AMBIGUOUS,COMPOSITE,EXCLUDE"')
        round_number = DataValidation(type="whole", operator="equal", formula1="1")
        sheet.add_data_validation(status)
        sheet.add_data_validation(round_number)
        status.add(f"{sheet.cell(2, headers['gold_status']).coordinate}:{sheet.cell(sheet.max_row, headers['gold_status']).coordinate}")
        round_number.add(f"{sheet.cell(2, headers['annotation_round']).coordinate}:{sheet.cell(sheet.max_row, headers['annotation_round']).coordinate}")
    sheet.freeze_panes = "E2" if blinded else "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False
    sheet.protection.sheet = True
    reference = workbook["Canonical Reference"]
    for cell in reference[1]:
        cell.fill = PatternFill("solid", fgColor="5B9BD5")
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    for row in reference.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for index, width in enumerate([28, 34, 16, 42, 38], start=1):
        reference.column_dimensions[reference.cell(1, index).column_letter].width = width
    reference.freeze_panes = "A2"
    reference.auto_filter.ref = reference.dimensions
    reference.sheet_view.showGridLines = False
    reference.protection.sheet = True
    workbook.save(path)


def _write_workbook(path: Path, annotations: pd.DataFrame, schema: CanonicalSchema, *, blinded: bool) -> None:
    with pd.ExcelWriter(path) as writer:
        annotations.to_excel(writer, sheet_name="Annotations", index=False)
        _reference_frame(schema).to_excel(writer, sheet_name="Canonical Reference", index=False)
    _style_workbook(path, blinded=blinded)


def _git_revision(project_root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=True)
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def build_campaign_metadata(
    manifest_path: Path, output_dir: Path, *, project_root: Path = PROJECT_ROOT,
    guideline_path: Path | None = None,
) -> dict:
    """Build the hash chain for an already-written pilot campaign package."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    readiness_path = output_dir / "readiness.json"
    master_path = output_dir / "master" / "master_evaluation.xlsx"
    output_a = output_dir / "round1" / "annotator_A_round1.xlsx"
    output_b = output_dir / "round1" / "annotator_B_round1.xlsx"
    guideline = guideline_path or project_root / manifest["annotation_guideline_path"]
    required = [readiness_path, master_path, output_a, output_b, guideline]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"cannot freeze incomplete campaign package: {missing}")
    expected_config = _manifest_config(manifest)
    return {
        "campaign_version": manifest["campaign_version"], "campaign_type": manifest["campaign_type"],
        "annotation_version": manifest["annotation_version"], "annotation_round": manifest["annotation_round"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "code_revision": _git_revision(project_root),
        "campaign_manifest": {"path": manifest_path.as_posix(), "sha256": _sha256(manifest_path)},
        "readiness": {"path": readiness_path.as_posix(), "sha256": _sha256(readiness_path)},
        "validation_workbooks": [
            {"entry_id": entry["entry_id"], "path": entry["path"], "sha256": entry["sha256"]}
            for entry in manifest["validation_workbooks"] if entry["part_of_validation"]
        ],
        "master_artifact": {"path": master_path.as_posix(), "sha256": _sha256(master_path)},
        "annotator_A_template": {"path": output_a.as_posix(), "sha256": _sha256(output_a)},
        "annotator_B_template": {"path": output_b.as_posix(), "sha256": _sha256(output_b)},
        "canonical_schema_version": manifest["canonical_schema_version"],
        "canonical_template_hash": manifest["canonical_template_hash"],
        "canonical_template": {
            "path": "data/canonical/template_kanonik.xlsx",
            "sha256": _sha256(project_root / "data/canonical/template_kanonik.xlsx"),
        },
        "frozen_evaluation_config_fingerprint": expected_config.fingerprint,
        "annotation_guideline": {"path": manifest["annotation_guideline_path"], "version": manifest["annotation_guideline_version"], "sha256": _sha256(guideline)},
        "prediction_blinded": True,
    }


def prepare_campaign(
    manifest_path: Path, output_dir: Path, *, project_root: Path = PROJECT_ROOT,
    guideline_path: Path | None = None, pipeline_call: Callable = run_pipeline_ui,
) -> tuple[Path, Path, Path, Path, Path]:
    """Write readiness, master, A/B, and cryptographic campaign metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    readiness_path = output_dir / "readiness.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    readiness = assess_campaign_readiness(manifest_path, project_root=project_root)
    readiness_path.write_bytes(_json_bytes(readiness))
    if not readiness["campaign_ready"]:
        raise ValueError(f"campaign is not ready: {readiness['blockers']}")
    master_path = output_dir / "master" / "master_evaluation.xlsx"
    output_a = output_dir / "round1" / "annotator_A_round1.xlsx"
    output_b = output_dir / "round1" / "annotator_B_round1.xlsx"
    metadata_path = output_dir / "metadata.json"
    collisions = [path for path in (master_path, output_a, output_b, metadata_path) if path.exists()]
    if collisions:
        raise FileExistsError(f"refusing to overwrite campaign artifact(s): {collisions}")
    for path in (master_path, output_a, output_b):
        path.parent.mkdir(parents=True, exist_ok=True)

    schema = CanonicalSchema.from_template()
    expected_config = _manifest_config(manifest)
    frames: list[pd.DataFrame] = []
    original_orchestrator_call = pipeline_runner.run_pipeline
    with tempfile.TemporaryDirectory(prefix="cabai-kms-annotation-") as temporary:
        if pipeline_call is run_pipeline_ui:
            isolated_db = Path(temporary) / "orchestrator.sqlite"
            def isolated_orchestrator(*args, **kwargs):
                return original_orchestrator_call(*args, db_path=isolated_db, **kwargs)
            pipeline_runner.run_pipeline = isolated_orchestrator
        try:
            for entry in manifest["validation_workbooks"]:
                if not entry["part_of_validation"]:
                    continue
                source = project_root / entry["path"]
                for sheet in entry["sheets"]:
                    result = pipeline_call(
                        source, source_format=entry["source_format"], sheet_name=sheet,
                        source_backend=entry["source_backend"], retrieval_backend=entry["retrieval_backend"],
                        k=entry["retrieval_k"],
                    )
                    if result.evaluation_config_fingerprint != expected_config.fingerprint:
                        raise ValueError(f"evaluation configuration mismatch for {entry['entry_id']}:{sheet}")
                    frames.append(create_annotation_table(result))
        finally:
            pipeline_runner.run_pipeline = original_orchestrator_call

    master = pd.concat(frames, ignore_index=True).reindex(columns=ANNOTATION_COLUMNS)
    observed_identity = summarize_observation_identities(master)
    if observed_identity["unavailable_identity_count"]:
        raise ValueError("generated observations contain unavailable stable identities")
    if observed_identity["duplicate_mapping_item_id_count"]:
        raise ValueError("validation campaign contains duplicate mapping_item_id values")
    if len(master) != readiness["annotatable_item_count"]:
        raise ValueError("master item count differs from readiness report")
    if any(master[column].fillna("").astype(str).str.strip().ne("").any() for column in HUMAN_COLUMNS):
        raise ValueError("master human gold fields must remain blank")
    blinded = master.reindex(columns=BLINDED_COLUMNS).copy(deep=True)
    if PREDICTION_COLUMNS & set(blinded.columns):
        raise ValueError("prediction columns leaked into blinded view")
    verify_master_blinded_integrity(master, blinded, blinded.copy(deep=True))
    _write_workbook(master_path, master, schema, blinded=False)
    _write_workbook(output_a, blinded, schema, blinded=True)
    _write_workbook(output_b, blinded.copy(deep=True), schema, blinded=True)

    metadata = build_campaign_metadata(
        manifest_path, output_dir, project_root=project_root, guideline_path=guideline_path,
    )
    metadata_path.write_bytes(_json_bytes(metadata))
    return readiness_path, master_path, output_a, output_b, metadata_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--guideline", type=Path)
    parser.add_argument("--readiness-only", action="store_true")
    parser.add_argument("--refresh-metadata-only", action="store_true")
    args = parser.parse_args()
    if args.readiness_only:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        readiness_path = args.output_dir / "readiness.json"
        readiness_path.write_bytes(_json_bytes(assess_campaign_readiness(args.manifest, project_root=args.project_root)))
        print(readiness_path)
        return
    if args.refresh_metadata_only:
        metadata_path = args.output_dir / "metadata.json"
        metadata_path.write_bytes(_json_bytes(build_campaign_metadata(
            args.manifest, args.output_dir, project_root=args.project_root,
            guideline_path=args.guideline,
        )))
        print(metadata_path)
        return
    for path in prepare_campaign(args.manifest, args.output_dir, project_root=args.project_root, guideline_path=args.guideline):
        print(path)


if __name__ == "__main__":
    main()
