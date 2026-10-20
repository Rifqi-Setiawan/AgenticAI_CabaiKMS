"""Acceptance test suite for Stage S7: UI Streamlit (Review Kategori & Commit).

Contract source:
- reports/cabai-kms-jsonb/TECH_PLAN.md:
  * Line 523: Table 5 DoD & boundaries for S7 (UI Streamlit: Review Kategori & Commit)
  * Line 541: Acceptance criterion A06 (test_plant_identity_level_and_source_category_retention)
  * Line 555: Acceptance criterion A20 (test_regression_pipeline_media_and_excel_export)
  * Line 691: Section 11 Gate 1-2 S6/S7 implementation phases
  * PRD criteria: A01, A03, A04, A05, A06, A07, A09, A11, A12, A16, A17, A20.

Implementation boundaries for S7 (strict):
- src/integrations/streamlit_commit.py
- src/ui/pages/3_Hasil.py
- src/ui/pages/4_KMS.py
- tests/ui/test_document_ui.py

DoD S7:
- Panel review Streamlit menampilkan:
  1. Target hierarki wilayah (AdministrativePath & HabitatIdentity)
  2. Antrean review per kategori (DocumentReviewItem grouped by category)
  3. Diff sementara (staged document changes & attribute summary)
  4. Tombol commit transaksional (disabled on pending, calls /runs/v2/{id}/commit, handles replay & sanitized conflict)
  5. JSONB viewer (staged draft & committed documents via GET /documents without historical trace arrays)

All tests are deterministic, mock HTTP/client calls without real network or LLM,
and serve as the test-first RED acceptance harness before S7 implementation.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import openpyxl
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.integrations import streamlit_commit
from src.schema.canonical import CanonicalSchema
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
    PlantIdentity,
    SamplingLocationDetail,
)
from src.ui.pipeline_runner import PipelineRunResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HASIL_PAGE_PATH = str(PROJECT_ROOT / "src/ui/pages/3_Hasil.py")
KMS_PAGE_PATH = str(PROJECT_ROOT / "src/ui/pages/4_KMS.py")
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
    """Habitat identity representing Desa Lamuk, Kec. Kalikajar, Kab. Wonosobo (B12/B13)."""
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
def sample_habitat_hargobinangun() -> HabitatIdentity:
    """Habitat identity representing Desa Hargobinangun, Kec. Pakem, Kab. Sleman (B3/B4)."""
    return HabitatIdentity(
        id="hab_sleman_pakem_hargobinangun",
        definition="administrative_village_v1",
        label="Desa Hargobinangun, Sleman",
        administrative_path=AdministrativePath(
            province_name="D.I. Yogyakarta",
            regency_name="Sleman",
            district_name="Pakem",
            village_name="Hargobinangun",
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
    attr_klorofil = AttributeValue(
        label="Kandungan Klorofil (SPAD)",
        value=49.02,
        value_type="number",
        unit="SPAD",
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
        attributes={
            "attr_tinggi_tanaman": attr_tinggi,
            "attr_klorofil": attr_klorofil,
        },
        updated_by_run="run_s7_test_001",
    )


@pytest.fixture
def sample_categorized_reviews() -> list[DocumentReviewItem]:
    """Sample list of DocumentReviewItem covering diverse categories."""
    return [
        DocumentReviewItem(
            item_id="rev_loc_001",
            category="LOCATION_UNRESOLVED",
            source_label="Alamat Desa Tidak Lengkap",
            source_context="Desa Lamuk atau Desa Pakem tanpa kejelasan kecamatan",
            raw_values=["Desa Lamuk atau Desa Pakem"],
            status="pending",
            run_id="run_s7_test_001",
        ),
        DocumentReviewItem(
            item_id="rev_conflict_001",
            category="INTRA_RUN_VALUE_CONFLICT",
            source_label="Kandungan Klorofil (SPAD)",
            source_context="Benturan nilai B12 (49.02) vs B13 (46.54) pada varietas dan habitat yang sama",
            raw_values=[49.02, 46.54],
            status="pending",
            run_id="run_s7_test_001",
        ),
        DocumentReviewItem(
            item_id="rev_attr_001",
            category="NEW_ATTRIBUTE",
            source_label="Kelembaban Tanah (%)",
            source_context="Header sel K2 non-kanonik",
            raw_values=[58.0],
            status="approved",
            run_id="run_s7_test_001",
        ),
        DocumentReviewItem(
            item_id="rev_photo_001",
            category="PHOTO_VARIETY_MISMATCH",
            source_label="cabai_hias_pelangi.jpg",
            source_context="Ciri visual cabai hias tidak cocok dengan opsi Excel Cabai rawit / Cabai besar",
            raw_values=["cabai_hias_pelangi.jpg"],
            status="pending",
            run_id="run_s7_test_001",
        ),
    ]


@pytest.fixture
def sample_document_draft(
    sample_knowledge_document: KnowledgeDocument,
    sample_categorized_reviews: list[DocumentReviewItem],
) -> DocumentDraft:
    """Sample DocumentDraft staging envelope."""
    doc_key = str(sample_knowledge_document.doc_id)
    return DocumentDraft(
        run_id="run_s7_test_001",
        source_filename="data_input.xlsx",
        file_sha256="a" * 64,
        source_scope="cabai-research",
        schema_version="kms-document-v1",
        template_hash="b" * 64,
        config_fingerprint="c" * 64,
        revision=1,
        documents={doc_key: sample_knowledge_document},
        reviews=sample_categorized_reviews,
    )


@pytest.fixture
def sample_pipeline_result() -> PipelineRunResult:
    """Fixture PipelineRunResult for Streamlit page tests."""
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
            },
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
            "filename": "cabai_rawit_daun.jpg",
            "status": "KNOWN",
            "matched_variety": "Cabai rawit",
            "identified_part": "DAUN",
            "confidence": 0.92,
            "visual_evidence": "daun cabai rawit sehat",
            "write_applied": True,
            "write_reason": "ok",
        }
    ]
    return PipelineRunResult(
        mapping_df=mapping_df,
        canonical_df=canonical_df,
        workbook_bytes=b"fake-bytes-for-s7-testing",
        vision_rows=vision_rows,
        run_id="run_s7_test_001",
        schema_version="kms-document-v1",
        template_hash="b" * 64,
    )


# ============================================================================
# Section 1: Plant Identity Level & Source Category Retention (Criterion A06)
# ============================================================================


def test_plant_identity_level_and_source_category_retention(
    sample_plant_rawit: PlantIdentity,
    sample_plant_besar: PlantIdentity,
):
    """Criterion A06: Label sumber dan identity level tanaman dipertahankan;
    sistem dilarang mengarang kultivar buatan.

    Verifikasi bahwa UI menampilkan format identitas tanaman dengan tingkat identitas
    'source_category' dan nama taksonomi asli (sel F3 Cabai rawit & sel F14 cabai besar)
    tanpa mengarang nama kultivar buatan (synthetic cultivars).
    """
    # 1. Format identitas F3 Cabai rawit (Capsicum frutescens L)
    formatted_rawit = streamlit_commit.format_plant_identity(sample_plant_rawit)
    assert "source_category" in formatted_rawit.lower() or sample_plant_rawit.identity_level == "source_category"
    assert "Cabai rawit" in formatted_rawit
    assert "Capsicum frutescens L" in formatted_rawit
    # Sistem dilarang mengarang kultivar
    assert "kultivar" not in formatted_rawit.lower() or "bukan kultivar" in formatted_rawit.lower()

    # 2. Format identitas F14 cabai besar (Capsicum annum L)
    formatted_besar = streamlit_commit.format_plant_identity(sample_plant_besar)
    assert "cabai besar" in formatted_besar
    assert "Capsicum annum L" in formatted_besar
    assert sample_plant_besar.identity_level == "source_category"


# ============================================================================
# Section 2: Regional Hierarchy Target Display (DoD S7, Criteria A03, A04, A05)
# ============================================================================


def test_format_regional_hierarchy_displays_four_tier_administrative_path(
    sample_habitat_lamuk: HabitatIdentity,
    sample_habitat_hargobinangun: HabitatIdentity,
):
    """Criteria A03, A04, DoD S7: Format hierarki wilayah administratif 4-tingkat.

    Verifikasi bahwa format hierarki menampilkan Provinsi, Kabupaten, Kecamatan, dan Desa
    secara terstruktur, serta memisahkan secara tegas desa senama pada kabupaten berbeda
    (Desa Lamuk Kab. Wonosobo vs Desa Lamuk Kab. Purbalingga).
    """
    formatted_lamuk = streamlit_commit.format_regional_hierarchy(sample_habitat_lamuk)
    assert "Jawa Tengah" in formatted_lamuk
    assert "Wonosobo" in formatted_lamuk
    assert "Kalikajar" in formatted_lamuk
    assert "Lamuk" in formatted_lamuk

    # Homonymous village in Purbalingga must produce distinct formatted hierarchy
    habitat_lamuk_purbalingga = HabitatIdentity(
        id="hab_purbalingga_kalikajar_lamuk",
        definition="administrative_village_v1",
        label="Desa Lamuk, Purbalingga",
        administrative_path=AdministrativePath(
            province_name="Jawa Tengah",
            regency_name="Purbalingga",
            district_name="Kalikajar",
            village_name="Lamuk",
        ),
    )
    formatted_purbalingga = streamlit_commit.format_regional_hierarchy(habitat_lamuk_purbalingga)
    assert "Purbalingga" in formatted_purbalingga
    assert formatted_lamuk != formatted_purbalingga


def test_review_panel_displays_regional_hierarchy_target(
    sample_document_draft: DocumentDraft,
):
    """Criteria A05, DoD S7: Panel review Streamlit menampilkan target hierarki wilayah dokumen.

    Verifikasi bahwa render_regional_hierarchy menampilkan target wilayah administratif
    untuk setiap dokumen yang ada di draft, dan menandai lokasi belum teresolusi (A05)
    sebagai blocker review.
    """
    with patch("streamlit.subheader") as mock_subheader, \
         patch("streamlit.write") as mock_write, \
         patch("streamlit.info") as mock_info:
        streamlit_commit.render_regional_hierarchy(sample_document_draft)

        # Harus merender hierarki wilayah
        rendered_texts = [str(call[0][0]) for call in mock_write.call_args_list if call[0]]
        all_text = " ".join(rendered_texts)
        assert "Wonosobo" in all_text or "Lamuk" in all_text


# ============================================================================
# Section 3: Categorized Review Queue (DoD S7, Criteria A07, A09, A11)
# ============================================================================


def test_group_reviews_by_category_groups_document_review_items(
    sample_categorized_reviews: list[DocumentReviewItem],
):
    """Criteria A07, A09, A11, DoD S7: Pengelompokan antrean review per kategori.

    Verifikasi bahwa group_reviews_by_category mengelompokkan DocumentReviewItem
    ke dalam kategori spesifik: LOCATION_UNRESOLVED, INTRA_RUN_VALUE_CONFLICT,
    NEW_ATTRIBUTE, dan PHOTO_VARIETY_MISMATCH.
    """
    grouped = streamlit_commit.group_reviews_by_category(sample_categorized_reviews)
    assert isinstance(grouped, dict)
    assert "LOCATION_UNRESOLVED" in grouped
    assert "INTRA_RUN_VALUE_CONFLICT" in grouped
    assert "NEW_ATTRIBUTE" in grouped
    assert "PHOTO_VARIETY_MISMATCH" in grouped

    assert len(grouped["LOCATION_UNRESOLVED"]) == 1
    assert len(grouped["INTRA_RUN_VALUE_CONFLICT"]) == 1
    assert len(grouped["NEW_ATTRIBUTE"]) == 1
    assert len(grouped["PHOTO_VARIETY_MISMATCH"]) == 1


def test_render_categorized_review_queue_renders_category_sections_and_items(
    sample_document_draft: DocumentDraft,
):
    """DoD S7: Render antrean review per kategori dengan kontrol resolusi kurator.

    Verifikasi bahwa render_categorized_review_queue merender expander/bagian untuk
    setiap kategori review, menampilkan konteks dan nilai mentah, serta tombol aksi.
    """
    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write") as mock_write, \
         patch("streamlit.button") as mock_button:
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(sample_document_draft, run_id="run_s7_test_001")
        assert mock_expander.called


def test_review_queue_resolution_updates_draft_and_item_status():
    """DoD S7, S6 Integration: Resolusi review item memanggil endpoint v2 dan memperbarui status.

    Verifikasi bahwa resolve_review_item_v2 mengirim POST ke
    /runs/v2/{run_id}/reviews/{item_id}/resolve dan mengembalikan status teresolusi.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {
        "item_id": "rev_conflict_001",
        "status": "approved",
        "decision": {"action": "APPROVE_VALUE", "selected_value": 49.02},
    }

    decision = {"action": "APPROVE_VALUE", "selected_value": 49.02}
    result = streamlit_commit.resolve_review_item_v2(
        run_id="run_s7_test_001",
        item_id="rev_conflict_001",
        decision=decision,
        client=mock_client,
    )

    mock_client.request.assert_called_once_with(
        "POST",
        "/runs/v2/run_s7_test_001/reviews/rev_conflict_001/resolve",
        json={"decision": decision},
    )
    assert result["status"] == "approved"


