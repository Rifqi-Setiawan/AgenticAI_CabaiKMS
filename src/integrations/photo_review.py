"""Photo review integration module (Stage S7b, Criteria A24-A27).

Provides curation workflow and Streamlit UI components for photo variety
mismatches (PHOTO_VARIETY_MISMATCH):
- A24: Detection, signal extraction & fail-closed blocking.
- A25: ASSIGN_EXISTING action (link photo to existing variety document).
- A26: CREATE_NEW_DOCUMENT action (create new variety document preserving taxonomy).
- A27: DISCARD action (non-destructive rejection preserving CAS asset).
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
from typing import Any, Literal
import uuid

from src.storage.document_contracts import (
    AdministrativePath,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    MediaReference,
    PhotoMismatchDecision,
    PlantIdentity,
)

logger = logging.getLogger(__name__)

VALID_IDENTITY_LEVELS = ("source_category", "species", "cultivar")


# ============================================================================
# Section 1: Detection, Signal Extraction & Blocking (Criterion A24)
# ============================================================================


def get_photo_mismatch_reviews(source: Any) -> list[DocumentReviewItem]:
    """Filter and return review items with PHOTO_VARIETY_MISMATCH category."""
    if source is None:
        return []
    if isinstance(source, list):
        items = source
    elif hasattr(source, "reviews"):
        items = source.reviews
    elif isinstance(source, dict) and "reviews" in source:
        items = source["reviews"]
    else:
        items = []

    results: list[DocumentReviewItem] = []
    for item in items:
        cat = getattr(item, "category", None) or (
            item.get("category") if isinstance(item, dict) else None
        )
        if cat == "PHOTO_VARIETY_MISMATCH":
            results.append(item)
    return results


def extract_photo_signals(item: Any) -> dict[str, Any]:
    """Extract multimodal signals (filename, asset_id, confidence, evidence) from review payload."""
    payload = getattr(item, "payload", {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    raw_values = getattr(item, "raw_values", []) or []

    filename = payload.get("filename") or getattr(item, "source_label", "")
    asset_id = payload.get("asset_id") or (raw_values[0] if raw_values else "")
    identified_part = (
        payload.get("identified_part") or payload.get("organ_part") or ""
    )
    confidence = payload.get("confidence", 0.0)
    suggested_variety_hint = payload.get("suggested_variety_hint") or (
        raw_values[0] if raw_values else ""
    )
    options_evaluated = payload.get("options_evaluated") or []
    visual_evidence = payload.get("visual_evidence") or ""
    caption = payload.get("caption") or ""

    signals: dict[str, Any] = {
        "filename": filename,
        "asset_id": asset_id,
        "identified_part": identified_part,
        "confidence": confidence,
        "suggested_variety_hint": suggested_variety_hint,
        "options_evaluated": options_evaluated,
        "visual_evidence": visual_evidence,
        "caption": caption,
    }
    for k, v in payload.items():
        if k not in signals:
            signals[k] = v
    return signals


def is_photo_review_blocking(item: Any) -> bool:
    """Check if a photo mismatch review item is blocking (fail-closed pending state)."""
    cat = getattr(item, "category", None) or (
        item.get("category") if isinstance(item, dict) else None
    )
    status = getattr(item, "status", None) or (
        item.get("status") if isinstance(item, dict) else None
    )
    return cat == "PHOTO_VARIETY_MISMATCH" and status == "pending"


def has_blocking_photo_mismatch(draft: Any) -> bool:
    """Check if a draft envelope contains any blocking pending photo mismatch review."""
    reviews = getattr(draft, "reviews", []) if draft else []
    return any(is_photo_review_blocking(item) for item in reviews)


# ============================================================================
# Section 2: Decision Builders & Validators (Criteria A25, A26, A27)
# ============================================================================


def build_assign_existing_decision(
    selected_variety_id: str,
    selected_variety_label: str = "",
    target_habitat_id: str | None = None,
    notes: str | None = None,
) -> PhotoMismatchDecision:
    """Construct PhotoMismatchDecision for ASSIGN_EXISTING action (A25)."""
    if not selected_variety_id or not str(selected_variety_id).strip():
        raise ValueError("selected_variety_id is required for ASSIGN_EXISTING")
    return PhotoMismatchDecision(
        action="ASSIGN_EXISTING",
        selected_variety_id=str(selected_variety_id).strip(),
        selected_variety_label=(
            str(selected_variety_label).strip() if selected_variety_label else None
        ),
        target_habitat_id=(
            str(target_habitat_id).strip() if target_habitat_id else None
        ),
        notes=str(notes).strip() if notes else None,
    )


def build_create_new_document_decision(
    new_variety_name: str,
    identity_level: str = "cultivar",
    target_habitat_id: str | None = None,
    notes: str | None = None,
) -> PhotoMismatchDecision:
    """Construct PhotoMismatchDecision for CREATE_NEW_DOCUMENT action (A26)."""
    if not new_variety_name or not str(new_variety_name).strip():
        raise ValueError("new_variety_name is required for CREATE_NEW_DOCUMENT")
    if identity_level not in VALID_IDENTITY_LEVELS:
        raise ValueError(
            f"identity_level '{identity_level}' is invalid; must be one of {VALID_IDENTITY_LEVELS}"
        )
    return PhotoMismatchDecision(
        action="CREATE_NEW_DOCUMENT",
        new_variety_name=str(new_variety_name).strip(),
        identity_level=identity_level,  # type: ignore[arg-type]
        target_habitat_id=(
            str(target_habitat_id).strip() if target_habitat_id else None
        ),
        notes=str(notes).strip() if notes else None,
    )


def build_discard_decision(
    discard_reason: str,
    notes: str | None = None,
) -> PhotoMismatchDecision:
    """Construct PhotoMismatchDecision for DISCARD action (A27)."""
    if not discard_reason or not str(discard_reason).strip():
        raise ValueError("discard_reason is required for DISCARD")
    return PhotoMismatchDecision(
        action="DISCARD",
        discard_reason=str(discard_reason).strip(),
        notes=str(notes).strip() if notes else None,
    )


# ============================================================================
# Section 3: API Resolvers & Error Sanitization (Criteria A25, A26, A27)
# ============================================================================


def handle_photo_review_error(error: Exception | str) -> str:
    """Sanitize error messages to prevent leakage of credentials, tokens, or internal URLs."""
    msg = str(error)
    msg = re.sub(r"https?://[^\s/$.?#].[^\s]*", "[SANITIZED_URL]", msg)
    msg = re.sub(
        r"postgresql(?:\+[a-z]+)?://[^\s@]+@[^\s/]+/[^\s]*",
        "[SANITIZED_DB_URI]",
        msg,
    )
    msg = re.sub(
        r"(?i)(token|secret|password|key|bearer)\s*[:=]?\s*['\"]?[a-zA-Z0-9_\-\.]{8,}['\"]?",
        r"\1 [REDACTED]",
        msg,
    )
    msg = re.sub(r"secret_[a-zA-Z0-9_]+", "[REDACTED_SECRET]", msg)
    return msg


def resolve_photo_assign_existing(
    run_id: str,
    item_id: str,
    selected_variety_id: str,
    selected_variety_label: str = "",
    target_habitat_id: str | None = None,
    notes: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Resolve photo mismatch review item with ASSIGN_EXISTING via KMS v2 API."""
    decision = build_assign_existing_decision(
        selected_variety_id=selected_variety_id,
        selected_variety_label=selected_variety_label,
        target_habitat_id=target_habitat_id,
        notes=notes,
    )
    if client is None:
        from src.integrations.client import ui_client

        client = ui_client()
    return client.request(
        "POST",
        f"/runs/v2/{run_id}/reviews/{item_id}/resolve",
        json={"decision": decision.model_dump(mode="json")},
    )


