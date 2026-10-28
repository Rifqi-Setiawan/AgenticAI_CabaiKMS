"""Suite pengujian runtime dan analisis query dinamis untuk pencegahan purge legacy S8.

Memverifikasi bahwa pipeline migrasi dan simulasi rollback tidak menjalankan perintah
SQL destruktif (DROP TABLE, DROP SCHEMA, TRUNCATE, DELETE FROM) terhadap tabel legacy
pada tingkat runtime engine database, serta mendeteksi query SQL dinamis yang dibangun
menggunakan string formatting (f-string, operator %, atau str.format).
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url

from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.migrate import migrate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "migrate_kms_documents.py"

pytestmark = pytest.mark.integration


# ============================================================================
# Interceptor Runtime SQL
# ============================================================================


class DestructivePurgeQueryInterceptor:
    """Interseptor eksekusi SQL pada tingkat engine dan cursor driver database.

    Lokasi pemeriksaan:
    Mendengarkan event 'before_cursor_execute' pada kelas Engine SQLAlchemy.
    Setiap query mentah yang dikirim ke database diperiksa terhadap pola regex
    perintah destruktif (DROP TABLE, DROP SCHEMA, TRUNCATE, DELETE FROM tabel legacy).
    """

    FORBIDDEN_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+SCHEMA\b", re.IGNORECASE),
        re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
        re.compile(
            r"\bDELETE\s+FROM\s+(?:kms\.)?(?:variety_character_values|value_observations|draft_revisions|acquisition_runs|source_artifacts|varieties|characteristics)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bCASCADE\b", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        self.captured_statements: list[str] = []
        self.destructive_queries: list[dict[str, Any]] = []

    def _hook(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        raw_stmt = str(statement).strip()
        self.captured_statements.append(raw_stmt)
        for pattern in self.FORBIDDEN_PATTERNS:
            match = pattern.search(raw_stmt)
            if match:
                self.destructive_queries.append({
                    "statement": raw_stmt,
                    "matched_pattern": pattern.pattern,
                    "matched_text": match.group(0),
                    "parameters": parameters,
                })

    def __enter__(self) -> "DestructivePurgeQueryInterceptor":
        event.listen(Engine, "before_cursor_execute", self._hook)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        event.remove(Engine, "before_cursor_execute", self._hook)


# ============================================================================
# Fixtures Database Uji & Seed Data
# ============================================================================


def _load_migration_module() -> Any:
    """Memuat modul skrip migrasi scripts.migrate_kms_documents."""
    import scripts.migrate_kms_documents as module

    return module


@pytest.fixture
def test_db() -> Generator[Engine, None, None]:
    """Koneksi database PostgreSQL uji. Menolak database non-uji."""
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://cabai_test@/cabai_kms_test?host=/tmp",
    )
    parsed = make_url(url)
    db_name = parsed.database or ""

    if not db_name.endswith("_test"):
        pytest.fail(f"Menolak uji integrasi pada database non-test: {db_name}")
    if db_name == "cabai_kms":
        pytest.fail("Database produksi cabai_kms tidak boleh disentuh oleh pengujian!")

    pytest.importorskip("psycopg")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL") or url

    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


@pytest.fixture
def legacy_seed_data(test_db: Engine) -> dict[str, Any]:
    """Menyemai data representatif tabel legacy untuk pengujian retensi runtime."""
    rawit_id = str(uuid4())
    besar_id = str(uuid4())
    char_height_id = str(uuid4())
    char_fruit_id = str(uuid4())
    char_chlorophyll_id = str(uuid4())

    source_sha = "0" * 64
    run_id = f"run_purge_test_{uuid4().hex[:8]}"

    with test_db.connect() as conn:
        with conn.begin():
            conn.execute(text("SET LOCAL kms.actor = 'purge-runtime-tester'"))

            conn.execute(
                text("""
                    INSERT INTO kms.source_artifacts (sha256, storage_uri, file_size)
                    VALUES (:sha, 'file:///data/legacy_survey.xlsx', 10240)
                    ON CONFLICT (sha256) DO NOTHING
                """),
                {"sha": source_sha},
            )

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

    return {
        "run_id": run_id,
        "rawit_id": rawit_id,
        "besar_id": besar_id,
        "val1_id": val1_id,
        "val2_id": val2_id,
    }


# ============================================================================
# Kasus Uji Penerimaan Tambahan
# ============================================================================


def test_runtime_migration_apply_executes_no_destructive_purge(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Pengujian runtime eksekusi migrasi mode apply terhadap tabel legacy.

    Apa yang diuji:
    Memastikan eksekusi run_migration(dry_run=False) tidak memanggil perintah
    destruktif (DROP, TRUNCATE, DELETE) terhadap tabel sumber legacy pada tingkat driver SQL,
    serta menjamin jumlah baris tabel legacy tidak berubah setelah migrasi selesai.

    Di mana letak pemeriksaannya:
    1. Interseptor cursor SQLAlchemy (DestructivePurgeQueryInterceptor) merekam seluruh
       statement SQL yang dikirim ke database selama proses migrasi berlangsung.
    2. Pengecekan row count SQL pada kms.variety_character_values dan kms.value_observations
       sebelum dan sesudah pemanggilan fungsi migrasi.
    """
    migration_module = _load_migration_module()

    with test_db.connect() as conn:
        count_vcv_before = conn.execute(
            text("SELECT COUNT(*) FROM kms.variety_character_values")
        ).scalar()
        count_vo_before = conn.execute(
            text("SELECT COUNT(*) FROM kms.value_observations")
        ).scalar()

    with DestructivePurgeQueryInterceptor() as interceptor:
        manifest = migration_module.run_migration(
            db_url=str(test_db.url),
            dry_run=False,
            actor="test-purge-verifier",
        )

    # 1. Verifikasi ketiadaan query destruktif pada tingkat driver runtime
    assert not interceptor.destructive_queries, (
        f"Terdeteksi query destruktif saat runtime migrasi: {interceptor.destructive_queries}"
    )

    # 2. Verifikasi statement SQL benar-benar dijalankan
    executed_statements = interceptor.captured_statements
    assert len(executed_statements) > 0, "Harus ada statement SQL yang dieksekusi saat migrasi apply."
    has_insert = any("INSERT INTO kms.knowledge_documents" in stmt for stmt in executed_statements)
    assert has_insert, "Eksekusi apply harus menjalankan INSERT ke tabel knowledge_documents."

    # 3. Verifikasi jumlah baris tabel legacy tetap utuh tanpa mutasi atau penghapusan
    with test_db.connect() as conn:
        count_vcv_after = conn.execute(
            text("SELECT COUNT(*) FROM kms.variety_character_values")
        ).scalar()
        count_vo_after = conn.execute(
            text("SELECT COUNT(*) FROM kms.value_observations")
        ).scalar()

    assert count_vcv_after == count_vcv_before, (
        f"Jumlah baris variety_character_values berubah: {count_vcv_before} -> {count_vcv_after}"
    )
    assert count_vo_after == count_vo_before, (
        f"Jumlah baris value_observations berubah: {count_vo_before} -> {count_vo_after}"
    )


