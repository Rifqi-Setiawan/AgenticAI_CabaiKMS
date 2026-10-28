"""Documentation parity tests for Round 3 (B-7).

Tests:
1. README.md contains 'CANDIDATE', 'habitat_unknown', '/candidates', and '0004'.
2. docs/DESIGN_DECISIONS.md contains entries D10, D11, D12, and D13.
3. docs/IMAGE_CLASSIFICATION.md exists and documents the 3-signal flow, candidate queue, and evaluation.
4. docs/kms/02_POSTGRESQL_KMS_SPECIFICATION.md documents migration 0004.
5. No TODO or FIXME markers in touched docs.
"""

from __future__ import annotations

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_v3_01_readme_contains_round3_markers():
    """README.md contains CANDIDATE, habitat_unknown, /candidates, and 0004."""
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.is_file(), "README.md missing"
    content = readme_path.read_text(encoding="utf-8")

    for marker in ["CANDIDATE", "habitat_unknown", "/candidates", "0004"]:
        assert marker in content, f"Missing required marker '{marker}' in README.md"


def test_v3_02_design_decisions_d10_d13():
    """docs/DESIGN_DECISIONS.md contains entries D10, D11, D12, and D13."""
    dec_path = REPO_ROOT / "docs" / "DESIGN_DECISIONS.md"
    assert dec_path.is_file(), "docs/DESIGN_DECISIONS.md missing"
    content = dec_path.read_text(encoding="utf-8")

    for marker in ["D10", "D11", "D12", "D13"]:
        assert marker in content, f"Missing decision marker '{marker}' in docs/DESIGN_DECISIONS.md"


def test_v3_03_image_classification_doc_exists_and_content():
    """docs/IMAGE_CLASSIFICATION.md exists and covers key workflows."""
    doc_path = REPO_ROOT / "docs" / "IMAGE_CLASSIFICATION.md"
    assert doc_path.is_file(), "docs/IMAGE_CLASSIFICATION.md missing"
    content = doc_path.read_text(encoding="utf-8")

    required = [
        "CANDIDATE",
        "AUTO_LINK",
        "REVIEW_MISMATCH",
        "REVIEW_UNCERTAIN",
        "habitat_unknown",
        "eval_vision",
    ]
    for r in required:
        assert r in content, f"Missing section/marker '{r}' in docs/IMAGE_CLASSIFICATION.md"


def test_v3_04_kms_specification_documents_0004():
    """docs/kms/02_POSTGRESQL_KMS_SPECIFICATION.md documents migration 0004."""
    spec_path = REPO_ROOT / "docs" / "kms" / "02_POSTGRESQL_KMS_SPECIFICATION.md"
    assert spec_path.is_file(), "02_POSTGRESQL_KMS_SPECIFICATION.md missing"
    content = spec_path.read_text(encoding="utf-8")
    assert "0004" in content, "Missing migration 0004 in 02_POSTGRESQL_KMS_SPECIFICATION.md"
    assert "image_candidates" in content, "Missing image_candidates in 02_POSTGRESQL_KMS_SPECIFICATION.md"


def test_v3_05_no_todo_or_fixme_in_round3_docs():
    """No TODO or FIXME markers in documentation files touched in Round 3."""
    files_to_check = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "DESIGN_DECISIONS.md",
        REPO_ROOT / "docs" / "IMAGE_CLASSIFICATION.md",
        REPO_ROOT / "docs" / "kms" / "02_POSTGRESQL_KMS_SPECIFICATION.md",
        REPO_ROOT / "docs" / "PROJECT_GUIDE.md",
    ]
    for p in files_to_check:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            assert "TODO" not in text, f"Found TODO in {p.name}"
            assert "FIXME" not in text, f"Found FIXME in {p.name}"
