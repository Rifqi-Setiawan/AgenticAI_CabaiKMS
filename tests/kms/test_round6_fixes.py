"""Tests for Round 6 audit fixes (H-1 fabricated habitat, H-2 exactness, H-3 habitat id, H-4 silent UI failures)."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import Engine

from src.agents.signal_fusion import FusionAction, fuse_photo_signals
from src.agents.variety_registry import VarietyRegistry
from src.agents.vision_classification import extract_photo_context_signal
from src.integrations.candidates_ui import (
    load_all_documents,
    render_habitat_unknown_documents_panel,
)
from src.storage.document_contracts import (
    AdministrativePath,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
)
from src.storage.document_repository import DocumentRepository
from src.storage.errors import InvalidState
from src.storage.identity_resolution import compute_habitat_id

REPO_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------------
# H-1: no fabricated administrative values in production code
# ----------------------------------------------------------------------------
def test_w1_no_hardcoded_administrative_values_in_src():
    forbidden = ['"Kabupaten Garut"', '"Kecamatan Tarogong"', "Kompatibilitas", "legacy test scripts"]
    offenders = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append((str(path.relative_to(REPO_ROOT)), token))
    assert offenders == []


def _run_habitat_panel(values: dict[str, str]):
    docs = [{"id": "plant_x:habitat_unknown", "variety": {"label": "Cabai X"}, "habitat_unknown": True, "media_refs": []}]
    mock_set = MagicMock()
    mock_warning = MagicMock()

    def fake_text_input(label, *args, **kwargs):
        key = kwargs.get("key", "")
        for prefix, val in values.items():
            if key.startswith(prefix):
                return val
        return ""

    fake_client = MagicMock()
    fake_client.request.return_value = {"items": []}
    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), patch("streamlit.markdown"), patch("streamlit.subheader"), \
         patch("streamlit.caption"), patch("streamlit.success"), patch("streamlit.rerun"), \
         patch("streamlit.radio", side_effect=lambda label, options, **kw: options[0]), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("streamlit.warning", mock_warning), \
         patch("streamlit.text_input", side_effect=fake_text_input), \
         patch("streamlit.button", return_value=True), \
         patch("src.integrations.candidates_ui.ui_client", return_value=fake_client), \
         patch("src.integrations.candidates_ui.set_document_habitat_api", mock_set):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False
        render_habitat_unknown_documents_panel(docs)
    return mock_set, mock_warning


def test_w2_only_village_filled_warns_and_makes_no_api_call():
    mock_set, mock_warning = _run_habitat_panel({"desa_": "Pananjung"})
    assert not mock_set.called
    assert mock_warning.called


def test_w3_four_tiers_use_user_values_verbatim():
    mock_set, _ = _run_habitat_panel(
        {"prov_": "Jawa Tengah", "kab_": "Wonosobo", "kec_": "Kalikajar", "desa_": "Lamuk"}
    )
    assert mock_set.called
    payload = mock_set.call_args[0][1]
    assert payload["administrative_path"]["province_name"] == "Jawa Tengah"
    assert payload["administrative_path"]["regency_name"] == "Wonosobo"
    assert payload["administrative_path"]["village_name"] == "Lamuk"
    assert payload["id"] == "hab_wonosobo_kalikajar_lamuk"


# ----------------------------------------------------------------------------
# H-2: exactness ignores indices/camera prefixes/organ words; candidate names are clean
# ----------------------------------------------------------------------------
def _other_outcome(filename: str, registry_names=("Rawit", "Rawit Hijau")):
    registry = VarietyRegistry.build(spreadsheet_varieties=list(registry_names))
    signal = extract_photo_context_signal(filename, registry=registry)
    visual = {"classification_status": "OTHER", "visual_confidence": 0.95, "matched_variety": None}
    return fuse_photo_signals(
        filename_match=signal.suggested_variety_hint,
        registry_known=registry,
        visual_result=visual,
        is_exact_hint=signal.is_exact_hint,
        raw_filename=filename,
    )


def test_x1_indexed_known_name_with_other_is_mismatch():
    assert _other_outcome("rawit_01.jpg").action == FusionAction.REVIEW_MISMATCH


def test_x2_camera_prefix_and_organ_word_ignored():
    assert _other_outcome("IMG_0012_rawit_buah.jpg").action == FusionAction.REVIEW_MISMATCH


def test_x3_extra_discriminating_word_stays_candidate():
    out = _other_outcome("rawit_merah_01.jpg")
    assert out.action == FusionAction.CANDIDATE
    assert out.suggested_candidate_name == "rawit merah"


def test_x4_unregistered_name_is_clean_candidate_suggestion():
    out = _other_outcome("IMG_0034_kopay_03.jpg")
    assert out.action == FusionAction.CANDIDATE
    assert out.suggested_candidate_name == "kopay"


# ----------------------------------------------------------------------------
# H-4: pagination helper loads everything
# ----------------------------------------------------------------------------
def test_z2_load_all_documents_paginates():
    docs = [{"id": f"d{i}"} for i in range(250)]

    def fake_request(method, path, params=None, **kw):
        off, lim = params["offset"], params["limit"]
        return {"items": docs[off: off + lim]}

    client = MagicMock()
    client.request.side_effect = fake_request
    assert len(load_all_documents(client, page_size=100)) == 250


def test_z1_failed_document_load_is_surfaced_not_swallowed():
    from src.integrations.candidates_ui import render_habitat_unknown_documents_panel as panel

    docs = [{"id": "plant_x:habitat_unknown", "variety": {"label": "Cabai X"}, "habitat_unknown": True, "media_refs": []}]
    failing = MagicMock()
    failing.request.side_effect = RuntimeError("api down")
    mock_warning = MagicMock()
    with patch("streamlit.expander") as ex, patch("streamlit.write"), patch("streamlit.markdown"), \
         patch("streamlit.subheader"), patch("streamlit.radio", side_effect=lambda l, o, **k: o[0]), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("streamlit.text_input", return_value=""), patch("streamlit.button", return_value=False), \
         patch("streamlit.warning", mock_warning), \
         patch("src.integrations.candidates_ui.ui_client", return_value=failing):
        ex.return_value.__enter__.return_value = MagicMock()
        ex.return_value.__exit__.return_value = False
        panel(docs)
    assert mock_warning.called


# ----------------------------------------------------------------------------
# H-3: server verifies habitat id against the administrative path
# ----------------------------------------------------------------------------
@pytest.fixture
def doc_repo_db() -> DocumentRepository:
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL not configured")
    from src.storage.config import Settings
    from src.storage.db import make_engine
    from src.storage.migrate import migrate

    migrate(admin_url)
    settings = Settings(_env_file=None, database_url=admin_url, database_admin_url=admin_url)
    return DocumentRepository(make_engine(settings))


def _stage_unknown_doc(repo: DocumentRepository, suffix: str) -> str:
    plant = PlantIdentity(id=f"plant_r6_{suffix}", label=f"Cabai R6 {suffix}", identity_level="cultivar")
    unknown = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="Unknown", regency_name="Unknown", district_name="Unknown", village_name="Unknown"),
        label="Habitat Tidak Diketahui",
    )
    key = f"{plant.id}:{unknown.id}"
    doc = KnowledgeDocument(variety=plant, habitat=unknown, attributes={}, media_refs=[], habitat_unknown=True)
    draft = repo.stage_direct_document(key, doc, run_id=f"run_r6_{suffix}", actor="curator-alice")
    repo.commit(f"run_r6_{suffix}", draft["revision"], draft["payload_sha256"], actor="curator-alice")
    return key


def _payload(hab_id: str) -> dict:
    return {
        "id": hab_id,
        "label": "Desa Lamuk",
        "definition": "administrative_village_v1",
        "administrative_path": {
            "province_name": "Jawa Tengah",
            "regency_name": "Wonosobo",
            "district_name": "Kalikajar",
            "village_name": "Lamuk",
        },
    }


def test_y1_registered_habitat_id_cannot_be_reused_for_another_path(doc_repo_db):
    suffix = uuid.uuid4().hex[:8]
    first = _stage_unknown_doc(doc_repo_db, suffix + "a")
    hab_id = f"hab_r6_{suffix}"
    doc_repo_db.set_document_habitat(first, _payload(hab_id), actor="curator-alice", actor_role="curator")

    second = _stage_unknown_doc(doc_repo_db, suffix + "b")
    other_path = _payload(hab_id)
    other_path["administrative_path"]["village_name"] = "Desa Lain"
    with pytest.raises(InvalidState):
        doc_repo_db.set_document_habitat(second, other_path, actor="curator-alice", actor_role="curator")


def test_y2_matching_id_is_accepted():
    # Pure check of the id rule the server relies on.
    path = AdministrativePath(province_name="Jawa Tengah", regency_name="Wonosobo", district_name="Kalikajar", village_name="Lamuk")
    assert compute_habitat_id(path) == "hab_wonosobo_kalikajar_lamuk"


def test_y3_matching_id_set_habitat_succeeds(doc_repo_db):
    key = _stage_unknown_doc(doc_repo_db, uuid.uuid4().hex[:8])
    result = doc_repo_db.set_document_habitat(key, _payload("hab_wonosobo_kalikajar_lamuk"), actor="curator-alice", actor_role="curator")
    assert result["habitat"]["id"] == "hab_wonosobo_kalikajar_lamuk"
    assert result["habitat_unknown"] is False