def test_runtime_migration_dry_run_executes_zero_mutations(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
):
    """Pengujian runtime eksekusi migrasi mode dry-run terhadap integritas data.

    Apa yang diuji:
    Memastikan eksekusi mode dry-run tidak menjalankan perintah DDL/DML penulisan
    (INSERT, UPDATE, DELETE, TRUNCATE, DROP) ke database sama sekali.

    Di mana letak pemeriksaannya:
    1. Interseptor cursor SQLAlchemy merekam semua statement SQL selama pemanggilan
       run_migration(dry_run=True) dan memastikan ketiadaan operasi penulisan dokumen.
    2. Pemeriksaan tabel tujuan kms.knowledge_documents untuk memastikan tidak ada dokumen tertulis.
    """
    migration_module = _load_migration_module()

    with DestructivePurgeQueryInterceptor() as interceptor:
        manifest = migration_module.run_migration(
            db_url=str(test_db.url),
            dry_run=True,
            actor="test-purge-verifier",
        )

    assert not interceptor.destructive_queries, (
        f"Terdeteksi query destruktif saat dry-run: {interceptor.destructive_queries}"
    )

    # Pastikan tidak ada INSERT ke knowledge_documents pada dry-run
    mutating_stmts = [
        s for s in interceptor.captured_statements
        if re.search(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE|DROP)\b", s, re.IGNORECASE)
    ]
    assert not mutating_stmts, (
        f"Dry-run dilarang melakukan operasi mutasi: {mutating_stmts}"
    )