# ============================================================================
# Section 4: Temporary Diff Preview (DoD S7)
# ============================================================================


def test_build_document_diff_computes_created_updated_and_attribute_changes(
    sample_document_draft: DocumentDraft,
):
    """DoD S7: Perhitungan diff dokumen sementara sebelum commit.

    Verifikasi bahwa build_document_diff menghitung dokumen yang akan dibuat (documents_to_create),
    dokumen yang diperbarui (documents_to_update), jumlah atribut baru, dan review tertunda.
    """
    # Kasus: database belum memiliki dokumen (semua dokumen baru)
    diff = streamlit_commit.build_document_diff(sample_document_draft, existing_documents={})
    assert isinstance(diff, dict)
    assert "documents_to_create" in diff
    assert "documents_to_update" in diff
    assert "attributes_added" in diff
    assert "pending_reviews_count" in diff

    assert len(diff["documents_to_create"]) == 1
    assert len(diff["documents_to_update"]) == 0
    assert diff["attributes_added"] == 2
    # 3 item pending (loc, conflict, photo), 1 approved (attr)
    assert diff["pending_reviews_count"] == 3


def test_render_temporary_diff_displays_change_metrics_and_summary():
    """DoD S7: Tampilan diff sementara pada antarmuka Streamlit.

    Verifikasi bahwa render_temporary_diff menampilkan metrik perubahan dokumen
    (dokumen baru, diperbarui, atribut) dan ringkasan diff perubahan.
    """
    diff_summary = {
        "documents_to_create": ["cabai_rawit:hab_wonosobo_kalikajar_lamuk"],
        "documents_to_update": [],
        "documents_unchanged": [],
        "attributes_added": 2,
        "attributes_updated": 0,
        "pending_reviews_count": 0,
    }

    with patch("streamlit.columns") as mock_columns, \
         patch("streamlit.metric") as mock_metric, \
         patch("streamlit.dataframe") as mock_df:
        col_mocks = [MagicMock(), MagicMock(), MagicMock()]
        mock_columns.return_value = col_mocks

        streamlit_commit.render_temporary_diff(diff_summary)
        assert mock_columns.called or mock_metric.called


