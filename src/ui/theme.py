"""Shared UI/UX styling and Clean Agritech Lab theme injection for CABAI-Flow."""

import streamlit as st

CUSTOM_CSS = """
<style>
/* Modern Clean Agritech Lab Palette */
:root {
  --bg-main: #F8FAFC;
  --bg-card: #FFFFFF;
  --text-main: #0F172A;
  --text-muted: #64748B;
  --chili-red: #DC2626;
  --chili-maroon: #B91C1C;
  --leaf-green: #059669;
  --leaf-emerald: #10B981;
  --border-subtle: #E2E8F0;
  --border-hover: #CBD5E1;
}

/* Overall page background */
.stApp {
  background-color: var(--bg-main);
  color: var(--text-main);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
  background-color: #FFFFFF !important;
  border-right: 1px solid var(--border-subtle);
}

section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a {
  border-radius: 8px !important;
  color: #334155 !important;
  font-weight: 500 !important;
  padding: 8px 12px !important;
  transition: all 0.15s ease !important;
}

section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a:hover {
  background-color: #FEF2F2 !important;
  color: var(--chili-maroon) !important;
}

section[data-testid="stSidebar"] [data-testid="stSidebarNav"] li a[aria-current="page"] {
  background-color: #FEF2F2 !important;
  color: var(--chili-red) !important;
  font-weight: 600 !important;
  border-left: 3px solid var(--chili-red) !important;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
  color: var(--text-main);
}

/* Headings */
h1 {
  color: #0F172A !important;
  font-weight: 750 !important;
  letter-spacing: -0.025em !important;
}

h2, h3, h4 {
  color: #1E293B !important;
  font-weight: 650 !important;
  letter-spacing: -0.015em !important;
}

/* File Uploader styling */
div[data-testid="stFileUploader"] {
  background-color: #FFFFFF;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.02);
}

div[data-testid="stFileUploader"] section {
  background-color: #F8FAFC !important;
  border: 1.5px dashed #CBD5E1 !important;
  border-radius: 8px !important;
  transition: all 0.2s ease-in-out;
}

div[data-testid="stFileUploader"] section:hover {
  border-color: var(--chili-red) !important;
  background-color: #FEF2F2 !important;
}

/* Input elements: text input, selectbox, number input */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div {
  background-color: #FFFFFF !important;
  color: #0F172A !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02) !important;
}

.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
  border-color: var(--chili-red) !important;
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.12) !important;
}

/* Metric Cards */
div[data-testid="stMetric"] {
  background-color: #FFFFFF !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important;
  padding: 14px 18px !important;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04) !important;
  border-top: 3px solid var(--leaf-green) !important;
}

div[data-testid="stMetric"] label {
  color: var(--text-muted) !important;
  font-size: 0.8rem !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
  font-weight: 600 !important;
}

div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
  color: #0F172A !important;
  font-weight: 700 !important;
  font-feature-settings: "tnum" on, "lnum" on !important;
}

/* Buttons */
.stButton > button[kind="primary"],
.stButton > button:first-child:not([kind="secondary"]) {
  background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%) !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: 0 2px 4px rgba(220, 38, 38, 0.2) !important;
  transition: all 0.2s ease;
}

.stButton > button[kind="primary"]:hover,
.stButton > button:first-child:not([kind="secondary"]):hover {
  background: linear-gradient(135deg, #B91C1C 0%, #991B1B 100%) !important;
  box-shadow: 0 4px 8px rgba(185, 28, 28, 0.3) !important;
  transform: translateY(-1px);
}

.stButton > button[kind="secondary"] {
  background-color: #FFFFFF !important;
  color: #334155 !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
}

/* Monospace tags & code pills */
code {
  color: var(--chili-maroon) !important;
  background-color: #FEF2F2 !important;
  border: 1px solid #FECACA !important;
  border-radius: 4px !important;
  padding: 2px 6px !important;
  font-size: 0.85em !important;
  font-weight: 500 !important;
}

/* Radio buttons active color */
div[data-testid="stRadio"] div[role="radiogroup"] label[data-checked="true"] {
  color: var(--chili-maroon) !important;
  font-weight: 600 !important;
}

/* Success / Info / Warning Alerts */
div[data-testid="stAlert"] {
  border-radius: 10px !important;
  border: 1px solid var(--border-subtle) !important;
}

/* Dataframe clean styling */
div[data-testid="stDataFrame"] {
  background-color: #FFFFFF !important;
  border: 1px solid var(--border-subtle) !important;
  border-radius: 10px !important;
  overflow: hidden !important;
}
</style>
"""


def apply_theme():
    """Inject Clean Agritech Lab theme into Streamlit view."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
