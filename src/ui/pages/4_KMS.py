"""Persistent KMS inspector and crash recovery."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.integrations.streamlit_commit import render_inspector
from src.ui.theme import apply_theme

apply_theme()
render_inspector()