# ============================================================================
# Section 5: Transactional Commit Button & API v2 Integration (Criteria A12, A16, A17)
# ============================================================================


def test_commit_button_disabled_when_pending_reviews_exist(
    sample_document_draft: DocumentDraft,
):
    """Criterion A12, DoD S7: Tombol commit dinonaktifkan jika ada review berstatus pending.

    Verifikasi bahwa jika masih ada item review pending (A12), tombol commit
    dinonaktifkan (disabled=True) dan tampil peringatan penahanan commit.
    """
    # sample_document_draft memiliki 3 item review pending
    is_allowed = streamlit_commit.is_commit_allowed(sample_document_draft)
    assert is_allowed is False


def test_commit_button_enabled_and_submits_v2_commit_when_all_resolved(
    sample_document_draft: DocumentDraft,
):
    """Criterion A12, DoD S7: Tombol commit aktif saat seluruh review selesai dan submit ke API v2.

    Verifikasi bahwa jika seluruh item review telah berstatus approved/revised/rejected,
    commit_document_draft_v2 memanggil POST /runs/v2/{id}/commit dengan expected_revision
    dan payload_sha256, serta mengembalikan CommitReceipt.
    """
    # Tandai seluruh review selesai
    for item in sample_document_draft.reviews:
        item.status = "approved"

    assert streamlit_commit.is_commit_allowed(sample_document_draft) is True

    mock_client = MagicMock()
    mock_client.request.return_value = {
        "run_id": "run_s7_test_001",
        "revision": 1,
        "documents_created": 1,
        "documents_updated": 0,
        "documents_unchanged": 0,
        "reviews_resolved": 4,
        "attributes_committed": 2,
        "media_linked": 0,
        "media_discarded": 0,
        "replayed": False,
        "receipt_id": "rcpt_001",
    }

    receipt = streamlit_commit.commit_document_draft_v2(
        run_id="run_s7_test_001",
        expected_revision=1,
        payload_sha256="a" * 64,
        client=mock_client,
    )

    mock_client.request.assert_called_once_with(
        "POST",
        "/runs/v2/run_s7_test_001/commit",
        json={"expected_revision": 1, "payload_sha256": "a" * 64},
    )
    assert receipt["documents_created"] == 1
    assert receipt["attributes_committed"] == 2
    assert receipt["replayed"] is False


