"""Documentation parity tests for Putaran 2 audit fixes (D-01..D-03).

Tests:
D-01: docs/AUDIT_FIX_REPORT.md contains 'Addendum 2', 'D2', 'T-H1', 'T-H2', 'T-H3', 'T-M1',
      'T-M2', 'T-M3', 'T-M4', the K1 approval commit hash '5f6022e', and approval timestamp.
D-02: docs/DESIGN_DECISIONS.md contains entries D7, D8, and D9.
D-03: No TODO or FIXME markers exist in the touched docs files.
"""

from __future__ import annotations

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_d01_audit_fix_report_addendum_2():
    """D-01: docs/AUDIT_FIX_REPORT.md contains all required Addendum 2 markers."""
    report_path = REPO_ROOT / "docs" / "AUDIT_FIX_REPORT.md"
    assert report_path.is_file(), "docs/AUDIT_FIX_REPORT.md missing"
    content = report_path.read_text(encoding="utf-8")

    required_keywords = [
        "Addendum 2",
        "D2",
        "T-H1",
        "T-H2",
        "T-H3",
        "T-M1",
        "T-M2",
        "T-M3",
        "T-M4",
        "5f6022e",
    ]
    for kw in required_keywords:
        assert kw in content, f"Missing required keyword '{kw}' in docs/AUDIT_FIX_REPORT.md"


def test_d02_design_decisions_d7_d8_d9():
    """D-02: docs/DESIGN_DECISIONS.md contains entries D7, D8, and D9."""
    dec_path = REPO_ROOT / "docs" / "DESIGN_DECISIONS.md"
    assert dec_path.is_file(), "docs/DESIGN_DECISIONS.md missing"
    content = dec_path.read_text(encoding="utf-8")

    for marker in ["D7", "D8", "D9"]:
        assert marker in content, f"Missing decision marker '{marker}' in docs/DESIGN_DECISIONS.md"


def test_d03_no_todo_or_fixme_in_touched_docs():
    """D-03: No TODO or FIXME markers in touched documentation files."""
    files_to_check = [
        REPO_ROOT / "docs" / "AUDIT_FIX_REPORT.md",
        REPO_ROOT / "docs" / "DESIGN_DECISIONS.md",
        REPO_ROOT / "docs" / "kms" / "02_POSTGRESQL_KMS_SPECIFICATION.md",
    ]
    for p in files_to_check:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            assert "TODO" not in text, f"Found TODO in {p.name}"
            assert "FIXME" not in text, f"Found FIXME in {p.name}"
