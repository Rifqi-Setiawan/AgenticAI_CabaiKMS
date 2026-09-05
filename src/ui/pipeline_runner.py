"""Fase 8 — pipeline runner behind the Streamlit UI.

Wires together what's already built (Fase 3 schema-matching, Fase 4 Drive
crawler, Fase 5 vision classification, Fase 6 tabular update, Fase 7
reliability wrappers, and Fase 2's checkpointed stub orchestrator) into one
function the UI calls. No new agent logic lives here — this module is glue
+ presentation-shaping, same spirit as eval/review_schema_matching.py.

The "hasil akhir" this produces is a real instance of the canonical
template's shape (data/canonical/template_kanonik.xlsx) — same row
labels, read dynamically — with varietas columns taken from whatever the
uploaded file's anchor column (row-oriented) or column headers
(transposed) actually contain. A canonical row nothing mapped to is left
blank; if Drive has no images (or none is given), the Gambar rows are
simply left blank too — see src/ui/output_builder.py.

Kept deliberately synchronous and capped (see max_images) — this is the
prototype phase named in the brief ("Overhead minimal; semua render dari
Python"), not a production job queue.
"""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import openpyxl
import pandas as pd

from src.agents.drive_crawler import DriveCrawlerError, list_images, normalize_folder_id
from src.agents.schema_matching.anchor import AnchorCandidate, detect_anchor
from src.agents.schema_matching.indexing import ensure_indexed
from src.agents.schema_matching.normalize import normalize
from src.agents.schema_matching.review_queue import AcceptanceStatus, decide_mapping_acceptance
from src.agents.schema_matching.retrieval import DEFAULT_K, SourceAttributeProfile, retrieve
from src.agents.schema_matching.source_parsing import load_row_oriented_columns, load_transposed_rows
from src.agents.tabular_update import apply_vision_result_to_worksheet
from src.agents.vision_classification import VisionSession
from src.ingestion.shadow_pipeline import run_structure_shadow, sanitize_shadow_error_message
from src.orchestrator.graph import run_pipeline
from src.reliability.wrappers import safe_classify_image, safe_rerank
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW
from src.schema.provenance import CellProvenanceRecord, source_file_sha256
from src.schema.shadow_parity import ShadowParityReport, ShadowStatus
from src.ui.output_builder import SHEET_NAME, CanonicalOutputBuilder, combine_multi_value, values_by_variety, worksheet_to_dataframe

MAPPING_COLUMNS = [
    "source_attribute_display",
    "source_attribute",
    "source_context",
    "predicted_row",
    "predicted_label",
    "target_domain",
    "confidence",
    "normalization_required",
    "reasoning",
    "acceptance_status",
    "acceptance_reason",
    "canonical_write",
]

ProgressCallback = Callable[[str], None]


@dataclass
class PipelineRunResult:
    mapping_df: pd.DataFrame
    canonical_df: pd.DataFrame
    workbook_bytes: bytes
    vision_rows: list[dict]
    provenance_records: list[CellProvenanceRecord] = field(default_factory=list)
    agent_status: dict[str, str] = field(default_factory=dict)
    checkpoint_thread_id: str = ""
    error_trace: list[str] = field(default_factory=list)
    structure_shadow: ShadowParityReport | None = None


def _noop(_: str) -> None:
    return None


def _deterministic_workbook_bytes(workbook) -> bytes:
    """Serialize equivalent workbooks identically despite OpenPyXL save timestamps."""
    raw = io.BytesIO()
    workbook.save(raw)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw.getvalue()), "r") as source:
        with zipfile.ZipFile(output, "w") as target:
            target.comment = source.comment
            for original in source.infolist():
                payload = source.read(original.filename)
                if original.filename == "docProps/core.xml":
                    payload = re.sub(
                        rb"(<dcterms:modified[^>]*>).*?(</dcterms:modified>)",
                        rb"\g<1>2000-01-01T00:00:00Z\g<2>",
                        payload,
                    )
                stable = zipfile.ZipInfo(original.filename, (2000, 1, 1, 0, 0, 0))
                stable.compress_type = original.compress_type
                stable.comment = original.comment
                stable.extra = original.extra
                stable.internal_attr = original.internal_attr
                stable.external_attr = original.external_attr
                stable.create_system = original.create_system
                target.writestr(stable, payload)
    return output.getvalue()


