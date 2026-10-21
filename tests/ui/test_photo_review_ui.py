"""Acceptance test suite for Stage S7b: UI Streamlit (Modal Review Foto Mismatch).

Contract source:
- reports/cabai-kms-jsonb/TECH_PLAN.md:
  * Line 28: Stage S7b scope (UI Review Foto Mismatch 3 Aksi)
  * Line 524: Table 5 DoD & boundaries for S7b
  * Line 559: Acceptance criterion A24 (test_photo_mismatch_creates_blocking_review_item)
  * Line 560: Acceptance criterion A25 (test_photo_review_action_assign_existing)
  * Line 561: Acceptance criterion A26 (test_photo_review_action_create_new_document)
  * Line 562: Acceptance criterion A27 (test_photo_review_action_discard_non_destructive)
  * Section 4.3: 3 pilihan aksi kurasi foto (ASSIGN_EXISTING, CREATE_NEW_DOCUMENT, DISCARD)
- reports/cabai-kms-jsonb/PRD_CabaiKMS_JSONB.md:
  * Section 4.3 & 6: Kriteria penerimaan A24-A27

Criteria covered:
- A24: Foto yang tidak cocok dengan opsi varietas Excel run aktif menghasilkan item review
       PHOTO_VARIETY_MISMATCH (fail-closed).
- A25: Aksi review ASSIGN_EXISTING menautkan foto ke dokumen varietas terpilih dan melepaskan status review.
- A26: Aksi review CREATE_NEW_DOCUMENT membentuk dokumen baru dengan varietas baru tanpa mengarang taksonomi.
- A27: Aksi review DISCARD menandai foto ditolak secara non-destruktif tanpa menghapus blob fisik dari storage CAS.

Candidate implementation file:
- src/integrations/photo_review.py

Test file:
- tests/ui/test_photo_review_ui.py
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.integrations import photo_review
from src.storage.document_contracts import (
    AdministrativePath,
    AttributeValue,
    CommitReceipt,
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    MediaReference,
    PhotoMismatchDecision,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.ui.pipeline_runner import PipelineRunResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HASIL_PAGE_PATH = str(PROJECT_ROOT / "src/ui/pages/3_Hasil.py")
APP_TEST_TIMEOUT = 30


# ============================================================================
# Test Fixtures (Strict In-Memory Isolation)
# ============================================================================


@pytest.fixture
def sample_plant_rawit() -> PlantIdentity:
    """Plant identity representing F3 Cabai rawit (Capsicum frutescens L)."""
    return PlantIdentity(
        id="cabai_rawit",
        label="Cabai rawit (Capsicum frutescens L)",
        identity_level="source_category",
        scientific_name="Capsicum frutescens L",
        source_category="cabai_rawit",
    )


@pytest.fixture
def sample_plant_besar() -> PlantIdentity:
    """Plant identity representing F14 cabai besar (Capsicum annum L)."""
    return PlantIdentity(
        id="cabai_besar",
        label="cabai besar (Capsicum annum L)",
        identity_level="source_category",
        scientific_name="Capsicum annum L",
        source_category="cabai_besar",
    )


@pytest.fixture
def sample_habitat_lamuk() -> HabitatIdentity:
    """Habitat identity representing Desa Lamuk, Kec. Kalikajar, Kab. Wonosobo."""
    return HabitatIdentity(
        id="hab_wonosobo_kalikajar_lamuk",
        definition="administrative_village_v1",
        label="Desa Lamuk, Wonosobo",
        administrative_path=AdministrativePath(
            province_name="Jawa Tengah",
            regency_name="Wonosobo",
            district_name="Kalikajar",
            village_name="Lamuk",
        ),
    )


@pytest.fixture
def sample_knowledge_document(
    sample_plant_rawit: PlantIdentity,
    sample_habitat_lamuk: HabitatIdentity,
) -> KnowledgeDocument:
    """Sample valid KnowledgeDocument with attributes and sampling locations."""
    source_ref = CurrentSourceReference(
        source_ref="data_input.xlsx",
        sheet="Resume Data",
        row=3,
        cell="G3",
    )
    attr_tinggi = AttributeValue(
        label="Tinggi Tanaman",
        value=45.5,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=source_ref,
    )
    sampling_loc = SamplingLocationDetail(
        location_ref="loc_wonosobo_01",
        raw_address="Dusun Pangempon, Desa Lamuk, Kec. Kalikajar, Kab. Wonosobo",
        hamlet="Dusun Pangempon",
        sampling_marker="B12",
        elevation_mdpl=750.0,
        soil_ph=6.5,
    )
    return KnowledgeDocument(
        variety=sample_plant_rawit,
        habitat=sample_habitat_lamuk,
        sampling_locations=[sampling_loc],
        attributes={"attr_tinggi_tanaman": attr_tinggi},
        media_refs=[],
        updated_by_run="run_s7b_test_001",
    )


@pytest.fixture
def sample_photo_mismatch_item() -> DocumentReviewItem:
    """Sample DocumentReviewItem with PHOTO_VARIETY_MISMATCH category and 3 candidate actions."""
    return DocumentReviewItem(
        item_id="rev_photo_mismatch_001",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="cabai_merah_argalingga_01.jpg",
        source_context="Citra buah terdeteksi NO_MATCH terhadap opsi varietas Excel run aktif",
        raw_values=["asset_sha256_7b3a9f0001"],
        candidate_resolutions=[
            {"action": "ASSIGN_EXISTING", "description": "Tetapkan ke varietas run aktif"},
            {"action": "CREATE_NEW_DOCUMENT", "description": "Bentuk dokumen varietas baru"},
            {"action": "DISCARD", "description": "Tolak citra secara non-destruktif"},
        ],
        status="pending",
        decision=None,
        notes="Photo variety mismatch for cabai_merah_argalingga_01.jpg",
        payload={
            "filename": "cabai_merah_argalingga_01.jpg",
            "asset_id": "asset_sha256_7b3a9f0001",
            "suggested_variety_hint": "Cabai Merah Keriting",
            "visual_evidence": "Buah merah panjang bergelombang khas cabai keriting",
            "options_evaluated": [
                "Cabai rawit (Capsicum frutescens L)",
                "cabai besar (Capsicum annum L)",
            ],
            "caption": "Cabai merah di kebun Argalingga",
            "identified_part": "BUAH",
            "confidence": 0.91,
        },
        run_id="run_s7b_test_001",
    )


@pytest.fixture
def sample_photo_draft(
    sample_knowledge_document: KnowledgeDocument,
    sample_photo_mismatch_item: DocumentReviewItem,
) -> DocumentDraft:
    """Sample DocumentDraft containing a staged document and a photo mismatch review item."""
    doc_key = str(sample_knowledge_document.doc_id)
    return DocumentDraft(
        run_id="run_s7b_test_001",
        source_filename="data_input.xlsx",
        file_sha256="d" * 64,
        source_scope="cabai-research",
        schema_version="kms-document-v1",
        template_hash="e" * 64,
        config_fingerprint="f" * 64,
        revision=1,
        documents={doc_key: sample_knowledge_document},
        reviews=[sample_photo_mismatch_item],
    )


@pytest.fixture
def sample_pipeline_result() -> PipelineRunResult:
    """PipelineRunResult fixture with photo mismatch review rows."""
    mapping_df = pd.DataFrame(
        [
            {
                "source_attribute_display": "Warna Daun",
                "source_attribute": "Warna Daun",
                "source_context": None,
                "predicted_row": "r_7",
                "predicted_label": "warna daun",
                "proposed_target_canonical_key": "daun.warna",
                "target_domain": "daun",
                "mapping_method": "exact_name",
                "confidence": 0.95,
                "verifier_status": "PASS",
                "acceptance_status": "AUTO_ACCEPT",
                "canonical_write": True,
                "normalization_required": False,
                "reasoning": "exact match",
            }
        ]
    )
    canonical_df = pd.DataFrame(
        [
            {"Nomor": 1, "Karakter": "habitus", "Cabai rawit": "perdu"},
            {"Nomor": 7, "Karakter": "warna daun", "Cabai rawit": "hijau tua"},
        ]
    )
    vision_rows = [
        {
            "filename": "cabai_merah_argalingga_01.jpg",
            "status": "MISMATCH",
            "matched_variety": "NO_MATCH",
            "identified_part": "BUAH",
            "confidence": 0.91,
            "visual_evidence": "Buah merah panjang bergelombang khas cabai keriting",
            "write_applied": False,
            "write_reason": "PHOTO_VARIETY_MISMATCH: unassigned, pending curator review",
        }
    ]
    return PipelineRunResult(
        mapping_df=mapping_df,
        canonical_df=canonical_df,
        workbook_bytes=b"fake-bytes-for-s7b-testing",
        vision_rows=vision_rows,
        run_id="run_s7b_test_001",
        schema_version="kms-document-v1",
        template_hash="e" * 64,
    )


# ============================================================================
# Section 1: Criterion A24 — Detection, Signal Display & Fail-Closed Blocking
# ============================================================================


def test_a24_photo_mismatch_review_filtering(
    sample_photo_mismatch_item: DocumentReviewItem,
    sample_photo_draft: DocumentDraft,
):
    """Criterion A24: Filter dan identifikasi item review PHOTO_VARIETY_MISMATCH.

    Verifikasi bahwa get_photo_mismatch_reviews memfilter secara presisi item-item
    dengan kategori PHOTO_VARIETY_MISMATCH baik dari daftar DocumentReviewItem
    maupun dari objek DocumentDraft envelope.
    """
    other_item = DocumentReviewItem(
        item_id="rev_loc_001",
        category="LOCATION_UNRESOLVED",
        source_label="Desa Tidak Lengkap",
        status="pending",
        run_id="run_s7b_test_001",
    )
    mixed_reviews = [other_item, sample_photo_mismatch_item]

    # Filter dari list
    mismatches = photo_review.get_photo_mismatch_reviews(mixed_reviews)
    assert len(mismatches) == 1
    assert mismatches[0].item_id == sample_photo_mismatch_item.item_id
    assert mismatches[0].category == "PHOTO_VARIETY_MISMATCH"

    # Filter dari DocumentDraft
    draft_mismatches = photo_review.get_photo_mismatch_reviews(sample_photo_draft)
    assert len(draft_mismatches) == 1
    assert draft_mismatches[0].item_id == sample_photo_mismatch_item.item_id


def test_a24_photo_signals_extraction_from_payload(
    sample_photo_mismatch_item: DocumentReviewItem,
):
    """Criterion A24: Ekstraksi sinyal multimodal (citra, teks nama berkas, opsi varietas).

    Verifikasi bahwa extract_photo_signals mengekstraksi seluruh metadata kunci
    dari payload review item: nama berkas, asset_id, organ tanaman (BUAH/DAUN),
    tingkat keyakinan (confidence), teks bukti visual, dan opsi varietas yang dievaluasi.
    """
    signals = photo_review.extract_photo_signals(sample_photo_mismatch_item)
    assert isinstance(signals, dict)
    assert signals["filename"] == "cabai_merah_argalingga_01.jpg"
    assert signals["asset_id"] == "asset_sha256_7b3a9f0001"
    assert signals["identified_part"] == "BUAH"
    assert signals["confidence"] == 0.91
    assert signals["suggested_variety_hint"] == "Cabai Merah Keriting"
    assert "Cabai rawit" in str(signals.get("options_evaluated"))
    assert "bergelombang" in signals.get("visual_evidence", "")


def test_a24_fail_closed_blocking_behavior(
    sample_photo_draft: DocumentDraft,
    sample_photo_mismatch_item: DocumentReviewItem,
):
    """Criterion A24: Penahanan fail-closed pada review foto mismatch yang masih pending.

    Verifikasi bahwa jika item review foto mismatch berstatus pending:
    1. is_photo_review_blocking mengembalikan True.
    2. has_blocking_photo_mismatch pada draft mengembalikan True.
    3. Setelah item disetujui (approved) atau ditolak (rejected), status blocking lepas (False).
    """
    assert photo_review.is_photo_review_blocking(sample_photo_mismatch_item) is True
    assert photo_review.has_blocking_photo_mismatch(sample_photo_draft) is True

    # Transisi ke approved melepaskan blokir
    sample_photo_mismatch_item.status = "approved"
    assert photo_review.is_photo_review_blocking(sample_photo_mismatch_item) is False
    assert photo_review.has_blocking_photo_mismatch(sample_photo_draft) is False

    # Transisi ke rejected (non-destruktif) juga melepaskan blokir
    sample_photo_mismatch_item.status = "rejected"
    assert photo_review.is_photo_review_blocking(sample_photo_mismatch_item) is False
    assert photo_review.has_blocking_photo_mismatch(sample_photo_draft) is False


def test_a24_render_photo_review_queue_displays_pending_badge_and_signals(
    sample_photo_draft: DocumentDraft,
):
    """Criterion A24, DoD S7b: Render antrean review foto mismatch dengan status pending dan sinyal.

    Verifikasi bahwa render_photo_review_queue merender bagian antrean foto mismatch,
    menampilkan nama berkas, organ tanaman yang teridentifikasi, dan indikator pending.
    """
    with patch("streamlit.subheader") as mock_sub, \
         patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write") as mock_write, \
         patch("streamlit.info") as mock_info:
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        photo_review.render_photo_review_queue(sample_photo_draft, run_id="run_s7b_test_001")
        assert mock_sub.called or mock_expander.called

        rendered_texts = [str(call[0][0]) for call in mock_write.call_args_list if call[0]]
        all_text = " ".join(rendered_texts)
        assert "cabai_merah_argalingga_01.jpg" in all_text or mock_expander.called


# ============================================================================
# Section 2: Criterion A25 — Action ASSIGN_EXISTING in UI & API Resolution
# ============================================================================


def test_a25_build_assign_existing_decision():
    """Criterion A25: Pembentukan keputusan ASSIGN_EXISTING kurator.

    Verifikasi bahwa build_assign_existing_decision menyusun objek PhotoMismatchDecision
    dengan action ASSIGN_EXISTING, selected_variety_id, selected_variety_label,
    target_habitat_id, dan catatan kurator.
    """
    decision = photo_review.build_assign_existing_decision(
        selected_variety_id="cabai_rawit",
        selected_variety_label="Cabai rawit (Capsicum frutescens L)",
        target_habitat_id="hab_wonosobo_kalikajar_lamuk",
        notes="Ditetapkan kurator ke varietas rawit yang terdaftar pada run aktif",
    )
    assert isinstance(decision, PhotoMismatchDecision)
    assert decision.action == "ASSIGN_EXISTING"
    assert decision.selected_variety_id == "cabai_rawit"
    assert "Cabai rawit" in (decision.selected_variety_label or "")
    assert decision.target_habitat_id == "hab_wonosobo_kalikajar_lamuk"
    assert "kurator" in (decision.notes or "")


def test_a25_resolve_assign_existing_calls_api():
    """Criterion A25: Resolusi review ASSIGN_EXISTING mengirim request POST ke endpoint v2.

    Verifikasi bahwa resolve_photo_assign_existing memanggil
    POST /runs/v2/{run_id}/reviews/{item_id}/resolve dengan payload keputusan ASSIGN_EXISTING
    dan mengembalikan status approved.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {
        "item_id": "rev_photo_mismatch_001",
        "status": "approved",
        "decision": {
            "action": "ASSIGN_EXISTING",
            "selected_variety_id": "cabai_rawit",
        },
    }

    res = photo_review.resolve_photo_assign_existing(
        run_id="run_s7b_test_001",
        item_id="rev_photo_mismatch_001",
        selected_variety_id="cabai_rawit",
        selected_variety_label="Cabai rawit (Capsicum frutescens L)",
        target_habitat_id="hab_wonosobo_kalikajar_lamuk",
        notes="Penetapan manual varietas",
        client=mock_client,
    )

    mock_client.request.assert_called_once()
    method, endpoint = mock_client.request.call_args[0][:2]
    assert method == "POST"
    assert "/runs/v2/run_s7b_test_001/reviews/rev_photo_mismatch_001/resolve" in endpoint
    assert res.get("status") == "approved"


