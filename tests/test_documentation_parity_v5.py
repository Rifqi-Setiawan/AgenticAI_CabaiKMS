"""Documentation parity tests for Round 5 audit remediation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v5_01_audit_fix_report_addendum_5():
    """docs/AUDIT_FIX_REPORT.md must contain Addendum 5 describing all findings G-1..G-8."""
    report_path = ROOT / "docs" / "AUDIT_FIX_REPORT.md"
    assert report_path.is_file(), "docs/AUDIT_FIX_REPORT.md must exist"
    content = report_path.read_text(encoding="utf-8")

    assert "## Addendum 5: Perbaikan Hasil Audit Ronde 4" in content
    assert "G-1" in content
    assert "TypeError" in content
    assert "G-2" in content
    assert "compute_habitat_id" in content
    assert "G-3" in content
    assert "expected_version" in content
    assert "G-4" in content
    assert "G-6" in content
    assert "habitat_migration_relink" in content


def test_v5_02_image_classification_documents_habitat_relink():
    """docs/IMAGE_CLASSIFICATION.md documents G-6 habitat_migration_relink."""
    doc_path = ROOT / "docs" / "IMAGE_CLASSIFICATION.md"
    content = doc_path.read_text(encoding="utf-8")
    assert "habitat_migration_relink" in content
    assert "compute_habitat_id" in content