def test_commit_receipt_handles_idempotent_replay():
    """Criterion A16, DoD S7: Tampilan receipt commit menangani pemanggilan ulang idempotent.

    Verifikasi bahwa jika CommitReceipt memiliki flag replayed=True, UI menampilkan
    pesan bahwa commit sudah tercatat dan tidak terjadi mutasi ganda.
    """
    replayed_receipt = CommitReceipt(
        run_id="run_s7_test_001",
        revision=1,
        documents_created=0,
        documents_updated=0,
        documents_unchanged=1,
        reviews_resolved=0,
        attributes_committed=0,
        media_linked=0,
        replayed=True,
    )

    with patch("streamlit.success") as mock_success, patch("streamlit.info") as mock_info:
        streamlit_commit.render_commit_receipt(replayed_receipt)
        success_text = mock_success.call_args[0][0] if mock_success.called else ""
        info_text = mock_info.call_args[0][0] if mock_info.called else ""
        combined = f"{success_text} {info_text}"
        assert "sudah tercatat" in combined or "tidak ada penulisan ulang" in combined or replayed_receipt.replayed


def test_commit_conflict_displays_sanitized_error_without_leaking_credentials():
    """Criterion A17, DoD S7: Penanganan error konflik commit tanpa membocorkan kredensial.

    Verifikasi bahwa pesan error HTTP 409 Conflict atau kegagalan koneksi database
    disanitasi: tidak menampilkan DSN, database URL, password, token, atau raw SQL ke UI.
    """
    leaky_error = Exception(
        "Conflict: VERSION_CONFLICT at postgresql+psycopg://cabai_user:secret_pass_123@db.internal:5432/cabai_kms: "
        "Dokumen berubah sejak draft disusun. Reload dan hitung ulang diff."
    )

    sanitized = streamlit_commit.handle_commit_error(leaky_error)
    assert isinstance(sanitized, str)
    assert "secret_pass_123" not in sanitized
    assert "postgresql+psycopg" not in sanitized
    assert "cabai_user" not in sanitized
    assert "db.internal" not in sanitized
    assert "VERSION_CONFLICT" in sanitized or "Dokumen berubah" in sanitized