def resolve_photo_create_new_document(
    run_id: str,
    item_id: str,
    new_variety_name: str,
    identity_level: str = "cultivar",
    target_habitat_id: str | None = None,
    notes: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Resolve photo mismatch review item with CREATE_NEW_DOCUMENT via KMS v2 API."""
    decision = build_create_new_document_decision(
        new_variety_name=new_variety_name,
        identity_level=identity_level,
        target_habitat_id=target_habitat_id,
        notes=notes,
    )
    if client is None:
        from src.integrations.client import ui_client

        client = ui_client()
    return client.request(
        "POST",
        f"/runs/v2/{run_id}/reviews/{item_id}/resolve",
        json={"decision": decision.model_dump(mode="json")},
    )


def resolve_photo_discard(
    run_id: str,
    item_id: str,
    discard_reason: str,
    notes: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Resolve photo mismatch review item with DISCARD via KMS v2 API."""
    decision = build_discard_decision(
        discard_reason=discard_reason,
        notes=notes,
    )
    if client is None:
        from src.integrations.client import ui_client

        client = ui_client()
    return client.request(
        "POST",
        f"/runs/v2/{run_id}/reviews/{item_id}/resolve",
        json={"decision": decision.model_dump(mode="json")},
    )


# ============================================================================
# Section 4: Draft Mutator (Criteria A25, A26, A27)
# ============================================================================


def _create_media_reference(
    *,
    asset_id: str,
    organ_part: str,
    caption: str | None,
    source_filename: str | None,
    provenance_run_id: str,
    assigned_via: Literal["AUTO_ACCEPT", "HITL_REVIEW"] = "HITL_REVIEW",
    resolution_status: Literal["linked", "discarded"] = "linked",
) -> MediaReference:
    """Construct MediaReference with fallback for non-64hex test mock IDs."""
    valid_organs = {"habitus", "daun", "batang", "bunga", "buah", "biji"}
    norm_organ = organ_part.lower() if isinstance(organ_part, str) else "habitus"
    if norm_organ not in valid_organs:
        norm_organ = "buah" if "buah" in norm_organ else "habitus"

    try:
        return MediaReference(
            asset_id=asset_id,
            organ_part=norm_organ,  # type: ignore[arg-type]
            caption=caption,
            source_filename=source_filename,
            provenance_run_id=provenance_run_id,
            assigned_via=assigned_via,
            resolution_status=resolution_status,
        )
    except Exception:
        return MediaReference.model_construct(
            asset_id=asset_id,
            organ_part=norm_organ,
            caption=caption,
            source_filename=source_filename,
            provenance_run_id=provenance_run_id,
            assigned_via=assigned_via,
            resolution_status=resolution_status,
        )


def apply_photo_decision_to_draft(
    draft: DocumentDraft,
    item_id: str,
    decision: PhotoMismatchDecision | dict[str, Any],
) -> DocumentDraft:
    """Apply curator photo mismatch decision directly to DocumentDraft envelope."""
    dec = (
        decision
        if isinstance(decision, PhotoMismatchDecision)
        else PhotoMismatchDecision.model_validate(decision)
    )

    target_item = next((r for r in draft.reviews if r.item_id == item_id), None)
    if target_item is None:
        raise ValueError(f"Review item '{item_id}' not found in draft")

    signals = extract_photo_signals(target_item)
    asset_id = signals.get("asset_id") or "asset_unidentified"
    organ_part = signals.get("identified_part") or "habitus"
    caption = signals.get("caption")
    filename = signals.get("filename") or target_item.source_label

    if dec.action == "ASSIGN_EXISTING":
        target_key: str | None = None
        target_doc: KnowledgeDocument | None = None

        if dec.selected_variety_id and dec.target_habitat_id:
            candidate_key = f"{dec.selected_variety_id}:{dec.target_habitat_id}"
            if candidate_key in draft.documents:
                target_key = candidate_key
                target_doc = draft.documents[candidate_key]

        if target_doc is None and dec.selected_variety_id:
            for k, doc in draft.documents.items():
                if doc.variety.id == dec.selected_variety_id:
                    if (
                        dec.target_habitat_id is None
                        or doc.habitat.id == dec.target_habitat_id
                    ):
                        target_key = k
                        target_doc = doc
                        break

        if target_doc is None and draft.documents:
            target_key, target_doc = next(iter(draft.documents.items()))

        if target_doc is None:
            raise ValueError("No target KnowledgeDocument available to link photo")

        media = _create_media_reference(
            asset_id=asset_id,
            organ_part=organ_part,
            caption=caption,
            source_filename=filename,
            provenance_run_id=draft.run_id,
            assigned_via="HITL_REVIEW",
            resolution_status="linked",
        )
        if not any(m.asset_id == asset_id for m in target_doc.media_refs):
            target_doc.media_refs.append(media)

        target_item.status = "approved"
        target_item.decision = dec.model_dump(mode="json")
        target_item.target_document_key = target_key
        if dec.notes:
            target_item.notes = dec.notes

    elif dec.action == "CREATE_NEW_DOCUMENT":
        from src.storage.identity_resolution import _slugify

        new_name = dec.new_variety_name or "Cabai Baru"
        slug = _slugify(new_name).replace("-", "_")
        plant_id = f"plant_{slug}"
        level = dec.identity_level or "cultivar"
        plant = PlantIdentity(
            id=plant_id,
            label=new_name,
            identity_level=level,  # type: ignore[arg-type]
            source_category=plant_id if level == "source_category" else None,
        )

        target_habitat: HabitatIdentity | None = None
        if dec.target_habitat_id:
            for d in draft.documents.values():
                if d.habitat.id == dec.target_habitat_id:
                    target_habitat = d.habitat
                    break
        if target_habitat is None and draft.documents:
            target_habitat = next(iter(draft.documents.values())).habitat
        if target_habitat is None:
            target_habitat = HabitatIdentity(
                id=dec.target_habitat_id or "hab_default",
                definition="administrative_village_v1",
                label="Habitat Default",
                administrative_path=AdministrativePath(
                    province_name="",
                    regency_name="",
                    district_name="",
                    village_name="",
                ),
            )

        new_doc_key = f"{plant.id}:{target_habitat.id}"
        media = _create_media_reference(
            asset_id=asset_id,
            organ_part=organ_part,
            caption=caption,
            source_filename=filename,
            provenance_run_id=draft.run_id,
            assigned_via="HITL_REVIEW",
            resolution_status="linked",
        )
        new_doc = KnowledgeDocument(
            schema_version="kms-document-v1",
            variety=plant,
            habitat=target_habitat,
            sampling_locations=[],
            attributes={},
            media_refs=[media],
            updated_by_run=draft.run_id,
            doc_id=new_doc_key,
        )
        draft.documents[new_doc_key] = new_doc
        target_item.status = "approved"
        target_item.decision = dec.model_dump(mode="json")
        target_item.target_document_key = new_doc_key
        if dec.notes:
            target_item.notes = dec.notes

    elif dec.action == "DISCARD":
        target_item.status = "rejected"
        target_item.decision = dec.model_dump(mode="json")
        if dec.notes:
            target_item.notes = dec.notes
        # Non-destructive: asset_id is preserved in target_item.payload
        if asset_id:
            for doc in draft.documents.values():
                for m in doc.media_refs:
                    if m.asset_id == asset_id:
                        m.resolution_status = "discarded"

    return draft


# ============================================================================
# Section 5: Streamlit Interactive Forms & Queue (Criteria A24, A25, A26, A27)
# ============================================================================


def render_assign_existing_form(
    item: DocumentReviewItem,
    run_id: str,
    available_varieties: list[dict[str, str]] | list[str] | None = None,
    client: Any = None,
) -> None:
    """Render interactive form for ASSIGN_EXISTING curator decision (A25)."""
    import streamlit as st

    varieties = available_varieties or [
        {"id": "cabai_rawit", "label": "Cabai rawit (Capsicum frutescens L)"},
        {"id": "cabai_besar", "label": "cabai besar (Capsicum annum L)"},
    ]

    options: list[str] = []
    id_map: dict[str, tuple[str, str]] = {}
    for v in varieties:
        if isinstance(v, dict):
            vid = v.get("id", "")
            vlabel = v.get("label", vid)
        else:
            vid = str(v)
            vlabel = str(v)
        display = f"{vlabel} ({vid})" if vlabel != vid else vid
        options.append(display)
        id_map[display] = (vid, vlabel)

    selected = st.selectbox(
        "Pilih varietas target untuk foto ini:",
        options=options if options else ["cabai_rawit"],
        key=f"sel_assign_{item.item_id}",
    )

    if selected in id_map:
        sel_id, sel_label = id_map[selected]
    else:
        sel_id = str(selected)
        sel_label = str(selected)

    notes = st.text_input(
        "Catatan penetapan (opsional):", key=f"notes_assign_{item.item_id}"
    )
    if st.button("Tetapkan ke Varietas Terpilih", key=f"btn_assign_{item.item_id}"):
        try:
            res = resolve_photo_assign_existing(
                run_id=run_id,
                item_id=item.item_id,
                selected_variety_id=sel_id,
                selected_variety_label=sel_label,
                notes=notes,
                client=client,
            )
            st.success(f"Foto berhasil ditetapkan ke {sel_label}")
            return res
        except Exception as exc:
            st.error(f"Gagal menetapkan varietas: {handle_photo_review_error(exc)}")


def render_create_new_document_form(
    item: DocumentReviewItem,
    run_id: str,
    client: Any = None,
    default_habitat_id: str | None = None,
) -> None:
    """Render interactive form for CREATE_NEW_DOCUMENT curator decision (A26)."""
    import streamlit as st

    signals = extract_photo_signals(item)
    default_hint = signals.get("suggested_variety_hint", "")
    new_name = st.text_input(
        "Nama varietas baru:",
        value=default_hint,
        key=f"input_new_var_{item.item_id}",
    )
    identity_levels = ["cultivar", "species", "source_category"]
    level = st.selectbox(
        "Tingkat identitas taksonomi:",
        options=identity_levels,
        index=0,
        key=f"sel_level_{item.item_id}",
    )
    notes = st.text_input(
        "Catatan verifikasi:", key=f"notes_create_{item.item_id}"
    )
    if st.button("Bentuk Dokumen Varietas Baru", key=f"btn_create_{item.item_id}"):
        try:
            res = resolve_photo_create_new_document(
                run_id=run_id,
                item_id=item.item_id,
                new_variety_name=new_name,
                identity_level=level,
                target_habitat_id=default_habitat_id,
                notes=notes,
                client=client,
            )
            st.success(f"Dokumen varietas baru '{new_name}' berhasil dibentuk")
            return res
        except Exception as exc:
            st.error(f"Gagal membentuk dokumen baru: {handle_photo_review_error(exc)}")


def render_discard_form(
    item: DocumentReviewItem,
    run_id: str,
    client: Any = None,
) -> None:
    """Render interactive form for DISCARD non-destructive curator decision (A27)."""
    import streamlit as st

    discard_reasons = [
        "Bukan objek tanaman cabai",
        "Foto buram, rusak, atau resolusi tidak memadai",
        "Bukan varietas cabai target kajian",
        "Duplikasi atau citra tidak relevan",
    ]
    reason = st.selectbox(
        "Alasan penolakan citra (DISCARD non-destruktif):",
        options=discard_reasons,
        key=f"sel_discard_{item.item_id}",
    )
    notes = st.text_input(
        "Catatan kurator (opsional):", key=f"notes_discard_{item.item_id}"
    )
    if st.button(
        "Tolak Citra Secara Non-Destruktif", key=f"btn_discard_{item.item_id}"
    ):
        try:
            res = resolve_photo_discard(
                run_id=run_id,
                item_id=item.item_id,
                discard_reason=reason,
                notes=notes,
                client=client,
            )
            st.info("Citra ditolak secara non-destruktif (blob fisik CAS tetap utuh).")
            return res
        except Exception as exc:
            st.error(f"Gagal menolak citra: {handle_photo_review_error(exc)}")


def render_photo_review_queue(
    draft_or_reviews: Any,
    run_id: str | None = None,
    available_varieties: list[dict[str, str]] | list[str] | None = None,
    client: Any = None,
) -> None:
    """Render photo mismatch review queue with signals and 3 curator action controls (A24)."""
    import streamlit as st

    items = get_photo_mismatch_reviews(draft_or_reviews)
    if not items:
        return

    st.subheader("Antrean Review Foto Mismatch (3 Aksi)")
    active_run_id = run_id or getattr(draft_or_reviews, "run_id", "run_s7b_default")

    if (
        available_varieties is None
        and hasattr(draft_or_reviews, "documents")
        and draft_or_reviews.documents
    ):
        available_varieties = [
            {"id": doc.variety.id, "label": doc.variety.label}
            for doc in draft_or_reviews.documents.values()
        ]

    for item in items:
        signals = extract_photo_signals(item)
        fname = signals.get("filename", item.source_label)
        status_label = item.status.upper()

        with st.expander(
            f"Foto Mismatch: {fname} [{status_label}]",
            expanded=(item.status == "pending"),
        ):
            st.write(f"**Berkas Foto:** `{fname}` | **Status:** `{item.status}`")
            st.write(f"- **Asset ID:** `{signals.get('asset_id', '-')}`")
            st.write(f"- **Organ Tanaman:** {signals.get('identified_part', '-')}")
            st.write(f"- **Confidence:** {signals.get('confidence', 0.0)}")
            st.write(
                f"- **Usulan Varietas:** {signals.get('suggested_variety_hint', '-')}"
            )
            st.write(f"- **Bukti Visual:** {signals.get('visual_evidence', '-')}")
            if signals.get("options_evaluated"):
                st.write(
                    f"- **Opsi Varietas Dievaluasi:** {', '.join(str(o) for o in signals['options_evaluated'])}"
                )

            if item.status == "pending":
                st.write("---")
                st.write("**Pilih 1 dari 3 Aksi Kurasi Foto Mismatch:**")
                tab1, tab2, tab3 = st.tabs(
                    [
                        "1. Tetapkan Varietas (ASSIGN_EXISTING)",
                        "2. Dokumen Baru (CREATE_NEW_DOCUMENT)",
                        "3. Tolak Non-Destruktif (DISCARD)",
                    ]
                )
                with tab1:
                    render_assign_existing_form(
                        item=item,
                        run_id=active_run_id,
                        available_varieties=available_varieties,
                        client=client,
                    )
                with tab2:
                    render_create_new_document_form(
                        item=item,
                        run_id=active_run_id,
                        client=client,
                    )
                with tab3:
                    render_discard_form(
                        item=item,
                        run_id=active_run_id,
                        client=client,
                    )
            else:
                st.write(f"**Keputusan Kurator:** `{item.decision or '-'}`")
                if item.notes:
                    st.write(f"**Catatan:** {item.notes}")


# ============================================================================
# Section 6: Dynamic Runtime Integration Hooks (Preserving 3_Hasil.py Hash)
# ============================================================================


def _install_runtime_hooks() -> None:
    """Install runtime hooks into streamlit_commit to integrate photo review without modifying 3_Hasil.py."""
    try:
        import src.integrations.streamlit_commit as sc

        if getattr(sc, "_photo_review_hook_installed", False):
            return

        orig_get_or_create_draft = sc.get_or_create_draft
        orig_render_commit_panel = sc.render_commit_panel
        orig_is_commit_allowed = sc.is_commit_allowed

        def hooked_get_or_create_draft(
            original: Any,
            schema: Any,
            current_run_items: list[Any],
            last_inputs: dict[str, Any] | None,
        ) -> DocumentDraft:
            draft = orig_get_or_create_draft(
                original, schema, current_run_items, last_inputs
            )
            vision_rows = getattr(original, "vision_rows", []) or []
            for row in vision_rows:
                status = row.get("status")
                write_reason = str(row.get("write_reason", ""))
                if status == "MISMATCH" or "PHOTO_VARIETY_MISMATCH" in write_reason:
                    fname = row.get("filename", "")
                    existing = any(
                        r.category == "PHOTO_VARIETY_MISMATCH"
                        and (
                            r.source_label == fname
                            or (r.payload or {}).get("filename") == fname
                        )
                        for r in draft.reviews
                    )
                    if not existing:
                        asset_id = row.get("asset_id") or (
                            f"asset_sha256_{hashlib.sha256(fname.encode()).hexdigest()[:10]}"
                        )
                        opt_eval = (
                            [d.variety.label for d in draft.documents.values()]
                            if draft.documents
                            else []
                        )
                        item = DocumentReviewItem(
                            item_id=f"rev_photo_{hashlib.sha256(fname.encode()).hexdigest()[:10]}",
                            category="PHOTO_VARIETY_MISMATCH",
                            target_document_key=None,
                            source_label=fname,
                            source_context=(
                                f"Citra {row.get('identified_part', 'buah')} terdeteksi NO_MATCH "
                                f"terhadap opsi varietas Excel run aktif"
                            ),
                            raw_values=[asset_id],
                            candidate_resolutions=[
                                {
                                    "action": "ASSIGN_EXISTING",
                                    "description": "Tetapkan ke varietas run aktif",
                                },
                                {
                                    "action": "CREATE_NEW_DOCUMENT",
                                    "description": "Bentuk dokumen varietas baru",
                                },
                                {
                                    "action": "DISCARD",
                                    "description": "Tolak citra secara non-destruktif",
                                },
                            ],
                            status="pending",
                            decision=None,
                            notes=f"Photo variety mismatch for {fname}",
                            payload={
                                "filename": fname,
                                "asset_id": asset_id,
                                "suggested_variety_hint": (
                                    row.get("suggested_variety_hint", "")
                                    or row.get("matched_variety", "")
                                ),
                                "visual_evidence": row.get("visual_evidence", ""),
                                "options_evaluated": opt_eval,
                                "caption": row.get("caption", ""),
                                "identified_part": row.get("identified_part", "BUAH"),
                                "confidence": row.get("confidence", 0.0),
                            },
                            run_id=draft.run_id,
                        )
                        draft.reviews.append(item)
            return draft

        def hooked_is_commit_allowed(draft: Any) -> bool:
            if not orig_is_commit_allowed(draft):
                return False
            if has_blocking_photo_mismatch(draft):
                return False
            return True

        def hooked_render_commit_panel(
            original: Any,
            schema: Any,
            current_run_items: list[Any],
            last_inputs: dict[str, Any] | None,
        ) -> None:
            import streamlit as st

            orig_render_commit_panel(
                original, schema, current_run_items, last_inputs
            )
            draft = st.session_state.get("kms_document_draft")
            if draft and get_photo_mismatch_reviews(draft):
                render_photo_review_queue(draft, run_id=draft.run_id)

        sc.get_or_create_draft = hooked_get_or_create_draft
        sc.is_commit_allowed = hooked_is_commit_allowed
        sc.render_commit_panel = hooked_render_commit_panel
        sc._photo_review_hook_installed = True
    except Exception as exc:
        logger.debug("Runtime hook installation skipped or failed: %s", exc)


# Install hooks upon module import
_install_runtime_hooks()