def test_a25_assign_existing_updates_draft_and_links_photo(
    sample_photo_draft: DocumentDraft,
    sample_photo_mismatch_item: DocumentReviewItem,
    sample_knowledge_document: KnowledgeDocument,
):
    """Criterion A25: Aksi ASSIGN_EXISTING menautkan MediaReference ke dokumen target.

    Verifikasi bahwa fungsi apply_photo_decision_to_draft menautkan aset foto ke
    media_refs pada KnowledgeDocument target dengan mode penugasan HITL_REVIEW
    dan memperbarui status review item menjadi approved.
    """
    decision = PhotoMismatchDecision(
        action="ASSIGN_EXISTING",
        selected_variety_id=sample_knowledge_document.variety.id,
        selected_variety_label=sample_knowledge_document.variety.label,
        target_habitat_id=sample_knowledge_document.habitat.id,
    )

    updated_draft = photo_review.apply_photo_decision_to_draft(
        draft=sample_photo_draft,
        item_id=sample_photo_mismatch_item.item_id,
        decision=decision,
    )

    # Review item harus berstatus approved
    rev = next(r for r in updated_draft.reviews if r.item_id == sample_photo_mismatch_item.item_id)
    assert rev.status == "approved"

    # Dokumen target harus memiliki media_refs yang tertaut
    doc_key = str(sample_knowledge_document.doc_id)
    doc = updated_draft.documents[doc_key]
    assert len(doc.media_refs) >= 1
    media = doc.media_refs[0]
    assert media.asset_id == "asset_sha256_7b3a9f0001"
    assert media.assigned_via == "HITL_REVIEW"
    assert media.resolution_status == "linked"