def run_pipeline_ui(
    file_path: Path,
    *,
    source_format: str = "row-oriented",
    sheet_name: str | None = None,
    header_rows: int | None = None,
    drive_folder_id: str | None = None,
    k: int = DEFAULT_K,
    max_images: int = 5,
    on_progress: ProgressCallback = _noop,
    enable_structure_shadow: bool = False,
    structure_llm_call: Callable | None = None,
) -> PipelineRunResult:
    run_id = uuid.uuid4().hex
    resolved_sheet_name = sheet_name or _first_sheet(file_path)
    source_hash = source_file_sha256(file_path)
    state: dict = {"error_trace": []}
    agent_status: dict[str, str] = {}
    structure_shadow: ShadowParityReport | None = None

    # --- parsing + variety-column discovery ---
    on_progress(f"Memuat berkas: {file_path.name} (format={source_format!r})")
    if source_format == "row-oriented":
        parsed = load_row_oriented_columns(
            file_path, resolved_sheet_name, header_rows=header_rows,
        )
        on_progress(f"Header sumber: {[p.attribute_name for p in parsed]}")
        candidates = [AnchorCandidate(p.attribute_name, p.sample_values) for p in parsed]
        anchor_result = detect_anchor(candidates, source_format="row-oriented")
        on_progress(f"Deteksi anchor: status={anchor_result.status!r} kolom={anchor_result.column_name!r}")

        anchor_attr = next((p for p in parsed if p.attribute_name == anchor_result.column_name), None)
        if anchor_result.status != "found" or anchor_attr is None:
            raise ValueError(
                "Kolom varietas tidak ditemukan. Periksa jumlah baris header dan "
                "nama kolom identitas (misalnya Variety atau Jenis Cabai). "
                "Proses dihentikan agar tidak menghasilkan workbook kosong."
            )
        position_to_variety = [v.strip() if v is not None else None for v in anchor_attr.row_values]
        for index, variety in enumerate(position_to_variety):
            if not variety and any(
                p.row_values[index] is not None and str(p.row_values[index]).strip()
                for p in parsed
            ):
                raise ValueError(
                    f"Varietas kosong pada observasi ke-{index + 1}. "
                    "Isi kolom varietas sebelum menjalankan pipeline."
                )
        variety_names_seen: list[str] = []
        for v in position_to_variety:
            if v and v not in variety_names_seen:
                variety_names_seen.append(v)
        attributes = [p for p in parsed if p.attribute_name != anchor_result.column_name]
    else:
        on_progress("Format transposed — anchor tidak diperlukan (varietas sudah jadi header kolom).")
        parsed, variety_names_seen = load_transposed_rows(file_path, resolved_sheet_name)
        position_to_variety = variety_names_seen  # row_values[i] <-> variety_names_seen[i]
        attributes = parsed

    if not variety_names_seen:
        raise ValueError("Tidak ada varietas untuk keluaran. Periksa header dan isi data sumber.")
    on_progress(f"Atribut untuk schema matching: {len(attributes)}")
    on_progress(f"Varietas terdeteksi dari sumber: {variety_names_seen}")

    # Observation-only migration path. Legacy values above remain the sole
    # authority for every downstream operation regardless of this outcome.
    if enable_structure_shadow:
        on_progress("structure_shadow: membandingkan legacy parser dengan Source IR...")
        try:
            structure_shadow = run_structure_shadow(
                file_path,
                resolved_sheet_name,
                source_format=source_format,
                header_rows=header_rows,
                llm_call=structure_llm_call,
                anchor_detector=detect_anchor,
            )
        except Exception as exc:  # noqa: BLE001 - shadow must never abort primary work
            message = sanitize_shadow_error_message(exc)
            structure_shadow = ShadowParityReport(
                status=ShadowStatus.NEW_PATH_FAILED,
                source_format=source_format,
                issue_codes=["SHADOW_RUNNER_EXCEPTION"],
                new_path_error_type=type(exc).__name__,
                new_path_error_message=message,
                summary="NEW_PATH_FAILED — isolated shadow exception; legacy pipeline continued",
            )
        agent_status["structure_shadow"] = structure_shadow.summary
        on_progress(f"structure_shadow: {structure_shadow.summary}")

    schema = CanonicalSchema.from_template()
    on_progress("Memastikan indeks ChromaDB (idempoten)...")
    ensure_indexed(schema)

    builder = CanonicalOutputBuilder(schema=schema)
    for name in variety_names_seen:
        builder.add_variety(name)

    # --- schema matching (Fase 3, via the Fase 7 reliability wrapper) ---
    mapping_rows: list[dict] = []
    provenance_records: list[CellProvenanceRecord] = []
    n_auto_accept = 0
    n_review = 0
    n_no_write = 0

    for attr in attributes:
        on_progress(f"  schema_matching: '{attr.attribute_name}' — retrieval...")
        profile = SourceAttributeProfile(
            attribute_name=attr.attribute_name,
            structural_context=attr.structural_context,
            sample_values=attr.sample_values,
        )
        retrieved = retrieve(profile, k=k, schema=schema)

        on_progress(f"  schema_matching: '{attr.attribute_name}' — reranking...")
        mapping, patch = safe_rerank(profile, retrieved, state, source_format=source_format, schema=schema)
        state.update(patch)  # safe_* returns a patch; the caller applies it — see wrappers.py
        acceptance = decide_mapping_acceptance(mapping, reliability_patch=patch)

        target_row = (
            schema.row_by_id(mapping.target_canonical_row)
            if mapping is not None and mapping.target_canonical_row != NULL_ROW
            else None
        )
        mapping_row = {
            "source_attribute_display": attr.display_name,
            "source_attribute": attr.attribute_name,
            "source_context": attr.structural_context,
            "predicted_row": mapping.target_canonical_row if mapping is not None else None,
            "predicted_label": target_row.label if target_row else None,
            "target_domain": mapping.target_domain if mapping is not None else None,
            "confidence": mapping.confidence if mapping is not None else None,
            "normalization_required": mapping.normalization_required if mapping is not None else None,
            "reasoning": mapping.reasoning if mapping is not None else None,
            "acceptance_status": acceptance.status.value,
            "acceptance_reason": acceptance.reason,
            "canonical_write": False,
        }
        mapping_rows.append(mapping_row)

        # Selective-acceptance safety invariant: only AUTO_ACCEPT may cross
        # this boundary into normalization or canonical mutation.
        if not acceptance.allows_canonical_write:
            if acceptance.status is AcceptanceStatus.REVIEW:
                n_review += 1
            else:
                n_no_write += 1
            on_progress(
                f"  schema_matching: '{attr.attribute_name}' -> {acceptance.status.value}, "
                f"tidak ditulis: {acceptance.reason}"
            )
            continue

        n_auto_accept += 1

        on_progress(
            f"  schema_matching: '{attr.attribute_name}' -> {mapping.target_canonical_row} "
            f"(confidence={mapping.confidence:.2f}, AUTO_ACCEPT)"
        )

        if target_row is None:
            # Defensive fail-closed guard. The decision function must never
            # AUTO_ACCEPT an absent/NULL/unknown target.
            continue

        grouped = values_by_variety(attr.row_values, position_to_variety)
        for variety_name, raw_values in grouped.items():
            combined = combine_multi_value(raw_values)
            if combined is None:
                continue
            normalized = normalize(combined, target_row)
            written = builder.set_cell(target_row.id, variety_name, normalized.value)
            if written:
                mapping_row["canonical_write"] = True
                provenance_records.append(
                    CellProvenanceRecord(
                        run_id=run_id,
                        source_file_name=file_path.name,
                        source_file_sha256=source_hash,
                        source_sheet=resolved_sheet_name,
                        source_attribute=attr.attribute_name,
                        source_context=attr.structural_context,
                        source_attribute_display=attr.display_name,
                        source_cells=[],
                        variety=variety_name,
                        canonical_row_id=target_row.id,
                        canonical_key=target_row.canonical_key,
                        canonical_label=target_row.label,
                        canonical_domain=target_row.domain,
                        raw_value=combined,
                        normalized_value=normalized.value,
                        normalization_required=mapping.normalization_required,
                        mapping_confidence=mapping.confidence,
                        acceptance_status=acceptance.status.value,
                        acceptance_reason=acceptance.reason,
                        schema_version=schema.schema_version,
                        template_hash=schema.template_hash,
                    )
                )

    agent_status["schema_matching"] = (
        f"selesai — {len(mapping_rows)} atribut: {n_auto_accept} AUTO_ACCEPT, "
        f"{n_review} REVIEW, {n_no_write} NO_WRITE"
    )

    mapping_df = pd.DataFrame(mapping_rows, columns=MAPPING_COLUMNS)
    if not mapping_df.empty:
        mapping_df = mapping_df.sort_values("confidence", ascending=True, kind="stable").reset_index(drop=True)

    # --- materialize the canonical-shaped workbook (schema-matching values only, so far) ---
    workbook = builder.build_workbook()
    worksheet = workbook[SHEET_NAME]

    # --- vision classification (Fase 4 + 5, via the Fase 7 wrapper), writing
    # straight onto the SAME worksheet via Fase 6's own tabular_update logic ---
    vision_rows: list[dict] = []
    folder_id = (drive_folder_id or "").strip()
    if not folder_id:
        agent_status["vision_classification"] = "dilewati (tidak ada folder Drive)"
        on_progress("vision_classification: dilewati — tidak ada folder Drive diberikan.")
    else:
        try:
            on_progress(f"vision_classification: membuka folder Drive {folder_id!r}...")
            images = list_images(normalize_folder_id(folder_id))[:max_images]
            if not images:
                agent_status["vision_classification"] = "dilewati (folder Drive kosong, tidak ada citra)"
                on_progress("vision_classification: folder Drive kosong — dilewati.")
            else:
                on_progress(f"vision_classification: {len(images)} citra ditemukan (dibatasi {max_images})")
                session = VisionSession()
                n_uncertain = 0
                n_written = 0
                for image in images:
                    on_progress(f"  vision_classification: '{image.filename}'...")
                    result, patch = safe_classify_image(
                        image, session.knowledge_source_text, session.varieties, state,
                    )
                    state.update(patch)
                    if result is None:
                        on_progress(f"  vision_classification: '{image.filename}' -> GAGAL, diarahkan ke manual_review")
                        continue
                    if result.classification_status == "UNCERTAIN":
                        n_uncertain += 1
                    on_progress(
                        f"  vision_classification: '{image.filename}' -> {result.classification_status} "
                        f"({result.identified_part}, varietas={result.matched_variety})"
                    )
                    update_result = apply_vision_result_to_worksheet(worksheet, image, result)
                    if update_result.applied:
                        n_written += 1
                    elif update_result.reason:
                        on_progress(f"    tidak ditulis ke sel: {update_result.reason}")
                    vision_rows.append(
                        {
                            "filename": image.filename,
                            "status": result.classification_status,
                            "matched_variety": result.matched_variety,
                            "identified_part": result.identified_part,
                            "confidence": result.confidence,
                            "visual_evidence": result.visual_evidence,
                        }
                    )
                agent_status["vision_classification"] = (
                    f"selesai — {len(vision_rows)} citra diklasifikasi, {n_written} ditulis ke sel, "
                    f"{n_uncertain} UNCERTAIN"
                )
        except DriveCrawlerError as exc:
            agent_status["vision_classification"] = f"gagal: {exc}"
            on_progress(f"vision_classification: GAGAL — {exc}")

    canonical_df = worksheet_to_dataframe(worksheet, schema, builder.variety_names)

    workbook_bytes = _deterministic_workbook_bytes(workbook)

    # --- checkpointed stub orchestrator run (Fase 2), purely so the UI's
    # checkpoint debugger has a real thread/checkpoint to open ---
    thread_id = run_id
    on_progress(f"orchestrator: menjalankan graf (thread_id={thread_id})...")
    run_pipeline(str(file_path), f"drive-folder:{folder_id or '-'}", thread_id=thread_id)
    agent_status["orchestrator"] = f"checkpoint tersimpan (thread_id={thread_id})"
    on_progress("orchestrator: checkpoint tersimpan.")

    on_progress("Selesai.")

    return PipelineRunResult(
        mapping_df=mapping_df,
        canonical_df=canonical_df,
        workbook_bytes=workbook_bytes,
        vision_rows=vision_rows,
        provenance_records=provenance_records,
        agent_status=agent_status,
        checkpoint_thread_id=thread_id,
        error_trace=list(state.get("error_trace", [])),
        structure_shadow=structure_shadow,
    )


def _first_sheet(path: Path) -> str:
    wb = openpyxl.load_workbook(path, read_only=True)
    name = wb.sheetnames[0]
    wb.close()
    return name
