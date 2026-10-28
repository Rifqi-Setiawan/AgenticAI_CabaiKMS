"""Persistent KMS inspector and candidate queue management."""
import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.integrations.streamlit_commit import render_inspector
from src.integrations.candidates_ui import render_candidates_panel, render_habitat_unknown_documents_panel
from src.ui.theme import apply_theme

apply_theme()

tab_docs, tab_cand, tab_nohab = st.tabs([
    "Dokumen JSONB Terdaftar",
    "Antrean Kandidat Varietas Baru",
    "Dokumen Perlu Habitat (D11)",
])

with tab_docs:
    render_inspector()

with tab_cand:
    render_candidates_panel()

with tab_nohab:
    render_habitat_unknown_documents_panel()