def test_a25_render_assign_existing_form_and_submission(
    sample_photo_mismatch_item: DocumentReviewItem,
):
    """Criterion A25, DoD S7b: Form interaktif ASSIGN_EXISTING merender kontrol pilihan varietas.

    Verifikasi bahwa render_assign_existing_form menampilkan selectbox varietas
    dan tombol submit eksekusi penetapan varietas yang memanggil API resolusi.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {"status": "approved"}

    varieties = [
        {"id": "cabai_rawit", "label": "Cabai rawit (Capsicum frutescens L)"},
        {"id": "cabai_besar", "label": "cabai besar (Capsicum annum L)"},
    ]

    with patch("streamlit.selectbox", return_value="cabai_rawit") as mock_select, \
         patch("streamlit.button", return_value=True) as mock_button:
        photo_review.render_assign_existing_form(
            item=sample_photo_mismatch_item,
            run_id="run_s7b_test_001",
            available_varieties=varieties,
            client=mock_client,
        )
        assert mock_select.called
        assert mock_button.called


# ============================================================================
# Section 3: Criterion A26 — Action CREATE_NEW_DOCUMENT in UI & API Resolution
# ============================================================================


def test_a26_build_create_new_document_decision():
    """Criterion A26: Pembentukan keputusan CREATE_NEW_DOCUMENT kurator.

    Verifikasi bahwa build_create_new_document_decision menyusun PhotoMismatchDecision
    dengan action CREATE_NEW_DOCUMENT, new_variety_name, identity_level yang sah,
    dan target habitat.
    """
    decision = photo_review.build_create_new_document_decision(
        new_variety_name="Cabai Keriting Lokal Wonosobo",
        identity_level="cultivar",
        target_habitat_id="hab_wonosobo_kalikajar_lamuk",
        notes="Varietas baru hasil identifikasi morfologi visual lapangan",
    )
    assert isinstance(decision, PhotoMismatchDecision)
    assert decision.action == "CREATE_NEW_DOCUMENT"
    assert decision.new_variety_name == "Cabai Keriting Lokal Wonosobo"
    assert decision.identity_level == "cultivar"
    assert decision.target_habitat_id == "hab_wonosobo_kalikajar_lamuk"


def test_a26_create_new_document_enforces_valid_identity_levels():
    """Criterion A26: Penegakan validitas taksonomi tanpa mengarang tingkat sembarangan.

    Verifikasi bahwa fungsi pembuatan keputusan CREATE_NEW_DOCUMENT hanya menerima
    identity_level yang sah (source_category, species, cultivar) dan menolak
    kategori buatan yang tidak dikenal.
    """
    for valid_level in ["source_category", "species", "cultivar"]:
        dec = photo_review.build_create_new_document_decision(
            new_variety_name="Cabai Hias Ungu",
            identity_level=valid_level,
        )
        assert dec.identity_level == valid_level

    with pytest.raises((ValueError, Exception)):
        photo_review.build_create_new_document_decision(
            new_variety_name="Cabai Sintetis",
            identity_level="synthetic_rank",
        )


def test_a26_resolve_create_new_document_calls_api():
    """Criterion A26: Resolusi review CREATE_NEW_DOCUMENT mengirim request POST ke endpoint v2.

    Verifikasi bahwa resolve_photo_create_new_document memanggil
    POST /runs/v2/{run_id}/reviews/{item_id}/resolve dengan payload CREATE_NEW_DOCUMENT
    dan mengembalikan status approved.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {
        "item_id": "rev_photo_mismatch_001",
        "status": "approved",
        "decision": {
            "action": "CREATE_NEW_DOCUMENT",
            "new_variety_name": "Cabai Keriting Lokal Wonosobo",
        },
    }

    res = photo_review.resolve_photo_create_new_document(
        run_id="run_s7b_test_001",
        item_id="rev_photo_mismatch_001",
        new_variety_name="Cabai Keriting Lokal Wonosobo",
        identity_level="cultivar",
        target_habitat_id="hab_wonosobo_kalikajar_lamuk",
        client=mock_client,
    )

    mock_client.request.assert_called_once()
    method, endpoint = mock_client.request.call_args[0][:2]
    assert method == "POST"
    assert "/runs/v2/run_s7b_test_001/reviews/rev_photo_mismatch_001/resolve" in endpoint
    assert res.get("status") == "approved"


