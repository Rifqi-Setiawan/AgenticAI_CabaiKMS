"""Documentation parity tests for Round 4 audit remediation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v4_01_audit_fix_report_addendum_4():
    """docs/AUDIT_FIX_REPORT.md must contain Addendum 4 describing all findings F-1..F-10."""
    report_path = ROOT / "docs" / "AUDIT_FIX_REPORT.md"
    assert report_path.is_file(), "docs/AUDIT_FIX_REPORT.md must exist"
    content = report_path.read_text(encoding="utf-8")

    assert "## Addendum 4: Perbaikan Hasil Audit Ronde 3" in content
    assert "F-1" in content
    assert "cabai_app" in content
    assert "0005" in content
    assert "schema_0005_app_grants.sql" in content
    assert "PROMOTE" in content
    assert "MERGE" in content
    assert "set_document_habitat" in content


def test_v4_02_readme_contains_0005_and_varieties():
    """README.md contains migration 0005 and /varieties endpoint."""
    readme_path = ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    assert "0005" in content
    assert "/varieties" in content