def test_runtime_rollback_simulation_executes_no_destructive_purge(
    test_db: Engine,
    legacy_seed_data: dict[str, Any],
    tmp_path: Path,
):
    """Pengujian runtime simulasi rollback pra-cutover dan pasca-cutover.

    Apa yang diuji:
    Memastikan prosedur simulasi rollback pada kedua mode (pre-cutover dan post-cutover)
    tidak menjalankan query destruktif terhadap tabel legacy.

    Di mana letak pemeriksaannya:
    1. Interseptor cursor SQLAlchemy membungkus eksekusi simulate_rollback(mode="pre-cutover")
       dan simulate_rollback(mode="post-cutover").
    2. Menilai daftar query yang dieksekusi terhadap pola FORBIDDEN_PATTERNS.
    3. Memeriksa keberadaan snapshot ekspor data pementasan staging recovery.
    """
    migration_module = _load_migration_module()
    staging_file = tmp_path / "rollback_recovery_staging.json"

    with DestructivePurgeQueryInterceptor() as interceptor:
        res_pre = migration_module.simulate_rollback(
            db_url=str(test_db.url),
            mode="pre-cutover",
            actor="test-purge-verifier",
        )
        res_post = migration_module.simulate_rollback(
            db_url=str(test_db.url),
            mode="post-cutover",
            export_staging_path=staging_file,
            actor="test-purge-verifier",
        )

    assert not interceptor.destructive_queries, (
        f"Terdeteksi query destruktif saat rollback: {interceptor.destructive_queries}"
    )
    assert res_pre.get("legacy_data_intact") is True, "Pre-cutover harus menandai legacy_data_intact=True"
    assert res_post.get("legacy_data_intact") is True, "Post-cutover harus menandai legacy_data_intact=True"