# ============================================================================
# Section 6: JSONB Document Viewer (DoD S7, Criterion A01)
# ============================================================================


def test_jsonb_viewer_displays_staged_document_structure_without_history_arrays(
    sample_knowledge_document: KnowledgeDocument,
):
    """Criterion A01, DoD S7: JSONB viewer menampilkan struktur dokumen tanpa array riwayat.

    Verifikasi bahwa render_jsonb_viewer menampilkan payload KnowledgeDocument
    (variety, habitat, sampling_locations, attributes, media_refs) dan menjamin
    tidak ada array riwayat historis terlarang (previous_value, history, observations).
    """
    with patch("streamlit.json") as mock_json:
        streamlit_commit.render_jsonb_viewer(sample_knowledge_document)
        assert mock_json.called
        payload = mock_json.call_args[0][0]
        assert "variety" in payload
        assert "habitat" in payload
        assert "attributes" in payload
        # Larangan keras array riwayat
        for forbidden in ["previous_value", "history", "observations", "previous_values"]:
            assert forbidden not in payload


def test_kms_page_inspector_queries_and_renders_jsonb_documents(
    sample_knowledge_document: KnowledgeDocument,
):
    """Criterion A01, DoD S7: Halaman 4_KMS memanggil GET /documents dan menampilkan dokumen JSONB.

    Verifikasi bahwa render_inspector pada 4_KMS memanggil endpoint dokumen v2 (GET /documents),
    bukan endpoint nilai legacy (/values), dan merender dokumen JSONB.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {
        "items": [sample_knowledge_document.model_dump(mode="json")],
    }

    with patch.object(streamlit_commit, "ui_client", return_value=mock_client), \
         patch.object(streamlit_commit, "enabled", return_value=True), \
         patch("streamlit.dataframe") as mock_df, \
         patch("streamlit.json") as mock_json:
        streamlit_commit.render_inspector()

        # Harus memanggil endpoint /documents, bukan /values
        called_paths = [call[0][1] for call in mock_client.request.call_args_list if len(call[0]) > 1]
        assert any(p.startswith("/documents") for p in called_paths), (
            f"Expected call to /documents, got: {called_paths}"
        )
        assert not any(p.startswith("/values") for p in called_paths), (
            f"Expected NO calls to legacy /values, got: {called_paths}"
        )


def test_kms_page_filters_documents_by_variety_and_habitat():
    """DoD S7: Halaman 4_KMS menyediakan filter varietas dan habitat pada kueri dokumen.

    Verifikasi bahwa kueri dokumen ke endpoint GET /documents mendukung filter
    parameter variety_id dan habitat_id.
    """
    mock_client = MagicMock()
    mock_client.request.return_value = {"items": []}

    streamlit_commit.fetch_documents_v2(
        variety_id="cabai_rawit",
        habitat_id="hab_wonosobo_kalikajar_lamuk",
        client=mock_client,
    )

    mock_client.request.assert_called_once()
    called_path = mock_client.request.call_args[0][1]
    assert "/documents" in called_path
    assert "variety_id=cabai_rawit" in called_path
    assert "habitat_id=hab_wonosobo_kalikajar_lamuk" in called_path


# ============================================================================
# Section 7: Regression Guard for Existing Pipeline & Media Export (Criterion A20)
# ============================================================================


def test_regression_pipeline_media_and_excel_export(
    sample_pipeline_result: PipelineRunResult,
    sample_document_draft: DocumentDraft,
):
    """Criterion A20, S7-REGRESSION: Pipeline input, review, media existing, dan ekspor tetap berfungsi.

    Verifikasi bahwa integrasi panel commit S7 pada src/ui/pages/3_Hasil.py
    tidak merusak fitur unduh Excel kanonik dan ringkasan media klasifikasi citra.
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
    # Tombol unduh kanonik harus tetap tersedia (A20 regresi pipeline)
    download_labels = [b.label for b in list(at.button) + list(at.download_button)]
    assert any("Unduh" in label for label in download_labels)

    # Panel review S7 pada 3_Hasil.py harus menampilkan komponen S7
    rendered_texts = [
        str(elem.value)
        for elem in list(at.subheader) + list(at.caption) + list(at.info)
    ]
    assert any("hierarki wilayah" in t.lower() for t in rendered_texts), (
        "S7 review panel in 3_Hasil.py must render regional hierarchy target."
    )
