"""Acceptance test suite for L6: Documentation parity for audit follow-up fixes (T-35..T-36).

Tests:
T-35: Architecture & guide docs contain new audit follow-up terms:
     - 0003 / schema_0003_attribute_changes
     - kms.document_attribute_changes
     - OVERWRITE_BLOCKED
     - UNIT_MISMATCH
     - Decision D2 / HUMAN_REVIEW protection
T-36: docs/AUDIT_FIX_REPORT.md contains an Addendum with:
     - Corrected backup size: 2.078.582 bytes
     - SHA-256 matching: 79baded1f052a32d5cc8d5a30d06805403b01f2f02bd9539da0700d719dfbb2f
     - Corrected resolve_review line reference (~707-712 or updated location)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "docs" / "kms" / "02_POSTGRESQL_KMS_SPECIFICATION.md"
PROJECT_GUIDE_PATH = PROJECT_ROOT / "docs" / "PROJECT_GUIDE.md"
JSONB_MIGRATION_PATH = PROJECT_ROOT / "docs" / "KMS_JSONB_MIGRATION.md"
AUDIT_REPORT_PATH = PROJECT_ROOT / "docs" / "AUDIT_FIX_REPORT.md"


def test_t35_docs_contain_new_key_terms():
    """T-35: Architecture and guide docs contain 0003, document_attribute_changes, OVERWRITE_BLOCKED, UNIT_MISMATCH, and D2."""
    assert SPEC_PATH.exists(), f"Spec must exist at {SPEC_PATH}"
    assert PROJECT_GUIDE_PATH.exists(), f"Project guide must exist at {PROJECT_GUIDE_PATH}"
    assert JSONB_MIGRATION_PATH.exists(), f"JSONB migration doc must exist at {JSONB_MIGRATION_PATH}"

    guide_text = PROJECT_GUIDE_PATH.read_text(encoding="utf-8")
    migration_text = JSONB_MIGRATION_PATH.read_text(encoding="utf-8")
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    combined_docs = f"{guide_text}\n{migration_text}\n{spec_text}"

    # 1. 0003 migration mentioned
    assert "0003" in combined_docs
    assert "document_attribute_changes" in combined_docs

    # 2. Review categories mentioned
    assert "OVERWRITE_BLOCKED" in combined_docs
    assert "UNIT_MISMATCH" in combined_docs

    # 3. Decision D2 / HUMAN_REVIEW protected mentioned
    assert "HUMAN_REVIEW" in combined_docs
    assert (
        "EXISTING_HUMAN_PROTECTED" in combined_docs
        or "dilindungi" in combined_docs.lower()
        or "protected" in combined_docs.lower()
    )


def test_t36_audit_report_contains_addendum_with_corrected_backup_size():
    """T-36: Addendum in docs/AUDIT_FIX_REPORT.md specifies 2.078.582 bytes and matching SHA-256."""
    assert AUDIT_REPORT_PATH.exists(), f"Audit report must exist at {AUDIT_REPORT_PATH}"
    content = AUDIT_REPORT_PATH.read_text(encoding="utf-8")

    # Must contain an Addendum section
    assert re.search(r"##\s*Addendum", content, re.IGNORECASE) is not None, (
        "docs/AUDIT_FIX_REPORT.md must contain an Addendum section."
    )

    # Must contain corrected byte count 2.078.582
    assert "2.078.582" in content or "2078582" in content, (
        "Addendum must correct the physical backup size to 2.078.582 bytes."
    )

    # Must verify SHA-256 remains identical
    assert "79baded1f052a32d5cc8d5a30d06805403b01f2f02bd9539da0700d719dfbb2f" in content, (
        "Addendum must verify SHA-256 remains 79baded1f052a32d5cc8d5a30d06805403b01f2f02bd9539da0700d719dfbb2f."
    )

    # Must note the resolve_review line shift
    assert "resolve_review" in content
