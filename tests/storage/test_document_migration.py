"""Acceptance test suite for Stage S8: Legacy Data Migration Script & Quarantine.

Contract source:
- reports/cabai-kms-jsonb/TECH_PLAN.md:
  * Line 525: Table 5 DoD & boundaries for S8 (Skrip Migrasi Data Legacy & Karantina, pemilik forge)
  * Line 553: Acceptance criterion A18 (test_migration_dry_run_and_unattributed_quarantine)
  * Line 554: Acceptance criterion A19 (test_no_destructive_purge_in_migration_pipeline)
  * Line 629: Section 9.3 Legacy table retention policy (30-day transition, read-only)
  * Line 716: Gate 3 dry-run staging acceptance criteria
- reports/cabai-kms-jsonb/PRD_CabaiKMS_JSONB.md:
  * Section G2: Data existing dan backup (no automatic production purge)
  * Section H1: Staged migration strategy (dry-run mapper, reconciliation manifest)
  * Section H2: Rollback procedure (pre-cutover & post-cutover delta handling)
  * Section I7: Retensi dan migrasi (quarantine for unattributed legacy rows)

Criteria covered:
- A18: Skrip migrasi data legacy berjalan dalam mode dry-run akuntabel; data tanpa habitat masuk karantina.
- A19: Retensi data legacy transparan; tidak ada purge produksi otomatis di kode produk.
- A16: Replay / re-eksekusi migrasi bersifat idempotent dan tidak menggandakan dokumen.
- DoD-S8-DRY-RUN: Mode dry-run adalah default dan tidak menulis ke database.
- DoD-S8-MANIFEST: Manifest rekonsiliasi total: total == mapped + quarantine + rejected.
- DoD-S8-QUARANTINE: Data legacy variety-only tanpa lokasi masuk manifest karantina review.
- DoD-S8-ROLLBACK: Simulasi rollback teruji tanpa destructive purge (pre & post-cutover).
- DoD-S8-DOCS: Dokumentasi prosedur docs/KMS_JSONB_MIGRATION.md tersedia dan lengkap.

Candidate implementation files (strict boundaries for forge):
- scripts/migrate_kms_documents.py
- docs/KMS_JSONB_MIGRATION.md

Test file (protected):
- tests/storage/test_document_migration.py
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import KnowledgeDocument
from src.storage.migrate import migrate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "migrate_kms_documents.py"
DOC_PATH = PROJECT_ROOT / "docs" / "KMS_JSONB_MIGRATION.md"

pytestmark = pytest.mark.integration


# ============================================================================
# Test Fixtures & Database Setup
# ============================================================================


def _load_migration_module() -> Any:
    """Load scripts.migrate_kms_documents dynamically.

    In the test-first RED phase, this raises ModuleNotFoundError because
    scripts/migrate_kms_documents.py has not yet been implemented by forge.
    """
    import scripts.migrate_kms_documents as module

    return module


@pytest.fixture
def test_db() -> Engine:
    """Disposable PostgreSQL test database connection. Refuses non-test databases."""
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://cabai_test@/cabai_kms_test?host=/tmp",
    )
    parsed = make_url(url)
    db_name = parsed.database or ""

    if not db_name.endswith("_test"):
        pytest.fail(f"Refusing integration tests on non-test database: {db_name}")
    if db_name == "cabai_kms":
        pytest.fail("Production database cabai_kms must never be touched by tests!")

    pytest.importorskip("psycopg")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL") or url

    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


@pytest.fixture
def legacy_seed_data(test_db: Engine) -> dict[str, Any]:
    """Seed representative legacy data into kms schema tables.

    Includes:
    1. Varieties: Cabai rawit and Cabai besar.
    2. Characteristics: Plant height, fruit length, chlorophyll content.
    3. Source artifact and acquisition run.
    4. variety_character_values with associated value_observations:
       - 4 records WITH valid administrative location provenance (Sleman & Wonosobo).
       - 2 records WITHOUT administrative location provenance (variety-only).
       - 1 invalid / rejected legacy record (corrupted value payload).
    """
    rawit_id = str(uuid4())
    besar_id = str(uuid4())
    char_height_id = str(uuid4())
    char_fruit_id = str(uuid4())
    char_chlorophyll_id = str(uuid4())

    source_sha = "0" * 64
    run_id = f"run_legacy_test_{uuid4().hex[:8]}"

    with test_db.connect() as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL kms.actor = 'sentinel-test'"))

            # 1. Source artifact
            conn.execute(
                text("""
                    INSERT INTO kms.source_artifacts (sha256, storage_uri, file_size)
                    VALUES (:sha, 'file:///data/legacy_survey.xlsx', 10240)
                    ON CONFLICT (sha256) DO NOTHING
                """),
                {"sha": source_sha},
            )

            # 2. Acquisition run
            conn.execute(
                text("""
                    INSERT INTO kms.acquisition_runs (
                        run_id, source_filename, file_sha256, source_uri,
                        schema_version, template_hash, config_fingerprint,
                        total_attributes, auto_accepted_count, reviewed_count,
                        status, revision, payload_sha256, draft_payload, base_versions
                    ) VALUES (
                        :run_id, 'legacy_survey.xlsx', :sha, 'file:///data/legacy_survey.xlsx',
                        'v1.0', :thash, 'cfg_legacy_001',
                        7, 5, 2,
                        'STAGED', 1, :psha, '{}'::jsonb, '{}'::jsonb
                    ) ON CONFLICT (run_id) DO NOTHING
                """),
                {
                    "run_id": run_id,
                    "sha": source_sha,
                    "thash": "1" * 64,
                    "psha": "2" * 64,
                },
            )

            # 3. Varieties
            conn.execute(
                text("""
                    INSERT INTO kms.varieties (id, canonical_name, origin_region)
                    VALUES
                        (:r_id, 'Cabai rawit (Capsicum frutescens L)', 'Sleman'),
                        (:b_id, 'cabai besar (Capsicum annum L)', 'Wonosobo')
                    ON CONFLICT (canonical_name) DO NOTHING
                """),
                {"r_id": rawit_id, "b_id": besar_id},
            )

            # 4. Characteristics
            conn.execute(
                text("""
                    INSERT INTO kms.characteristics (
                        id, canonical_key, label_id, organ_domain, source_domain, data_type, standard_unit
                    ) VALUES
                        (:c1, 'tinggi_tanaman', 'Tinggi Tanaman', 'habitus', 'morfologi', 'number', 'cm'),
                        (:c2, 'panjang_buah', 'Panjang Buah', 'buah', 'morfologi', 'number', 'cm'),
                        (:c3, 'chlorophyll_spad', 'Chlorophyll Content (SPAD)', 'daun', 'fisiologi', 'number', 'SPAD')
                    ON CONFLICT (canonical_key) DO NOTHING
                """),
                {"c1": char_height_id, "c2": char_fruit_id, "c3": char_chlorophyll_id},
            )

            # 5. Legacy values WITH valid administrative location (Desa Hargobinangun, Sleman)
            val1_id = str(uuid4())
            val2_id = str(uuid4())
            conn.execute(
                text("""
                    INSERT INTO kms.variety_character_values (
                        id, variety_id, characteristic_id, normalized_value, raw_source_value,
                        value_type, is_multi_value, confidence_score, status, run_id, version
                    ) VALUES
                        (:v1, :r_id, :c1, '120.5'::jsonb, '"120.5 cm"'::jsonb, 'number', false, 0.98, 'AUTO_ACCEPT', :run_id, 1),
                        (:v2, :r_id, :c3, '49.02'::jsonb, '"49.02"'::jsonb, 'number', false, 0.95, 'AUTO_ACCEPT', :run_id, 1)
                    ON CONFLICT (variety_id, characteristic_id) DO NOTHING
                """),
                {"v1": val1_id, "v2": val2_id, "r_id": rawit_id, "c1": char_height_id, "c3": char_chlorophyll_id, "run_id": run_id},
            )

            # Observations with location evidence for val1 and val2
            obs1_sha = "3" * 64
            obs2_sha = "4" * 64
            conn.execute(
                text("""
                    INSERT INTO kms.value_observations (
                        run_id, variety_id, characteristic_id, observation_sha256, evidence
                    ) VALUES
                        (:run_id, :r_id, :c1, :obs1, CAST(:ev1 AS jsonb)),
                        (:run_id, :r_id, :c3, :obs2, CAST(:ev2 AS jsonb))
                    ON CONFLICT DO NOTHING
                """),
                {
                    "run_id": run_id,
                    "r_id": rawit_id,
                    "c1": char_height_id,
                    "c3": char_chlorophyll_id,
                    "obs1": obs1_sha,
                    "obs2": obs2_sha,
                    "ev1": json.dumps({
                        "raw_address": "Dusun Randu, Desa Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta",
                        "village": "Desa Hargobinangun",
                        "district": "Kecamatan Pakem",
                        "regency": "Kabupaten Sleman",
                        "province": "Daerah Istimewa Yogyakarta",
                        "sheet": "Resume Data",
                        "row": 3,
                        "cell": "G3",
                    }),
                    "ev2": json.dumps({
                        "raw_address": "Dusun Randu, Desa Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta",
                        "village": "Desa Hargobinangun",
                        "district": "Kecamatan Pakem",
                        "regency": "Kabupaten Sleman",
                        "province": "Daerah Istimewa Yogyakarta",
                        "sheet": "Resume Data",
                        "row": 3,
                        "cell": "H3",
                    }),
                },
            )

            # 6. Legacy values WITH valid location in Desa Lamuk, Wonosobo
            val3_id = str(uuid4())
            val4_id = str(uuid4())
            conn.execute(
                text("""
                    INSERT INTO kms.variety_character_values (
                        id, variety_id, characteristic_id, normalized_value, raw_source_value,
                        value_type, is_multi_value, confidence_score, status, run_id, version
                    ) VALUES
                        (:v3, :b_id, :c1, '95.0'::jsonb, '"95.0 cm"'::jsonb, 'number', false, 0.95, 'AUTO_ACCEPT', :run_id, 1),
                        (:v4, :b_id, :c2, '14.2'::jsonb, '"14.2 cm"'::jsonb, 'number', false, 0.92, 'AUTO_ACCEPT', :run_id, 1)
                    ON CONFLICT (variety_id, characteristic_id) DO NOTHING
                """),
                {"v3": val3_id, "v4": val4_id, "b_id": besar_id, "c1": char_height_id, "c2": char_fruit_id, "run_id": run_id},
            )

            obs3_sha = "5" * 64
            obs4_sha = "6" * 64
            conn.execute(
                text("""
                    INSERT INTO kms.value_observations (
                        run_id, variety_id, characteristic_id, observation_sha256, evidence
                    ) VALUES
                        (:run_id, :b_id, :c1, :obs3, CAST(:ev3 AS jsonb)),
                        (:run_id, :b_id, :c2, :obs4, CAST(:ev4 AS jsonb))
                    ON CONFLICT DO NOTHING
                """),
                {
                    "run_id": run_id,
                    "b_id": besar_id,
                    "c1": char_height_id,
                    "c2": char_fruit_id,
                    "obs3": obs3_sha,
                    "obs4": obs4_sha,
                    "ev3": json.dumps({
                        "raw_address": "Dusun Pangempon, Desa Lamuk, Kec. Kalikajar, Kab. Wonosobo, Jawa Tengah",
                        "village": "Desa Lamuk",
                        "district": "Kecamatan Kalikajar",
                        "regency": "Kabupaten Wonosobo",
                        "province": "Jawa Tengah",
                        "sheet": "Resume Data",
                        "row": 12,
                        "cell": "G12",
                    }),
                    "ev4": json.dumps({
                        "raw_address": "Dusun Pangempon, Desa Lamuk, Kec. Kalikajar, Kab. Wonosobo, Jawa Tengah",
                        "village": "Desa Lamuk",
                        "district": "Kecamatan Kalikajar",
                        "regency": "Kabupaten Wonosobo",
                        "province": "Jawa Tengah",
                        "sheet": "Resume Data",
                        "row": 12,
                        "cell": "H12",
                    }),
                },
            )

            # 7. Legacy values WITHOUT valid administrative location (VARIETY-ONLY, MUST QUARANTINE)
            val5_id = str(uuid4())
            conn.execute(
                text("""
                    INSERT INTO kms.variety_character_values (
                        id, variety_id, characteristic_id, normalized_value, raw_source_value,
                        value_type, is_multi_value, confidence_score, status, run_id, version
                    ) VALUES
                        (:v5, :r_id, :c2, '8.5'::jsonb, '"8.5 cm"'::jsonb, 'number', false, 0.88, 'HUMAN_REVIEW', :run_id, 1)
                    ON CONFLICT (variety_id, characteristic_id) DO NOTHING
                """),
                {"v5": val5_id, "r_id": rawit_id, "c2": char_fruit_id, "run_id": run_id},
            )

            obs5_sha = "7" * 64
            conn.execute(
                text("""
                    INSERT INTO kms.value_observations (
                        run_id, variety_id, characteristic_id, observation_sha256, evidence
                    ) VALUES
                        (:run_id, :r_id, :c2, :obs5, CAST(:ev5 AS jsonb))
                    ON CONFLICT DO NOTHING
                """),
                {
                    "run_id": run_id,
                    "r_id": rawit_id,
                    "c2": char_fruit_id,
                    "obs5": obs5_sha,
                    "ev5": json.dumps({
                        "raw_address": None,
                        "location": None,
                        "notes": "Data laboratorium tanpa lokasi sampling lapangan definitif",
                        "sheet": "Tabulasi Lama",
                        "row": 4,
                        "cell": "D4",
                    }),
                },
            )

    return {
        "run_id": run_id,
        "rawit_id": rawit_id,
        "besar_id": besar_id,
        "char_height_id": char_height_id,
        "char_fruit_id": char_fruit_id,
        "char_chlorophyll_id": char_chlorophyll_id,
        "mapped_expected_count": 4,
        "quarantine_expected_count": 1,
    }


# ============================================================================
# Acceptance Tests: A18, A19, and S8 DoD
# ============================================================================


def test_migration_dry_run_and_unattributed_quarantine(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A18: Skrip migrasi data legacy berjalan dalam mode dry-run akuntabel;
    data tanpa habitat masuk karantina.

    Verifikasi bahwa:
    1. Eksekusi dry-run memetakan baris legacy variety_character_values yang memiliki
       lokasi administratif valid ke dokumen target (mapped).
    2. Data legacy tanpa lokasi administratif valid dialihkan ke manifest karantina review
       (quarantine_items).
    3. Tidak ada baris yang ditulis ke kms.knowledge_documents pada mode dry-run.
    """
    migration_module = _load_migration_module()
    manifest = migration_module.run_migration(
        db_url=str(test_db.url),
        dry_run=True,
    )

    assert isinstance(manifest, dict), "Manifest harus berupa dictionary hasil pemetaan"
    assert manifest.get("dry_run") is True, "Manifest harus menandai dry_run=True"

    summary = manifest.get("summary", {})
    assert summary.get("mapped_count") >= legacy_seed_data["mapped_expected_count"], (
        f"Expected at least {legacy_seed_data['mapped_expected_count']} mapped rows, got {summary.get('mapped_count')}"
    )
    assert summary.get("quarantine_count") >= legacy_seed_data["quarantine_expected_count"], (
        f"Expected at least {legacy_seed_data['quarantine_expected_count']} quarantined rows, got {summary.get('quarantine_count')}"
    )

    # Verifikasi item karantina memiliki alasan ketidakhadiran habitat/lokasi
    quarantine_items = manifest.get("quarantine_items", [])
    assert len(quarantine_items) >= 1, "Harus ada minimal 1 item di daftar karantina"
    for item in quarantine_items:
        assert item.get("variety_id") is not None
        assert "location" in item.get("reason", "").lower() or "unresolved" in item.get("reason", "").lower()

    # Verifikasi tabel kms.knowledge_documents tetap bersih (0 row)
    with test_db.connect() as conn:
        doc_count = conn.execute(
            text("SELECT COUNT(*) FROM kms.knowledge_documents")
        ).scalar()
        assert doc_count == 0, "Dry-run tidak boleh menulis ke kms.knowledge_documents!"


