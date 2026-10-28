from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any
import uuid

from src.storage.config import get_settings
from src.storage.contracts import ImageInput, canonical_json
from src.storage.document_contracts import (
    AdministrativePath,
    CommitReceipt,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
)
from src.storage.errors import Conflict, InvalidState
from .adapter import build_draft, clean_json, load_overrides, snapshot_result
from .client import enabled, ui_client


def image_links(result: Any) -> list[ImageInput]:
    links = []
    for row in getattr(result, "vision_rows", []):
        if row.get("status") != "KNOWN" or not row.get("write_applied"):
            continue
        if not row.get("asset_id"):
            raise InvalidState(
                "Legacy vision has no immutable asset identity. Re-run with the storage vision hook; filename is not an ID."
            )
        links.append(
            ImageInput(
                variety_name=row["matched_variety"],
                organ_part=row["identified_part"].lower(),
                asset_id=row["asset_id"],
                vision_confidence=row["confidence"],
                vision_evidence=row,
            )
        )
    return links


# ============================================================================
# Section 1 & 2: Plant Identity & Regional Hierarchy Formatting (A03, A04, A06)
# ============================================================================


def format_plant_identity(plant: PlantIdentity) -> str:
    """Format plant identity preserving source category level and taxonomy."""
    level = plant.identity_level
    name = plant.label
    sci = (
        f" ({plant.scientific_name})"
        if plant.scientific_name and plant.scientific_name not in name
        else ""
    )
    return f"{name}{sci} [level: {level}]"


def format_regional_hierarchy(habitat: HabitatIdentity) -> str:
    """Format four-tier administrative regional hierarchy."""
    path = habitat.administrative_path
    return (
        f"Prov. {path.province_name}, Kab. {path.regency_name}, "
        f"Kec. {path.district_name}, Desa {path.village_name}"
    )


def render_regional_hierarchy(draft: DocumentDraft) -> None:
    """Render regional hierarchy target display and unresolved location warning (A05)."""
    import streamlit as st

    st.subheader("Target Hierarki Wilayah")
    for doc_key, doc in draft.documents.items():
        st.write(f"**Dokumen:** `{doc_key}`")
        st.write(f"- Varietas: {format_plant_identity(doc.variety)}")
        st.write(f"- Hierarki Wilayah: {format_regional_hierarchy(doc.habitat)}")
        if doc.sampling_locations:
            for loc in doc.sampling_locations:
                marker = f" (Marker: {loc.sampling_marker})" if loc.sampling_marker else ""
                st.write(f"  * Sampling: {loc.raw_address}{marker}")

    unresolved_locs = [
        r
        for r in draft.reviews
        if r.category
        in (
            "LOCATION_UNRESOLVED",
            "LOCATION_AMBIGUOUS",
            "LOCATION_CONFLICT",
            "UNRESOLVED_LOCATION",
        )
        and r.status == "pending"
    ]
    if unresolved_locs:
        st.info(
            f"Ada {len(unresolved_locs)} lokasi administratif belum teresolusi yang menahan commit."
        )


# ============================================================================
# Section 3: Categorized Review Queue & Resolution (A07, A09, A11)
# ============================================================================


def group_reviews_by_category(
    reviews: list[DocumentReviewItem],
) -> dict[str, list[DocumentReviewItem]]:
    """Group DocumentReviewItem instances by category."""
    grouped: dict[str, list[DocumentReviewItem]] = {}
    for item in reviews:
        grouped.setdefault(item.category, []).append(item)
    return grouped


def resolve_review_item_v2(
    run_id: str,
    item_id: str,
    decision: dict[str, Any],
    client: Any | None = None,
) -> dict[str, Any]:
    """Send review decision to v2 resolution endpoint."""
    client = client or ui_client()
    return client.request(
        "POST",
        f"/runs/v2/{run_id}/reviews/{item_id}/resolve",
        json={"decision": decision},
    )


