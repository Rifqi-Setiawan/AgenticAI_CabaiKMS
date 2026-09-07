"""Apply current-run human review decisions without rerunning any model stage."""

from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import openpyxl

from src.agents.schema_matching.review_queue import list_for_run
from src.agents.schema_matching.normalize import normalize
from src.schema.canonical import CanonicalSchema
from src.schema.provenance import CellProvenanceRecord
from src.ui.output_builder import (
    SHEET_NAME, append_unique_value, combine_multi_value, worksheet_to_dataframe,
)
from src.ui.pipeline_runner import PipelineRunResult, _deterministic_workbook_bytes


def apply_review_corrections(
    original: PipelineRunResult,
    *,
    queue_path: Path | str | None = None,
    schema: CanonicalSchema | None = None,
) -> PipelineRunResult:
    """Rebuild corrected output from the immutable original result and event log."""
    schema = schema or CanonicalSchema.from_template()
    if not original.run_id:
        raise ValueError("pipeline result has no run_id; deterministic review replay is unavailable")
    if original.schema_version != schema.schema_version or original.template_hash != schema.template_hash:
        raise ValueError("active canonical schema differs from the reviewed pipeline run")
    queue = Path(queue_path or original.review_queue_path)
    items = list_for_run(original.run_id, queue)
    pending = [item.item_id for item in items if item.status == "pending"]
    if pending:
        raise ValueError(f"all current-run review items must be resolved before replay: {pending}")

    workbook = openpyxl.load_workbook(io.BytesIO(original.workbook_bytes))
    worksheet = workbook[SHEET_NAME]
    corrected_mapping = original.mapping_df.copy(deep=True)
    provenance = list(original.provenance_records)
    row_number_by_id = {row.id: index + 2 for index, row in enumerate(schema.rows)}
    varieties = [str(cell.value) for cell in worksheet[1][2:] if cell.value not in (None, "")]

    try:
        for item in sorted(items, key=lambda value: value.item_id):
            mask = corrected_mapping["review_item_id"] == item.item_id
            matches = corrected_mapping.loc[mask]
            if len(matches) != 1:
                raise ValueError(f"review item must bind exactly one pipeline observation: {item.item_id}")
            observation = matches.iloc[0]
            if item.mapping_item_id != observation["mapping_item_id"]:
                raise ValueError(f"review item mapping identity mismatch: {item.item_id}")
            if item.source_file_sha256 != observation["source_file_sha256"]:
                raise ValueError(f"review item source fingerprint mismatch: {item.item_id}")
            if item.source_sheet != observation["source_sheet"]:
                raise ValueError(f"review item source sheet mismatch: {item.item_id}")
            if item.source_format != observation["source_format"]:
                raise ValueError(f"review item source format mismatch: {item.item_id}")
            if item.schema_version != schema.schema_version or item.template_hash != schema.template_hash:
                raise ValueError(f"review item canonical schema binding mismatch: {item.item_id}")

            corrected_mapping.loc[mask, "review_status"] = item.status.upper()
            corrected_mapping.loc[mask, "final_canonical_key"] = item.final_canonical_key
            corrected_mapping.loc[mask, "canonical_write"] = False
            if item.status == "no_match":
                continue
            target = schema.row_by_key(item.final_canonical_key or "")
            if target is None:
                raise ValueError(f"resolved review item has no valid final canonical key: {item.item_id}")
            original_mapping = item.original_mapping or item.mapping
            for variety, raw_values in item.raw_values_by_variety.items():
                if variety not in varieties:
                    raise ValueError(f"review item contains unknown output variety {variety!r}")
                combined = combine_multi_value(raw_values)
                if combined is None:
                    continue
                normalized = normalize(combined, target)
                row_number = row_number_by_id[target.id]
                column_number = 3 + varieties.index(variety)
                cell = worksheet.cell(row=row_number, column=column_number)
                updated, changed = append_unique_value(cell.value, normalized.value)
                if not changed:
                    continue
                cell.value = updated
                corrected_mapping.loc[mask, "canonical_write"] = True
                provenance.append(CellProvenanceRecord(
                    run_id=original.run_id,
                    source_file_name=item.source_file_name or "",
                    source_file_sha256=item.source_file_sha256 or "",
                    source_sheet=item.source_sheet or "",
                    source_attribute=original_mapping.source_attribute,
                    source_context=original_mapping.source_context,
                    source_attribute_display=item.source_attribute_display or original_mapping.source_attribute,
                    source_cells=item.source_cells_by_variety.get(variety, []),
                    source_attribute_id=item.source_attribute_id,
                    source_header_cells=item.source_header_cells,
                    source_ir_version=item.source_ir_version,
                    variety=variety,
                    canonical_row_id=target.id,
                    canonical_key=target.canonical_key,
                    canonical_label=target.label,
                    canonical_domain=target.domain,
                    raw_value=combined,
                    normalized_value=normalized.value,
                    normalization_required=original_mapping.normalization_required,
                    mapping_confidence=original_mapping.confidence,
                    acceptance_status="HUMAN_REVIEW",
                    acceptance_reason=f"human_review:{item.status}",
                    schema_version=schema.schema_version,
                    template_hash=schema.template_hash,
                    mapping_method="human_review",
                    verifier_status=item.verifier_status,
                    verifier_hard_issues=item.verifier_hard_issues,
                    review_item_id=item.item_id,
                    review_resolution=item.status,
                    resolved_by=item.resolved_by,
                    resolved_at=item.resolved_at.isoformat() if item.resolved_at else None,
                    original_proposed_canonical_key=item.proposed_canonical_key,
                    original_mapping_confidence=original_mapping.confidence,
                    original_verifier_status=item.verifier_status,
                ))
        canonical_df = worksheet_to_dataframe(worksheet, schema, varieties)
        return replace(
            original,
            canonical_df=canonical_df,
            workbook_bytes=_deterministic_workbook_bytes(workbook),
            provenance_records=provenance,
            mapping_df=corrected_mapping,
        )
    finally:
        workbook.close()