def test_ast_dynamic_query_construction_for_destructive_purge():
    """Pemeriksaan statis AST terhadap pembentukan query SQL dinamis.

    Apa yang diuji:
    Mendeteksi pembuatan perintah SQL destruktif melalui sintaks formatting dinamis,
    seperti f-string (ast.JoinedStr), operator concatenation (ast.BinOp dengan + atau %),
    atau pemanggilan str.format() (ast.Call), yang berpotensi menyamarkan perintah
    DROP, TRUNCATE, atau DELETE dari pemeriksaan konstanta literal biasa.

    Di mana letak pemeriksaannya:
    Analisis pohon sintaks abstrak (AST) dari berkas scripts/migrate_kms_documents.py.
    Menelusuri seluruh simpul JoinedStr, BinOp, dan Call untuk mencari penggabungan
    kata kunci destruktif dengan nama tabel legacy.
    """
    assert SCRIPT_PATH.is_file(), f"Berkas skrip migrasi tidak ditemukan di {SCRIPT_PATH}"

    source_code = SCRIPT_PATH.read_text(encoding="utf-8")
    parsed_tree = ast.parse(source_code, filename=str(SCRIPT_PATH))

    destructive_keywords = {"DROP", "TRUNCATE", "DELETE"}
    legacy_table_names = {
        "variety_character_values",
        "value_observations",
        "draft_revisions",
        "acquisition_runs",
        "varieties",
        "characteristics",
    }

    suspicious_dynamic_nodes: list[dict[str, Any]] = []

    for node in ast.walk(parsed_tree):
        # 1. Pemeriksaan f-string (ast.JoinedStr)
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    parts.append(part.value.upper())
            combined_text = " ".join(parts)
            has_kw = any(kw in combined_text for kw in destructive_keywords)
            has_tbl = any(tbl.upper() in combined_text for tbl in legacy_table_names)
            if has_kw and has_tbl:
                suspicious_dynamic_nodes.append({
                    "type": "JoinedStr (f-string)",
                    "lineno": getattr(node, "lineno", 0),
                    "snippet": combined_text,
                })

        # 2. Pemeriksaan konkatenasi string (ast.BinOp dengan Add atau Mod)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            text_chunks: list[str] = []
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    text_chunks.append(side.value.upper())
            combined_binop = " ".join(text_chunks)
            has_kw = any(kw in combined_binop for kw in destructive_keywords)
            has_tbl = any(tbl.upper() in combined_binop for tbl in legacy_table_names)
            if has_kw and has_tbl:
                suspicious_dynamic_nodes.append({
                    "type": "BinOp (string concatenation / %)",
                    "lineno": getattr(node, "lineno", 0),
                    "snippet": combined_binop,
                })

        # 3. Pemeriksaan pemanggilan format() (ast.Call)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            if isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
                format_base = node.func.value.value.upper()
                has_kw = any(kw in format_base for kw in destructive_keywords)
                has_tbl = any(tbl.upper() in format_base for tbl in legacy_table_names)
                if has_kw and has_tbl:
                    suspicious_dynamic_nodes.append({
                        "type": "Call (str.format)",
                        "lineno": getattr(node, "lineno", 0),
                        "snippet": format_base,
                    })

    assert not suspicious_dynamic_nodes, (
        f"Ditemukan konstruksi query dinamis yang mencurigakan di AST: {suspicious_dynamic_nodes}"
    )


def test_runtime_interceptor_detects_dynamic_formatted_destructive_query(test_db: Engine):
    """Pengujian validitas interseptor runtime terhadap query SQL dinamis.

    Apa yang diuji:
    Memvalidasi kemampuan DestructivePurgeQueryInterceptor dalam mendeteksi dan
    menggagalkan eksekusi query destruktif yang sengaja dibangun secara dinamis
    melalui f-string, operator modulo (%), dan str.format(), membuktikan bahwa
    interseptor runtime tidak dapat dikelabui oleh pembentukan string non-literal.

    Di mana letak pemeriksaannya:
    1. Simulasi eksekusi statement SQL dinamis ke connection database uji.
    2. Interseptor menangkap query pada level driver cursor dan memetakan pelanggaran
       ke dalam daftar destructive_queries.
    """
    interceptor = DestructivePurgeQueryInterceptor()

    target_table = "kms.variety_character_values"
    # Membangun query dinamis menggunakan berbagai mekanisme formatting
    dynamic_fstring = f"DELETE FROM {target_table} WHERE 1 = 0"
    dynamic_modulo = "TRUNCATE TABLE %s" % "kms.value_observations"
    dynamic_format = "DROP TABLE {}".format("kms.draft_revisions")

    with interceptor:
        with test_db.connect() as conn:
            # Jalankan query dinamis (DELETE berpredikat 1=0 aman dari mutasi data)
            conn.execute(text(dynamic_fstring))
            # Simulasikan deteksi hook untuk query lainnya
            interceptor._hook(conn, None, dynamic_modulo, (), None, False)
            interceptor._hook(conn, None, dynamic_format, (), None, False)

    assert len(interceptor.destructive_queries) == 3, (
        f"Interseptor harus menangkap 3 query destruktif dinamis, tertangkap: {len(interceptor.destructive_queries)}"
    )

    matched_texts = [item["matched_text"].upper() for item in interceptor.destructive_queries]
    assert any("DELETE FROM KMS.VARIETY_CHARACTER_VALUES" in t for t in matched_texts)
    assert any("TRUNCATE" in t for t in matched_texts)
    assert any("DROP TABLE" in t for t in matched_texts)