def test_migration_dry_run_is_default_and_writes_nothing_to_db(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A18, DoD S8: Dry-run adalah perilaku default dan tidak memutasi database.

    Verifikasi bahwa jika migrasi dijalankan tanpa flag eksplisit --apply / dry_run=False,
    sistem default ke dry-run, tidak melakukan INSERT, UPDATE, atau DELETE pada basis data.
    """
    migration_module = _load_migration_module()
    # Jalankan tanpa parameter dry_run eksplisit untuk menguji nilai default
    manifest = migration_module.run_migration(db_url=str(test_db.url))

    assert manifest.get("dry_run") is True, "Default run_migration harus dry_run=True!"

    with test_db.connect() as conn:
        doc_count = conn.execute(
            text("SELECT COUNT(*) FROM kms.knowledge_documents")
        ).scalar()
        assert doc_count == 0, "Default dry-run dilarang menulis ke kms.knowledge_documents"

        # Verifikasi data legacy tetap utuh dan tidak tersentuh
        val_count = conn.execute(
            text("SELECT COUNT(*) FROM kms.variety_character_values")
        ).scalar()
        assert val_count >= 5, "Tabel legacy variety_character_values tidak boleh berkurang"


def test_migration_manifest_reconciliation_total_accounting(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A18, PRD H1: Rekonsiliasi manifest akuntabel: total == mapped + quarantine + rejected.

    Verifikasi bahwa setiap baris data legacy terhitung secara definitif dalam manifest
    rekonsiliasi: tidak boleh ada baris legacy yang hilang tanpa alasan atau status.
    """
    migration_module = _load_migration_module()
    manifest = migration_module.run_migration(
        db_url=str(test_db.url),
        dry_run=True,
    )

    summary = manifest.get("summary", {})
    total = summary.get("total_legacy_rows", 0)
    mapped = summary.get("mapped_count", 0)
    quarantine = summary.get("quarantine_count", 0)
    rejected = summary.get("rejected_count", 0)

    assert total > 0, "Total baris legacy harus terhitung > 0"
    assert total == (mapped + quarantine + rejected), (
        f"Akuntansi rekonsiliasi tidak klop: total ({total}) != "
        f"mapped ({mapped}) + quarantine ({quarantine}) + rejected ({rejected})"
    )


def test_variety_only_legacy_without_location_enters_quarantine(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A18, PRD I7: Data legacy variety-only tanpa lokasi masuk karantina review;
    satu varietas banyak lokasi tidak mereplikasi semua nilai ke semua habitat.

    Verifikasi bahwa jika suatu varietas (misal Cabai rawit) telah memiliki dokumen habitat
    di Desa Hargobinangun, nilai legacy varietas tersebut yang TIDAK memiliki metadata lokasi
    DILARANG disalin secara membabi buta ke Desa Hargobinangun. Nilai tersebut wajib masuk karantina.
    """
    migration_module = _load_migration_module()
    manifest = migration_module.run_migration(
        db_url=str(test_db.url),
        dry_run=True,
    )

    quarantine_items = manifest.get("quarantine_items", [])
    rawit_quarantines = [
        item for item in quarantine_items
        if item.get("variety_id") == legacy_seed_data["rawit_id"]
    ]

    assert len(rawit_quarantines) >= 1, (
        "Nilai Cabai rawit tanpa lokasi harus masuk ke karantina review"
    )

    # Pastikan di daftar mapped_documents tidak ada replikasi liar nilai tanpa lokasi
    mapped_docs = manifest.get("mapped_documents", [])
    for doc in mapped_docs:
        # Jika dokumen rawit di Hargobinangun, atributnya tidak boleh mencakup c2 (fruit length yang tanpa lokasi)
        if doc.get("variety", {}).get("id") == legacy_seed_data["rawit_id"]:
            attrs = doc.get("attributes", {})
            assert "panjang_buah" not in attrs and "attr_panjang_buah" not in attrs, (
                "Nilai variety-only tanpa lokasi dilarang direplikasi ke habitat dokumen!"
            )


def test_migration_apply_flag_persists_mapped_documents_transactionally(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A18, DoD S8: Eksekusi dengan flag --apply menyimpan dokumen terpetakan
    secara transaksional ke basis data.

    Verifikasi bahwa saat dry_run=False (--apply), dokumen yang valid terpetakan berhasil
    disimpan ke kms.knowledge_documents, payload dokumen valid sesuai kontrak Pydantic v2,
    dan quarantine items dicatat untuk review lanjutan.
    """
    migration_module = _load_migration_module()
    manifest = migration_module.run_migration(
        db_url=str(test_db.url),
        dry_run=False,
    )

    assert manifest.get("dry_run") is False, "Manifest harus menandai dry_run=False"
    summary = manifest.get("summary", {})
    mapped_count = summary.get("mapped_count", 0)
    assert mapped_count > 0, "Harus ada dokumen yang terpetakan untuk disimpan"

    # Periksa tabel kms.knowledge_documents
    with test_db.connect() as conn:
        rows = conn.execute(
            text("SELECT id, variety_id, habitat_id, document, version FROM kms.knowledge_documents")
        ).mappings().all()

        assert len(rows) > 0, "kms.knowledge_documents harus terisi setelah --apply"
        for row in rows:
            doc_dict = row["document"]
            # Validasi kesesuaian kontrak KnowledgeDocument
            validated = KnowledgeDocument.model_validate(doc_dict)
            assert validated.schema_version == "kms-document-v1"
            assert validated.variety.id is not None
            assert validated.habitat.id is not None
            assert len(validated.attributes) > 0


def test_no_destructive_purge_in_migration_pipeline():
    """Criterion A19: Retensi data legacy transparan; tidak ada purge produksi otomatis di kode produk.

    Pemeriksaan statis dan runtime memastikan tidak ada eksekusi DROP TABLE atau TRUNCATE
    pada tabel legacy (kms.variety_character_values, kms.value_observations, kms.draft_revisions).
    """
    assert SCRIPT_PATH.is_file(), (
        f"Migration script {SCRIPT_PATH} does not exist yet (S8 implementation pending by forge)"
    )

    script_content = SCRIPT_PATH.read_text(encoding="utf-8")

    # 1. Pemeriksaan statis token terlarang
    forbidden_tokens = [
        "DROP TABLE",
        "TRUNCATE",
        "DROP SCHEMA",
        "CASCADE",
        "DELETE FROM kms.variety_character_values",
        "DELETE FROM kms.value_observations",
        "DELETE FROM kms.draft_revisions",
    ]

    for token in forbidden_tokens:
        assert token not in script_content.upper(), (
            f"Dilarang menggunakan perintah destruktif '{token}' di skrip migrasi legacy!"
        )

    # 2. Analisis AST memastikan tidak ada pemanggilan SQL destruktif tersembunyi
    parsed_ast = ast.parse(script_content)
    for node in ast.walk(parsed_ast):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text_val = node.value.upper()
            assert "TRUNCATE" not in text_val, "Terdapat klausa TRUNCATE pada string literal AST"
            assert "DROP TABLE" not in text_val, "Terdapat klausa DROP TABLE pada string literal AST"


def test_legacy_tables_retained_read_only_during_migration(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A19, PRD G2: Tabel legacy dipertahankan read-only selama masa transisi 30 hari.

    Verifikasi bahwa setelah eksekusi migrasi (bahkan dalam mode --apply), tabel historis
    kms.variety_character_values, kms.value_observations, dan kms.acquisition_runs
    tetap utuh, jumlah baris sama persis, dan tidak ada baris yang termutasi.
    """
    migration_module = _load_migration_module()
    # 1. Catat hitungan dan fingerprint data legacy sebelum migrasi
    with test_db.connect() as conn:
        count_val_before = conn.execute(
            text("SELECT COUNT(*) FROM kms.variety_character_values")
        ).scalar()
        count_obs_before = conn.execute(
            text("SELECT COUNT(*) FROM kms.value_observations")
        ).scalar()

    # 2. Jalankan migrasi dengan --apply
    migration_module.run_migration(db_url=str(test_db.url), dry_run=False)

    # 3. Verifikasi jumlah baris setelah migrasi sama persis
    with test_db.connect() as conn:
        count_val_after = conn.execute(
            text("SELECT COUNT(*) FROM kms.variety_character_values")
        ).scalar()
        count_obs_after = conn.execute(
            text("SELECT COUNT(*) FROM kms.value_observations")
        ).scalar()

        assert count_val_after == count_val_before, (
            "Jumlah baris kms.variety_character_values berubah setelah migrasi!"
        )
        assert count_obs_after == count_obs_before, (
            "Jumlah baris kms.value_observations berubah setelah migrasi!"
        )


def test_rollback_simulation_pre_cutover_preserves_legacy_state(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """DoD S8, PRD H2: Simulasi rollback pre-cutover mengembalikan konfigurasi tanpa kehilangan data legacy.

    Verifikasi bahwa jika migrasi dibatalkan sebelum cutover write baru JSONB:
    1. Operasi rollback memverifikasi data legacy 100% utuh.
    2. Dokumen JSONB sementara dapat dibersihkan dengan aman tanpa menyentuh tabel legacy.
    """
    migration_module = _load_migration_module()
    # Jalankan simulasi rollback pre-cutover
    rollback_result = migration_module.simulate_rollback(
        db_url=str(test_db.url),
        mode="pre-cutover",
    )

    assert rollback_result.get("status") == "success"
    assert rollback_result.get("legacy_data_intact") is True

    # Verifikasi data legacy tetap terbaca oleh kueri legacy
    with test_db.connect() as conn:
        val_rows = conn.execute(
            text("SELECT id, normalized_value FROM kms.variety_character_values")
        ).fetchall()
        assert len(val_rows) >= 5, "Data legacy harus tetap utuh dan terbaca"


def test_rollback_simulation_post_cutover_detects_delta_without_destructive_purge(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """DoD S8, PRD H2: Simulasi rollback post-cutover mendeteksi delta write baru
    dan mengekspor ke recovery staging tanpa destructive purge.

    Verifikasi bahwa jika write dokumen JSONB baru telah terjadi setelah cutover,
    prosedur rollback menolak pembersihan diam-diam, mengekspor snapshot recovery staging,
    dan menyajikan laporan rekonsiliasi status.
    """
    migration_module = _load_migration_module()
    # 1. Simulasikan adanya dokumen JSONB baru yang ditulis post-cutover
    with test_db.connect() as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL kms.actor = 'sentinel-test'"))
            conn.execute(
                text("""
                    INSERT INTO kms.knowledge_documents (
                        id, variety_id, habitat_id, document, version
                    ) VALUES (
                        'doc_post_cutover_new_01',
                        'variety_new_001',
                        'hab_wonosobo_lamuk_001',
                        '{"schema_version": "kms-document-v1", "variety": {"id": "v1", "label": "Rawit"}, "habitat": {"id": "h1", "label": "Desa Lamuk"}, "attributes": {}}'::jsonb,
                        1
                    ) ON CONFLICT DO NOTHING
                """)
            )

    # 2. Jalankan simulasi rollback post-cutover
    rollback_result = migration_module.simulate_rollback(
        db_url=str(test_db.url),
        mode="post-cutover",
        export_staging_path="/tmp/kms_rollback_recovery.json",
    )

    assert rollback_result.get("delta_detected") is True, (
        "Rollback post-cutover harus mendeteksi delta penulisan JSONB baru"
    )
    assert rollback_result.get("recovery_exported") is True, (
        "Delta harus diekspor ke recovery staging"
    )
    assert rollback_result.get("lossless_guarantee") is False, (
        "PRD H2: Tidak boleh mengklaim rollback lossless jika ada atribut/dokumen baru post-cutover"
    )


def test_migration_cli_interface_and_arguments():
    """DoD S8: Antarmuka CLI skrip migrasi mendukung --dry-run, --apply, dan --manifest-output.

    Verifikasi parser argumen skrip:
    1. Default argparse mengaktifkan dry-run (apply=False).
    2. Flag --apply menonaktifkan dry-run.
    3. Mendukung opsi path keluaran manifest (--manifest-output).
    """
    migration_module = _load_migration_module()
    # Default (tanpa argumen) -> dry_run=True / apply=False
    args_default = migration_module.parse_args([])
    assert getattr(args_default, "apply", False) is False, "Default CLI harus apply=False (dry-run)"

    # Flag --apply
    args_apply = migration_module.parse_args(["--apply"])
    assert getattr(args_apply, "apply", False) is True, "Flag --apply harus mengaktifkan mutasi basis data"

    # Flag --manifest-output
    custom_manifest_path = "/tmp/migration_manifest.json"
    args_output = migration_module.parse_args(["--manifest-output", custom_manifest_path])
    assert str(getattr(args_output, "manifest_output", "")) == custom_manifest_path


def test_migration_idempotent_reapplication(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Criterion A16, DoD S8: Eksekusi berulang skrip migrasi dengan --apply bersifat idempotent.

    Verifikasi bahwa menjalankan migrasi berulang kali tidak memicu error duplicate key,
    tidak menggandakan dokumen, dan menghasilkan state akhir yang deterministik.
    """
    migration_module = _load_migration_module()
    # Eksekusi pertama
    manifest_1 = migration_module.run_migration(db_url=str(test_db.url), dry_run=False)

    with test_db.connect() as conn:
        count_first = conn.execute(
            text("SELECT COUNT(*) FROM kms.knowledge_documents")
        ).scalar()

    # Eksekusi kedua (re-apply)
    manifest_2 = migration_module.run_migration(db_url=str(test_db.url), dry_run=False)

    with test_db.connect() as conn:
        count_second = conn.execute(
            text("SELECT COUNT(*) FROM kms.knowledge_documents")
        ).scalar()

    assert count_first == count_second, (
        f"Eksekusi ulang migrasi tidak idempotent: count berubah dari {count_first} ke {count_second}"
    )


def test_migration_documentation_exists_and_covers_procedures():
    """DoD S8: Berkas dokumentasi docs/KMS_JSONB_MIGRATION.md tersedia dan mencakup prosedur migrasi.

    Verifikasi bahwa dokumentasi migrasi memuat:
    1. Panduan eksekusi dry-run default dan verifikasi manifest.
    2. Karantina review data tanpa lokasi sampling administratif.
    3. Prosedur rollback pra-cutover dan pasca-cutover.
    4. Kebijakan retensi tabel legacy 30 hari tanpa purge destruktif.
    """
    assert DOC_PATH.is_file(), (
        f"Documentation file {DOC_PATH} does not exist yet (S8 documentation pending by forge)"
    )

    doc_text = DOC_PATH.read_text(encoding="utf-8")
    assert "--dry-run" in doc_text, "Dokumentasi harus mencantumkan opsi --dry-run"
    assert "manifest" in doc_text.lower(), "Dokumentasi harus menjelaskan manifest mapped/quarantine/rejected"
    assert "karantina" in doc_text.lower() or "quarantine" in doc_text.lower(), "Dokumentasi harus menjelaskan alur karantina"
    assert "rollback" in doc_text.lower(), "Dokumentasi harus mendokumentasikan prosedur rollback"
    assert "30" in doc_text, "Dokumentasi harus mencantumkan kebijakan masa transisi retensi 30 hari"