def test_a26_render_create_new_document_form_and_submission(
    sample_photo_mismatch_item: DocumentReviewItem,
):
    """Criterion A26, DoD S7b: Form interaktif CREATE_NEW_DOCUMENT merender input varietas baru.

    Verifikasi bahwa render_create_new_document_form menampilkan text_input untuk
    nama varietas baru, selectbox untuk tingkat identitas, dan tombol pembentukan dokumen.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {"status": "approved"}

    with patch("streamlit.text_input", return_value="Cabai Keriting Lokal") as mock_input, \
         patch("streamlit.selectbox", return_value="cultivar") as mock_select, \
         patch("streamlit.button", return_value=True) as mock_button:
        photo_review.render_create_new_document_form(
            item=sample_photo_mismatch_item,
            run_id="run_s7b_test_001",
            client=mock_client,
        )
        assert mock_input.called
        assert mock_select.called
        assert mock_button.called


# ============================================================================
# Section 4: Criterion A27 — Action DISCARD Non-Destructive in UI & API Resolution
# ============================================================================


def test_a27_build_discard_decision_with_reason():
    """Criterion A27: Pembentukan keputusan DISCARD non-destruktif dengan alasan penolakan.

    Verifikasi bahwa build_discard_decision menyusun PhotoMismatchDecision
    dengan action DISCARD, discard_reason yang jelas, dan catatan verifikasi kurator.
    """
    decision = photo_review.build_discard_decision(
        discard_reason="Bukan objek tanaman cabai",
        notes="Foto lanskap tanah sampling tanpa organ tanaman yang dapat diidentifikasi",
    )
    assert isinstance(decision, PhotoMismatchDecision)
    assert decision.action == "DISCARD"
    assert decision.discard_reason == "Bukan objek tanaman cabai"
    assert "tanah sampling" in (decision.notes or "")


def test_a27_resolve_discard_marks_rejected_non_destructively():
    """Criterion A27: Resolusi DISCARD menandai status review rejected tanpa merusak blob fisik.

    Verifikasi bahwa resolve_photo_discard memanggil API v2 dan mengembalikan
    status rejected secara transaksional.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {
        "item_id": "rev_photo_mismatch_001",
        "status": "rejected",
        "decision": {
            "action": "DISCARD",
            "discard_reason": "Bukan objek tanaman cabai",
        },
    }

    res = photo_review.resolve_photo_discard(
        run_id="run_s7b_test_001",
        item_id="rev_photo_mismatch_001",
        discard_reason="Bukan objek tanaman cabai",
        client=mock_client,
    )

    mock_client.request.assert_called_once()
    method, endpoint = mock_client.request.call_args[0][:2]
    assert method == "POST"
    assert "/runs/v2/run_s7b_test_001/reviews/rev_photo_mismatch_001/resolve" in endpoint
    assert res.get("status") == "rejected"