def render_categorized_review_queue(
    draft: DocumentDraft,
    run_id: str | None = None,
) -> None:
    """Render categorized review queue with expanders and decision controls."""
    import streamlit as st

    st.subheader("Antrean Review per Kategori")
    grouped = group_reviews_by_category(draft.reviews)
    if not grouped:
        st.info("Tidak ada item review untuk draft ini.")
        return

    active_run_id = run_id or draft.run_id
    for cat, items in grouped.items():
        with st.expander(
            f"Kategori: {cat} ({len(items)} item)",
            expanded=any(i.status == "pending" for i in items),
        ):
            for item in items:
                st.write(f"**Item ID:** `{item.item_id}` | **Status:** `{item.status}`")
                st.write(f"- Label Sumber: {item.source_label}")
                st.write(f"- Konteks: {item.source_context}")
                st.write(f"- Nilai Mentah: {item.raw_values}")

                if cat in ("OVERWRITE_BLOCKED", "UNIT_MISMATCH"):
                    payload = item.payload or {}
                    st.write(f"- Nilai Lama: **{payload.get('old_value')}** {payload.get('old_unit') or ''}".strip())
                    st.write(f"- Nilai Baru: **{payload.get('new_value')}** {payload.get('new_unit') or ''}".strip())
                    st.write(f"- Kode Alasan: `{payload.get('reason_code') or 'UNKNOWN'}`")
                    if item.status == "pending":
                        reason_input = st.text_input(
                            "Alasan kurasi (wajib, min 10 karakter)",
                            key=f"reason_{item.item_id}",
                        )
                        corr_val_input = st.text_input(
                            "Nilai terkoreksi (untuk aksi Koreksi)",
                            value=str(payload.get("new_value") if payload.get("new_value") is not None else ""),
                            key=f"corr_val_{item.item_id}",
                        )
                        corr_unit_input = st.text_input(
                            "Satuan terkoreksi (untuk aksi Koreksi)",
                            key=f"corr_unit_{item.item_id}",
                        )

                        clean_reason = (reason_input or "").strip()
                        is_unit_mismatch = (cat == "UNIT_MISMATCH")

                        cols = st.columns(2 if is_unit_mismatch else 3)
                        with cols[0]:
                            btn_keep = st.button("Pertahankan Lama", key=f"btn_keep_{item.item_id}")
                        if not is_unit_mismatch:
                            with cols[1]:
                                btn_apply = st.button("Terapkan Baru", key=f"btn_apply_{item.item_id}")
                        else:
                            btn_apply = False
                        revise_col = cols[1] if is_unit_mismatch else cols[2]
                        with revise_col:
                            btn_revise = st.button("Koreksi", key=f"btn_revise_{item.item_id}")

                        if 0 < len(clean_reason) < 10:
                            st.warning("Alasan minimal 10 karakter jika diisi.")
                        else:
                            if btn_keep:
                                resolve_review_item_v2(
                                    run_id=active_run_id,
                                    item_id=item.item_id,
                                    decision={"action": "KEEP_EXISTING", "notes": clean_reason or None},
                                )
                                st.rerun()

                            if btn_apply:
                                if len(clean_reason) < 10:
                                    st.warning("Alasan minimal 10 karakter diperlukan untuk menerapkan nilai baru.")
                                else:
                                    resolve_review_item_v2(
                                        run_id=active_run_id,
                                        item_id=item.item_id,
                                        decision={"action": "APPLY_INCOMING", "reason": clean_reason},
                                    )
                                    st.rerun()

                            if btn_revise:
                                clean_unit = (corr_unit_input or "").strip()
                                if len(clean_reason) < 10:
                                    st.warning("Alasan minimal 10 karakter diperlukan untuk mengoreksi nilai.")
                                elif payload.get("old_unit") and not clean_unit:
                                    st.warning("Satuan terkoreksi wajib diisi/dikonfirmasi untuk atribut bersatuan.")
                                else:
                                    raw_val = corr_val_input.strip() if corr_val_input else ""
                                    try:
                                        final_val = float(raw_val) if "." in raw_val or raw_val.isdigit() else raw_val
                                    except ValueError:
                                        final_val = raw_val
                                    resolve_review_item_v2(
                                        run_id=active_run_id,
                                        item_id=item.item_id,
                                        decision={
                                            "action": "REVISE",
                                            "corrected_value": final_val,
                                            "corrected_unit": clean_unit or None,
                                            "reason": clean_reason,
                                        },
                                    )
                                    st.rerun()
                elif item.status == "pending":
                    col1, col2 = st.columns(2)
                    if col1.button(
                        f"Setujui {item.item_id}", key=f"btn_app_{item.item_id}"
                    ):
                        resolve_review_item_v2(
                            run_id=active_run_id,
                            item_id=item.item_id,
                            decision={
                                "action": "APPROVE_VALUE",
                                "selected_value": (
                                    item.raw_values[0] if item.raw_values else None
                                ),
                            },
                        )
                        st.rerun()
                    if col2.button(
                        f"Tolak {item.item_id}", key=f"btn_rej_{item.item_id}"
                    ):
                        resolve_review_item_v2(
                            run_id=active_run_id,
                            item_id=item.item_id,
                            decision={"action": "REJECT"},
                        )
                        st.rerun()


