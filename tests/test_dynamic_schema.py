"""Dynamic canonical schema (phase 2, stage 1): appended rows, unchanged template output, persistence guards."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.schema.canonical import CanonicalSchema
from src.schema.contracts import valid_row_ids
from src.schema.dynamic import (
    ExtensionRow,
    build_run_schema,
    collection_name_for,
    dynamic_schema_enabled,
    extend_schema,
    extension_hash,
)
from src.ui.output_builder import SHEET_NAME, CanonicalOutputBuilder


@pytest.fixture(autouse=True)
def _reset_known_rows():
    """The set of acquired row ids is process-global; keep it from leaking into unrelated tests."""
    from src.schema import dynamic

    yield
    dynamic._KNOWN_EXTRA_IDS.clear()


def _row(seq: int, label: str, key: str, domain: str = "buah") -> ExtensionRow:
    return ExtensionRow(canonical_key=key, label=label, domain=domain, seq=seq, contoh_nilai=("1500",))


def test_no_rows_returns_the_template_schema_unchanged():
    base = CanonicalSchema.from_template()
    assert extend_schema(base, []) is base
    assert build_run_schema(()).schema_version == base.schema_version
    assert collection_name_for(base) == "canonical_rows"


def test_acquired_rows_are_appended_with_continuing_ids_and_versioned():
    base = CanonicalSchema.from_template()
    n = len(base.rows)
    ext = extend_schema(base, [_row(2, "Kandungan Vitamin C", "kandungan_vitamin_c"), _row(1, "Kadar Capsaicin", "kadar_capsaicin")])
    assert [r.id for r in ext.rows[:n]] == [r.id for r in base.rows]
    assert [r.canonical_key for r in ext.rows[n:]] == ["kadar_capsaicin", "kandungan_vitamin_c"]  # ordered by seq
    assert [r.id for r in ext.rows[n:]] == [f"r_{n + 1}", f"r_{n + 2}"]
    assert ext.schema_version.startswith(base.schema_version + "+ext.")
    assert ext.template_hash == base.template_hash
    assert collection_name_for(ext).startswith("canonical_rows_x")


def test_conflicting_stored_rows_never_shadow_template_rows():
    base = CanonicalSchema.from_template()
    clash_key = _row(1, "Label Lain", base.rows[0].canonical_key)
    clash_label = _row(2, base.rows[1].label, "kunci_unik_baru")
    assert extend_schema(base, [clash_key, clash_label]) is base


def test_extension_hash_is_stable_and_changes_with_content():
    a = [_row(1, "Kadar Capsaicin", "kadar_capsaicin")]
    assert extension_hash(a) == extension_hash(list(a)) != ""
    assert extension_hash(a) != extension_hash([_row(1, "Kadar Capsaicin Total", "kadar_capsaicin")])
    assert extension_hash([]) == ""


def test_new_row_ids_become_valid_mapping_targets_after_a_run_schema_is_built():
    base = CanonicalSchema.from_template()
    new_id = f"r_{len(base.rows) + 1}"
    assert new_id not in valid_row_ids()
    build_run_schema((_row(1, "Atribut Uji Validator", "atribut_uji_validator"),))
    assert new_id in valid_row_ids()


def test_excel_keeps_template_rows_identical_and_adds_rows_at_the_end():
    base = CanonicalSchema.from_template()
    ext = extend_schema(base, [_row(1, "Kadar Capsaicin", "kadar_capsaicin")])
    plain, extended = CanonicalOutputBuilder(schema=base), CanonicalOutputBuilder(schema=ext)
    for builder in (plain, extended):
        builder.add_variety("Cabai Uji")
        builder.set_cell(base.rows[2].id, "Cabai Uji", "nilai")
    extended.set_cell(ext.rows[-1].id, "Cabai Uji", "1500")
    a, b = plain.build_workbook()[SHEET_NAME], extended.build_workbook()[SHEET_NAME]
    for row in range(1, len(base.rows) + 2):
        assert [c.value for c in a[row]] == [c.value for c in b[row]], f"row {row} differs"
    assert b.max_row == a.max_row + 1
    assert b.cell(row=b.max_row, column=2).value == "Kadar Capsaicin"
    assert b.cell(row=b.max_row, column=3).value == "1500"


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("KMS_DYNAMIC_SCHEMA", raising=False)
    assert dynamic_schema_enabled() is False
    from src.ui.pipeline_runner import _load_extension_rows_for_run

    assert _load_extension_rows_for_run() == ((), None)
    monkeypatch.setenv("KMS_DYNAMIC_SCHEMA", "true")
    assert dynamic_schema_enabled() is True


# ----------------------------------------------------------------------------- database
@pytest.fixture
def db() -> Engine:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured; PostgreSQL test database required.")
    from src.storage.config import Settings
    from src.storage.db import make_engine
    from src.storage.migrate import migrate

    migrate(os.getenv("TEST_DATABASE_ADMIN_URL", url))
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _acquire(repo, label, domain="buah", **kw):
    return repo.acquire(label=label, domain=domain, examples=["1500"], source_label=label, run_id="run_dyn",
                        source_sha256="a" * 64, actor="tester", reason="uji akuisisi", **kw)


@pytest.mark.integration
def test_acquire_is_idempotent_and_duplicate_averse(db: Engine):
    from src.storage.schema_rows import SchemaRowRepository

    repo = SchemaRowRepository(db)
    label = f"Kadar Gula Buah {uuid.uuid4().hex[:6]}"
    first = _acquire(repo, label)
    assert first["created"] and first["row"]["status"] == "provisional"
    again = _acquire(repo, label.upper())
    assert not again["created"] and again["duplicate_of"] == first["row"]["canonical_key"]
    template = CanonicalSchema.from_template()
    dup = _acquire(repo, template.rows[3].label)
    assert not dup["created"] and dup["duplicate_of"] == template.rows[3].canonical_key
    alias = _acquire(repo, template.rows[3].alt_labels[0]) if template.rows[3].alt_labels else dup
    assert not alias["created"]
    listed = repo.list_rows()["rows"]
    assert first["row"]["canonical_key"] in {r["canonical_key"] for r in listed}
    seqs = [r["seq"] for r in listed]
    assert seqs == sorted(seqs)


@pytest.mark.integration
def test_acquire_validates_domain_and_protects_stored_rows(db: Engine):
    from src.storage.errors import InvalidState
    from src.storage.schema_rows import SchemaRowRepository

    repo = SchemaRowRepository(db)
    with pytest.raises(InvalidState):
        _acquire(repo, f"Atribut Domain Salah {uuid.uuid4().hex[:6]}", domain="tidak_ada")
    row = _acquire(repo, f"Atribut Terlindungi {uuid.uuid4().hex[:6]}")["row"]
    with pytest.raises(Exception):
        with db.begin() as conn:
            conn.execute(text("UPDATE kms.schema_rows_ext SET label = 'diubah' WHERE canonical_key = :k"), {"k": row["canonical_key"]})
    with pytest.raises(Exception):
        with db.begin() as conn:
            conn.execute(text("DELETE FROM kms.schema_rows_ext WHERE canonical_key = :k"), {"k": row["canonical_key"]})
    with db.begin() as conn:  # status is allowed to change
        conn.execute(text("UPDATE kms.schema_rows_ext SET status = 'approved' WHERE canonical_key = :k"), {"k": row["canonical_key"]})
