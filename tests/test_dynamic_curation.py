"""Dynamic schema stage 3: stable ids, merge aliases, curator actions and panel."""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import Engine

from src.schema.canonical import CanonicalSchema
from src.schema.dynamic import ExtensionAlias, ExtensionRow, extend_schema


@pytest.fixture(autouse=True)
def _reset_known_rows():
    from src.schema import dynamic

    yield
    dynamic._KNOWN_EXTRA_IDS.clear()


def _row(seq, label, key):
    return ExtensionRow(canonical_key=key, label=label, domain="buah", seq=seq)


def test_row_ids_follow_stored_seq_so_a_missing_row_never_renumbers_the_others():
    base = CanonicalSchema.from_template()
    n = len(base.rows)
    with_both = extend_schema(base, [_row(1, "Atribut Satu", "atribut_satu"), _row(2, "Atribut Dua", "atribut_dua")])
    only_second = extend_schema(base, [_row(2, "Atribut Dua", "atribut_dua")])  # seq 1 merged or discarded
    assert with_both.row_by_key("atribut_dua").id == only_second.row_by_key("atribut_dua").id == f"r_{n + 2}"
    assert len(only_second.rows) == n + 1


def test_merge_alias_extends_the_target_row_and_changes_the_schema_version():
    base = CanonicalSchema.from_template()
    target = base.rows[3]
    ext = extend_schema(base, [], [ExtensionAlias(target_key=target.canonical_key, alias="Sinonim Uji Kurator")])
    assert ext is not base and ext.schema_version.startswith(base.schema_version + "+ext.")
    assert "Sinonim Uji Kurator" in ext.row_by_key(target.canonical_key).alt_labels
    assert ext.row_by_key(target.canonical_key).id == target.id
    assert len(ext.rows) == len(base.rows)
    same_again = extend_schema(base, [], [ExtensionAlias(target_key=target.canonical_key, alias=target.label)])
    assert same_again is base  # an alias equal to the existing label adds nothing


def test_panel_offers_approve_merge_and_discard_for_each_provisional_row():
    from src.integrations import schema_rows_ui

    rows = [
        {"label": "Kadar Gula", "canonical_key": "kadar_gula", "domain": "buah", "status": "provisional", "examples": ["12"],
         "source_label": "Gula", "created_from_run": "r1", "merged_into_key": None},
        {"label": "Aroma", "canonical_key": "aroma", "domain": "buah", "status": "approved", "examples": [],
         "source_label": "Aroma", "created_from_run": "r1", "merged_into_key": None},
    ]
    client = MagicMock()
    client.request.return_value = {"rows": rows}
    keys: list[str] = []

    def button(label, key=None, **kwargs):
        keys.append(str(key))
        return False

    with patch("streamlit.expander") as expander, patch("streamlit.subheader"), patch("streamlit.caption"), \
            patch("streamlit.dataframe"), patch("streamlit.text_input", return_value=""), \
            patch("streamlit.selectbox", return_value="x"), patch("streamlit.button", side_effect=button):
        expander.return_value.__enter__.return_value = MagicMock()
        expander.return_value.__exit__.return_value = False
        schema_rows_ui.render_schema_rows_panel(client)
    assert sum(k.startswith("sr_ok_") for k in keys) == 1  # only the provisional row gets actions
    assert any(k.startswith("sr_merge_") for k in keys) and any(k.startswith("sr_drop_") for k in keys)


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


def _acq(repo, label, **kw):
    return repo.acquire(label=label, domain="buah", examples=["1"], source_label=label, run_id="r", source_sha256=None,
                        actor="t", reason="uji kurasi", **kw)


@pytest.mark.integration
def test_merge_into_acquired_row_moves_labels_to_aliases(db: Engine):
    from src.storage.schema_rows import SchemaRowRepository

    repo, tag = SchemaRowRepository(db), uuid.uuid4().hex[:6]
    a = _acq(repo, f"Kadar Vitamin C {tag}")["row"]
    b = _acq(repo, f"Kandungan Askorbat {tag}", aliases=[f"Ascorbic acid {tag}"])["row"]
    out = repo.merge(b["canonical_key"], a["canonical_key"], actor="curator", reason="Bermakna sama dengan vitamin C")
    assert out["status"] == "merged"
    listed = repo.list_rows()
    assert b["canonical_key"] not in {r["canonical_key"] for r in listed["rows"]}
    pairs = {(x["alias"].lower(), x["target_key"]) for x in listed["aliases"]}
    assert (f"kandungan askorbat {tag}", a["canonical_key"]) in pairs
    again = _acq(repo, f"KANDUNGAN ASKORBAT {tag}")
    assert not again["created"] and again["duplicate_of"] == a["canonical_key"]
    again2 = _acq(repo, f"ascorbic acid {tag}")
    assert not again2["created"] and again2["duplicate_of"] == a["canonical_key"]


@pytest.mark.integration
def test_merge_into_template_row_and_guards(db: Engine):
    from src.storage.errors import InvalidState
    from src.storage.schema_rows import SchemaRowRepository

    repo, tag = SchemaRowRepository(db), uuid.uuid4().hex[:6]
    row = _acq(repo, f"Panjang Daun Dewasa Uji {tag}")["row"]
    target = CanonicalSchema.from_template().rows[5].canonical_key
    with pytest.raises(InvalidState):
        repo.merge(row["canonical_key"], target, actor="c", reason="pendek")
    with pytest.raises(InvalidState):
        repo.merge(row["canonical_key"], row["canonical_key"], actor="c", reason="tidak boleh ke diri sendiri")
    with pytest.raises(InvalidState):
        repo.merge(row["canonical_key"], "kunci_tidak_ada", actor="c", reason="target tidak ada di katalog")
    repo.merge(row["canonical_key"], target, actor="c", reason="Sama dengan baris template")
    assert any(a["target_key"] == target for a in repo.list_rows()["aliases"])
    with pytest.raises(InvalidState):
        repo.merge(row["canonical_key"], target, actor="c", reason="sudah digabung sebelumnya")


@pytest.mark.integration
def test_approve_and_discard_and_a_discarded_label_is_not_reacquired(db: Engine):
    from src.storage.errors import InvalidState
    from src.storage.schema_rows import SchemaRowRepository

    repo, tag = SchemaRowRepository(db), uuid.uuid4().hex[:6]
    keep = _acq(repo, f"Ketebalan Kulit Buah {tag}")["row"]
    drop = _acq(repo, f"Catatan Tambahan Lain {tag}")["row"]
    assert repo.set_status(keep["canonical_key"], "approved", actor="c", reason="Karakter buah yang sah")["status"] == "approved"
    with pytest.raises(InvalidState):
        repo.set_status(keep["canonical_key"], "approved", actor="c", reason="sudah disetujui sebelumnya")
    repo.set_status(drop["canonical_key"], "discarded", actor="c", reason="Bukan karakter tanaman")
    keys = {r["canonical_key"] for r in repo.list_rows()["rows"]}
    assert keep["canonical_key"] in keys and drop["canonical_key"] not in keys
    retry = _acq(repo, f"Catatan Tambahan Lain {tag}")
    assert retry["created"] is False and retry.get("rejected") is True
    statuses = {r["canonical_key"]: r["status"] for r in repo.list_all()}
    assert statuses[keep["canonical_key"]] == "approved" and statuses[drop["canonical_key"]] == "discarded"