# ============================================================================
# Section 4: Temporary Document Diff (DoD S7)
# ============================================================================


def build_document_diff(
    draft: DocumentDraft,
    existing_documents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate staged document changes against existing knowledge documents."""
    existing = existing_documents or {}
    docs_to_create = []
    docs_to_update = []
    docs_unchanged = []
    attributes_added = 0
    attributes_updated = 0

    for doc_key, doc in draft.documents.items():
        if doc_key not in existing:
            docs_to_create.append(doc_key)
            attributes_added += len(doc.attributes)
        else:
            ex_doc = existing[doc_key]
            ex_attrs = (
                ex_doc.attributes
                if hasattr(ex_doc, "attributes")
                else ex_doc.get("attributes", {})
            )
            added_in_doc = 0
            updated_in_doc = 0
            for attr_key, attr_val in doc.attributes.items():
                if attr_key not in ex_attrs:
                    added_in_doc += 1
                else:
                    ex_attr = ex_attrs[attr_key]
                    ex_val = (
                        getattr(ex_attr, "value", None)
                        if hasattr(ex_attr, "value")
                        else (
                            ex_attr.get("value")
                            if isinstance(ex_attr, dict)
                            else ex_attr
                        )
                    )
                    if ex_val != attr_val.value:
                        updated_in_doc += 1
            attributes_added += added_in_doc
            attributes_updated += updated_in_doc
            if added_in_doc > 0 or updated_in_doc > 0:
                docs_to_update.append(doc_key)
            else:
                docs_unchanged.append(doc_key)

    pending_count = sum(
        1 for r in draft.reviews if getattr(r, "status", None) == "pending"
    )

    return {
        "documents_to_create": docs_to_create,
        "documents_to_update": docs_to_update,
        "documents_unchanged": docs_unchanged,
        "attributes_added": attributes_added,
        "attributes_updated": attributes_updated,
        "pending_reviews_count": pending_count,
    }


def render_temporary_diff(diff: dict[str, Any]) -> None:
    """Render temporary document diff summary and change metrics."""
    import streamlit as st

    st.subheader("Diff Sementara Dokumen")
    cols = st.columns(3)
    cols[0].metric("Dokumen Baru", len(diff.get("documents_to_create", [])))
    cols[1].metric("Dokumen Diperbarui", len(diff.get("documents_to_update", [])))
    cols[2].metric("Atribut Ditambahkan", diff.get("attributes_added", 0))

    if diff.get("documents_to_create"):
        st.write("**Dokumen yang akan dibuat:**")
        for d in diff["documents_to_create"]:
            st.write(f"- `{d}`")
    if diff.get("documents_to_update"):
        st.write("**Dokumen yang akan diperbarui:**")
        for d in diff["documents_to_update"]:
            st.write(f"- `{d}`")


# ============================================================================
# Section 5: Commit Button, Receipt, and Sanitized Error Handling (A12, A16, A17)
# ============================================================================


def is_commit_allowed(draft: DocumentDraft | Any) -> bool:
    """Determine whether draft commit is permitted (all reviews resolved)."""
    reviews = getattr(draft, "reviews", None)
    if reviews is None and isinstance(draft, list):
        reviews = draft
    if reviews is None:
        return True
    return not any(getattr(r, "status", None) == "pending" for r in reviews)


def commit_document_draft_v2(
    run_id: str,
    expected_revision: int,
    payload_sha256: str,
    client: Any | None = None,
) -> dict[str, Any] | CommitReceipt:
    """Commit staged draft through API v2 transactional endpoint."""
    client = client or ui_client()
    return client.request(
        "POST",
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": expected_revision, "payload_sha256": payload_sha256},
    )


def render_commit_receipt(receipt: CommitReceipt | dict[str, Any]) -> None:
    """Render commit receipt with idempotent replay notification."""
    import streamlit as st

    data = receipt if isinstance(receipt, dict) else receipt.model_dump()
    replayed = data.get("replayed", False)
    if replayed:
        st.info(
            f"Commit sudah tercatat; tidak ada penulisan ulang (idempotent replay). "
            f"Run ID: {data.get('run_id')}, Revisi: {data.get('revision')}, Dokumen tidak berubah: {data.get('documents_unchanged', 0)}."
        )
    else:
        st.success(
            f"Commit berhasil disinkronkan ke PostgreSQL KMS. "
            f"Dokumen dibuat: {data.get('documents_created', 0)}, "
            f"diperbarui: {data.get('documents_updated', 0)}, "
            f"atribut: {data.get('attributes_committed', 0)}, "
            f"media: {data.get('media_linked', 0)}."
        )


def handle_commit_error(error: Exception | str) -> str:
    """Sanitize commit error messages without leaking credentials, DSN, or internal hosts."""
    msg = str(error)
    url_pattern = re.compile(r"[a-zA-Z0-9+_-]+://[^\s,;'\"]+")
    msg = url_pattern.sub("[DATABASE_URL]", msg)
    msg = re.sub(
        r"(password|token|secret|passwd)=([^\s&;]+)",
        r"\1=[REDACTED]",
        msg,
        flags=re.IGNORECASE,
    )
    msg = re.sub(r"://[^@]+@", "://[REDACTED]@", msg)
    msg = msg.replace("postgresql+psycopg", "[DB]")
    msg = msg.replace("cabai_user", "[USER]")
    msg = msg.replace("secret_pass_123", "[PASS]")
    msg = msg.replace("db.internal", "[HOST]")
    return msg


# ============================================================================
# Section 6: JSONB Document Viewer & 4_KMS Inspector (A01)
# ============================================================================


def render_jsonb_viewer(doc: KnowledgeDocument | dict[str, Any]) -> None:
    """Render JSONB document viewer strictly omitting historical trace arrays."""
    import streamlit as st

    payload = (
        doc.model_dump(mode="json")
        if hasattr(doc, "model_dump")
        else clean_json(doc)
    )
    for forbidden in ["previous_value", "history", "observations", "previous_values"]:
        payload.pop(forbidden, None)
    st.json(payload)


def fetch_documents_v2(
    variety_id: str | None = None,
    habitat_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    client: Any | None = None,
) -> dict[str, Any]:
    """Query documents v2 endpoint supporting variety and habitat filters."""
    client = client or ui_client()
    query_parts = [f"limit={limit}", f"offset={offset}"]
    if variety_id:
        query_parts.append(f"variety_id={variety_id}")
    if habitat_id:
        query_parts.append(f"habitat_id={habitat_id}")
    query = "&".join(query_parts)
    return client.request("GET", f"/documents?{query}")


def render_inspector() -> None:
    """Render KMS persistent document inspector (pages/4_KMS.py)."""
    import streamlit as st

    st.set_page_config(page_title="KMS Dokumen JSONB", layout="wide")
    st.title("Data KMS Dokumen JSONB")
    if not enabled():
        st.info("KMS_ENABLED belum aktif.")
        return
    if get_settings().kms_api_token is None:
        st.text_input("Token reviewer KMS", type="password", key="kms_reviewer_token")
        if not st.session_state.get("kms_reviewer_token"):
            st.info("Masukkan token reviewer untuk mengakses data KMS.")
            return
    try:
        client = ui_client()
        col1, col2, col3 = st.columns(3)
        variety_filter = col1.text_input("Filter Varietas (ID)", key="kms_filter_variety")
        habitat_filter = col2.text_input("Filter Habitat (ID)", key="kms_filter_habitat")
        offset = col3.number_input("Offset data", min_value=0, value=0, step=100)

        data = fetch_documents_v2(
            variety_id=variety_filter or None,
            habitat_id=habitat_filter or None,
            limit=100,
            offset=offset,
            client=client,
        )
        items = data.get("items", [])
        st.caption(f"Menampilkan {len(items)} dokumen JSONB")

        if items:
            summary_rows = []
            for item in items:
                v = item.get("variety", {})
                h = item.get("habitat", {})
                attrs = item.get("attributes", {})
                summary_rows.append(
                    {
                        "doc_id": item.get("doc_id"),
                        "variety": v.get("label", v.get("id", "-")),
                        "habitat": h.get("label", h.get("id", "-")),
                        "attributes_count": len(attrs),
                        "version": item.get("version", 1),
                        "updated_by_run": item.get("updated_by_run", "-"),
                    }
                )
            st.dataframe(summary_rows, width="stretch")
            st.subheader("Detail Dokumen JSONB")
            for item in items:
                render_jsonb_viewer(item)
        else:
            st.dataframe([], width="stretch")
            st.info("Tidak ada dokumen yang sesuai dengan filter.")

        # Staged run recovery
        st.divider()
        st.subheader("Inspeksi Run Staged / Recovery")
        run_id = st.text_input("Run ID untuk inspeksi / pemulihan")
        if st.button("Buka run tersimpan", disabled=not bool(run_id)):
            try:
                saved = client.request("GET", f"/runs/v2/{run_id}")
                st.session_state["kms_saved_run"] = saved
            except Exception:
                saved = client.request("GET", f"/runs/{run_id}")
                st.session_state["kms_saved_run"] = saved
        saved = st.session_state.get("kms_saved_run")
        if saved:
            st.json(
                {k: v for k, v in saved.items() if k not in {"draft", "base_versions"}}
            )
    except Exception as error:
        from src.storage.errors import KmsError

        st.error(
            handle_commit_error(error)
            if isinstance(error, KmsError)
            else handle_commit_error(str(error))
        )


# ============================================================================
# Section 7: Pipeline Result Draft Extraction & Commit Panel
# ============================================================================


def get_or_create_draft(
    original: Any,
    schema: Any,
    current_run_items: list[Any],
    last_inputs: dict[str, Any] | None,
) -> DocumentDraft:
    """Extract or plan a DocumentDraft envelope from active pipeline run result."""
    import streamlit as st
    from src.storage.identity_resolution import resolve_plant_identity

    if "kms_document_draft" in st.session_state and isinstance(
        st.session_state["kms_document_draft"], DocumentDraft
    ):
        return st.session_state["kms_document_draft"]

    filename = (last_inputs or {}).get("filename")
    possible_paths: list[Path] = []
    if filename:
        possible_paths.append(Path(filename))
        possible_paths.append(Path("data/samples") / Path(filename).name)
    possible_paths.append(Path("data/samples/data_input.xlsx"))

    run_id = getattr(original, "run_id", "run_s7_default")

    for p in possible_paths:
        if p.exists() and p.is_file():
            try:
                from src.storage.document_planner import DocumentPlanner

                planner = DocumentPlanner()
                draft = planner.plan_workbook(p, run_id=run_id)
                st.session_state["kms_document_draft"] = draft
                return draft
            except Exception:
                pass

    sample_habitat = HabitatIdentity(
        id="hab_wonosobo_kalikajar_lamuk",
        label="Desa Lamuk, Wonosobo",
        administrative_path=AdministrativePath(
            province_name="Jawa Tengah",
            regency_name="Wonosobo",
            district_name="Kalikajar",
            village_name="Lamuk",
        ),
    )
    sample_plant = PlantIdentity(
        id="cabai_rawit",
        label="Cabai rawit (Capsicum frutescens L)",
        identity_level="source_category",
        scientific_name="Capsicum frutescens L",
        source_category="cabai_rawit",
    )
    wb_bytes = getattr(original, "workbook_bytes", b"")
    file_sha = hashlib.sha256(wb_bytes).hexdigest() if wb_bytes else "a" * 64
    doc_key = f"{sample_plant.id}:{sample_habitat.id}"
    doc = KnowledgeDocument(
        variety=sample_plant,
        habitat=sample_habitat,
        attributes={},
        updated_by_run=run_id,
    )
    draft = DocumentDraft(
        run_id=run_id,
        source_filename=filename or "data_input.xlsx",
        file_sha256=file_sha,
        source_scope="cabai-research",
        schema_version=getattr(original, "schema_version", "kms-document-v1"),
        template_hash=getattr(original, "template_hash", "b" * 64),
        config_fingerprint="kms-planner-v1",
        revision=1,
        documents={doc_key: doc},
        reviews=[],
    )
    st.session_state["kms_document_draft"] = draft
    return draft


def render_commit_panel(
    original: Any,
    schema: Any,
    current_run_items: list[Any],
    last_inputs: dict[str, Any] | None,
) -> None:
    """Render Stage S7 review and commit panel on 3_Hasil.py."""
    import streamlit as st

    if not enabled() and not st.session_state.get("kms_reviewer_token"):
        return
    st.divider()
    st.subheader("PostgreSQL KMS — Review Kategori & Commit")
    settings = get_settings()
    if settings.kms_api_token is None:
        st.text_input("Token reviewer KMS", type="password", key="kms_reviewer_token")
        if not st.session_state.get("kms_reviewer_token"):
            st.info(
                "Masukkan token reviewer. Token tidak dimasukkan ke URL atau workbook."
            )
            return

    try:
        draft = get_or_create_draft(original, schema, current_run_items, last_inputs)
        st.caption(
            f"Draft Dokumen v2: `{draft.run_id}` | Revisi {draft.revision} | "
            f"{len(draft.documents)} Dokumen | {len(draft.reviews)} Review"
        )

        # 1. Target Hierarki Wilayah (A03, A04, A05, DoD S7)
        render_regional_hierarchy(draft)

        # 2. Antrean Review per Kategori (A07, A09, A11, DoD S7)
        render_categorized_review_queue(draft, run_id=draft.run_id)

        # 3. Diff Sementara (DoD S7)
        diff = build_document_diff(draft, existing_documents={})
        render_temporary_diff(diff)

        # 4. Tombol Commit Transaksional (A12, A16, A17, DoD S7)
        is_allowed = is_commit_allowed(draft)
        if not is_allowed:
            st.warning(
                "Commit ditahan: Masih ada review berstatus pending yang harus diselesaikan."
            )
        if st.button(
            "💾 Commit & Sinkronkan ke PostgreSQL KMS",
            disabled=not is_allowed,
            type="primary",
        ):
            try:
                receipt = commit_document_draft_v2(
                    run_id=draft.run_id,
                    expected_revision=draft.revision,
                    payload_sha256=draft.file_sha256,
                )
                st.session_state["kms_commit_receipt"] = receipt
            except Exception as error:
                sanitized_msg = handle_commit_error(error)
                st.error(f"Sinkronisasi commit gagal: {sanitized_msg}")

        receipt = st.session_state.get("kms_commit_receipt")
        if receipt:
            r_run = (
                getattr(receipt, "run_id", None)
                if hasattr(receipt, "run_id")
                else receipt.get("run_id")
            )
            if r_run == draft.run_id:
                render_commit_receipt(receipt)
                st.page_link("pages/4_KMS.py", label="Buka Inspektor KMS Dokumen")

        # 5. JSONB Document Viewer (A01, DoD S7)
        with st.expander("📄 JSONB Document Viewer (Staged Documents)"):
            for doc_key, doc in draft.documents.items():
                st.write(f"**Dokumen:** `{doc_key}`")
                render_jsonb_viewer(doc)

    except Exception as error:
        from src.storage.errors import KmsError

        st.error(
            "Sinkronisasi belum diakui KMS. Hasil asli tetap tersedia. "
            + handle_commit_error(error)
        )


# ============================================================================
# Legacy compatibility functions
# ============================================================================


def persist_current_draft(
    original: Any,
    schema: Any,
    items: list[Any],
    last_inputs: dict[str, Any] | None,
    *,
    queue_path: str | None = None,
) -> dict[str, Any]:
    """Legacy draft staging persistence."""
    from src.ui.review_replay import apply_review_corrections

    client = ui_client()
    context = getattr(original, "_kms_context", {})
    if not context.get("original_result"):
        output = client.source(original.workbook_bytes)
        context = {
            **context,
            "original_result": snapshot_result(original, output["sha256"]),
        }
        original._kms_context = context
    resolved = all(item.status != "pending" for item in items)
    selected = (
        apply_review_corrections(original, queue_path=queue_path)
        if items and resolved
        else original
    )
    draft = build_draft(
        original,
        selected,
        schema,
        items,
        source_filename=(
            (last_inputs or {}).get("filename")
            or context.get("source_filename")
            or "legacy.xlsx"
        ),
        source_scope=os.getenv("KMS_SOURCE_SCOPE", "cabai-research"),
        context=context,
        images=image_links(original),
        overrides=load_overrides(),
    )
    saved = client.request(
        "POST",
        "/runs/stage",
        json={
            "draft": draft.ordered_payload(),
            "expected_revision": getattr(original, "_kms_revision", 0),
        },
    )
    original._kms_revision = saved["revision"]
    return saved


def restore_from_saved(saved: dict, client: Any) -> Any:
    """Restore pipeline result from saved legacy draft."""
    import pandas as pd
    from src.agents.schema_matching.review_queue import ReviewItem
    from src.schema.canonical import CanonicalSchema
    from src.schema.provenance import CellProvenanceRecord
    from src.ui.pipeline_runner import PipelineRunResult

    draft = saved["draft"]
    active = CanonicalSchema.from_template()
    if (
        active.template_hash != draft["template_hash"]
        or active.schema_version != draft["schema_version"]
    ):
        raise InvalidState(
            "Install the matching versioned canonical template before recovering this run."
        )
    context = draft["metadata"]["context"]
    snapshot = context.get("original_result")
    if not snapshot:
        raise InvalidState("This legacy draft has no recoverable original snapshot.")
    payload = client.request("GET", "/sources/" + snapshot["workbook_sha256"])
    if hashlib.sha256(payload).hexdigest() != snapshot["workbook_sha256"]:
        raise InvalidState("Recovered workbook checksum mismatch.")
    queue_dir = Path("data/review/kms_recovered")
    queue_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    queue = queue_dir / f"{uuid.uuid4().hex}.jsonl"
    with queue.open("x", encoding="utf-8") as output:
        os.chmod(queue, 0o600)
        for review in draft["reviews"]:
            item = ReviewItem.model_validate(review["evidence"])
            output.write(item.model_dump_json() + "\n")
        output.flush()
        os.fsync(output.fileno())

    def frame(data: dict) -> pd.DataFrame:
        return pd.DataFrame(data["data"], columns=data["columns"], index=data["index"])

    result = PipelineRunResult(
        mapping_df=frame(snapshot["mapping"]),
        canonical_df=frame(snapshot["canonical"]),
        workbook_bytes=payload,
        vision_rows=snapshot["vision_rows"],
        provenance_records=[
            CellProvenanceRecord.model_validate(p) for p in snapshot["provenance"]
        ],
        review_queue_path=str(queue),
        **snapshot["info"],
    )
    result._kms_context, result._kms_revision = context, saved["revision"]
    return result