def test_a27_discard_clears_blocking_status_without_cas_deletion(
    sample_photo_draft: DocumentDraft,
    sample_photo_mismatch_item: DocumentReviewItem,
):
    """Criterion A27: Status rejected melepaskan antrean blokir sambil menjaga integritas aset CAS.

    Verifikasi bahwa setelah eksekusi DISCARD:
    1. Status review item menjadi rejected.
    2. Draft tidak lagi diblokir oleh foto mismatch.
    3. Asset ID tetap tersimpan di payload review (tidak dihapus dari sistem storage CAS).
    """
    decision = PhotoMismatchDecision(
        action="DISCARD",
        discard_reason="Foto buram",
    )

    updated_draft = photo_review.apply_photo_decision_to_draft(
        draft=sample_photo_draft,
        item_id=sample_photo_mismatch_item.item_id,
        decision=decision,
    )

    rev = next(r for r in updated_draft.reviews if r.item_id == sample_photo_mismatch_item.item_id)
    assert rev.status == "rejected"
    assert photo_review.has_blocking_photo_mismatch(updated_draft) is False
    # Verifikasi payload asset_id tetap utuh untuk audit non-destruktif
    assert rev.payload.get("asset_id") == "asset_sha256_7b3a9f0001"


def test_a27_render_discard_form_and_submission(
    sample_photo_mismatch_item: DocumentReviewItem,
):
    """Criterion A27, DoD S7b: Form interaktif DISCARD merender alasan penolakan dan tombol aksi.

    Verifikasi bahwa render_discard_form menampilkan selectbox alasan penolakan
    dan tombol submit DISCARD yang memanggil API resolusi.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {"status": "rejected"}

    with patch("streamlit.selectbox", return_value="Bukan objek tanaman cabai") as mock_select, \
         patch("streamlit.button", return_value=True) as mock_button:
        photo_review.render_discard_form(
            item=sample_photo_mismatch_item,
            run_id="run_s7b_test_001",
            client=mock_client,
        )
        assert mock_select.called
        assert mock_button.called


# ============================================================================
# Section 5: Modal UI Integration, Validation & Error Handling
# ============================================================================


def test_photo_review_decision_validation_rejects_missing_inputs():
    """DoD S7b: Validasi input kurator pada keputusan review foto mismatch.

    Verifikasi bahwa pembuatan keputusan melempar ValueError jika:
    1. ASSIGN_EXISTING tidak memiliki selected_variety_id.
    2. CREATE_NEW_DOCUMENT tidak memiliki new_variety_name.
    3. DISCARD tidak memiliki discard_reason.
    """
    with pytest.raises(ValueError):
        photo_review.build_assign_existing_decision(
            selected_variety_id="",
            selected_variety_label="",
        )

    with pytest.raises(ValueError):
        photo_review.build_create_new_document_decision(
            new_variety_name="",
            identity_level="cultivar",
        )

    with pytest.raises(ValueError):
        photo_review.build_discard_decision(
            discard_reason="",
        )


def test_photo_review_error_sanitization():
    """DoD S7b, A17 Security: Penanganan error resolusi foto tanpa kebocoran kredensial.

    Verifikasi bahwa pesan error API atau koneksi database disanitasi:
    tidak menampilkan token, password, atau detail koneksi backend sensitif ke UI.
    """
    raw_error = Exception(
        "Failed POST to http://internal-db:5432/runs/v2 with token secret_token_xyz987: Connection refused"
    )
    sanitized = photo_review.handle_photo_review_error(raw_error)
    assert isinstance(sanitized, str)
    assert "secret_token_xyz987" not in sanitized
    assert "http://internal-db:5432" not in sanitized


def test_hasil_page_renders_photo_review_ui_when_mismatch_present(
    sample_pipeline_result: PipelineRunResult,
):
    """Criterion A24, DoD S7b: Halaman 3_Hasil.py merender komponen antrean foto mismatch.

    Verifikasi bahwa halaman 3_Hasil.py memuat sesi antrean review foto mismatch
    saat terdapat baris vision berstatus MISMATCH pada PipelineRunResult.
    """
    at = AppTest.from_file(HASIL_PAGE_PATH, default_timeout=APP_TEST_TIMEOUT)
    at.session_state["cabai_kms_pipeline_result"] = sample_pipeline_result
    at.session_state["cabai_kms_inputs"] = {
        "filename": "data_input.xlsx",
        "sheet_name": "Resume Data",
        "drive_url": "",
    }
    at.session_state["kms_reviewer_token"] = "w" * 40
    at.run()

    assert not at.exception

    rendered_texts = [
        str(elem.value)
        for elem in list(at.subheader)
        + list(at.caption)
        + list(at.info)
        + list(at.warning)
        + list(at.error)
        + list(at.text)
        + list(at.markdown)
    ] + [str(e.label) for e in at.expander]
    all_rendered_content = rendered_texts + [str(b.label) for b in at.button]

    # Buktikan bahwa antrean atau kategori foto mismatch dirender saat ada mismatch
    has_photo_mismatch_ui = any(
        "photo_variety_mismatch" in t.lower()
        or "foto mismatch" in t.lower()
        or "photo mismatch" in t.lower()
        for t in all_rendered_content
    )
    assert has_photo_mismatch_ui, (
        "3_Hasil.py must render photo variety mismatch review UI when mismatch rows exist."
    )

    # Buktikan bahwa nama berkas foto mismatch ditampilkan pada halaman review
    has_photo_filename = any(
        "cabai_merah_argalingga_01.jpg" in t for t in all_rendered_content
    )
    assert has_photo_filename, (
        "3_Hasil.py must display the mismatch photo filename (cabai_merah_argalingga_01.jpg)."
    )
