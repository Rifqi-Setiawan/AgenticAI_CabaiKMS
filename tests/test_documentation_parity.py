"""Acceptance test suite for Stage S9: Documentation Parity Verification.

Contract source:
- reports/cabai-kms-jsonb/TECH_PLAN.md:
  * Line 526: Table 5 DoD & boundaries for S9 (Verifikasi End-to-End & Pemenuhan Kriteria A01-A28)
  * Line 556: Acceptance criterion A21 (test_readme_accurately_reflects_tested_state)
  * Section 11: Production Cutover Gates & Gate 4
- reports/cabai-kms-jsonb/PRD_CabaiKMS_JSONB.md:
  * Section I8: Validasi akhir dan README
  * Section J (Line 443): Kriteria penerimaan A21

Criteria covered:
- A21: README dan panduan teknis membedakan status rancangan, kemampuan teruji,
       aktivasi konfigurasi, dan deployment produksi.

Candidate documentation files:
- README.md
- docs/PROJECT_GUIDE.md

Test file:
- tests/test_documentation_parity.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
PROJECT_GUIDE_PATH = PROJECT_ROOT / "docs" / "PROJECT_GUIDE.md"
MIGRATION_GUIDE_PATH = PROJECT_ROOT / "docs" / "KMS_JSONB_MIGRATION.md"


# ============================================================================
# Criterion A21: Documentation Parity Checks
# ============================================================================


def test_a21_readme_accurately_reflects_tested_state():
    """Criterion A21: README accurately reflects tested JSONB document model and capabilities.

    Asserts that README.md documents:
    1. JSONB document storage model and KnowledgeDocument architecture.
    2. Staging and transactional commit capabilities.
    3. Plant variety and administrative habitat identity resolution.
    """
    assert README_PATH.exists(), f"README.md must exist at {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")

    # 1. Must document JSONB document storage capability
    has_jsonb_storage = bool(
        re.search(r"jsonb", content, re.IGNORECASE)
        and re.search(r"dokumen|document", content, re.IGNORECASE)
    )
    assert has_jsonb_storage, (
        "Criterion A21 failure: README.md does not document the tested JSONB document "
        "storage architecture and capabilities."
    )

    # 2. Must document transactional commit or staging lifecycle
    has_commit_lifecycle = bool(
        re.search(r"staging|stage", content, re.IGNORECASE)
        and re.search(r"commit", content, re.IGNORECASE)
    )
    assert has_commit_lifecycle, (
        "Criterion A21 failure: README.md does not document the document staging and "
        "transactional commit lifecycle."
    )

    # 3. Must document administrative habitat resolution
    has_habitat_identity = bool(
        re.search(r"habitat", content, re.IGNORECASE)
        and re.search(r"administratif|administrative", content, re.IGNORECASE)
    )
    assert has_habitat_identity, (
        "Criterion A21 failure: README.md does not document administrative habitat "
        "identity resolution."
    )


def test_a21_readme_links_migration_guide_and_retention_policy():
    """Criterion A21: README links to migration guide and explains retention policy.

    Asserts that README.md includes:
    1. A reference or link to docs/KMS_JSONB_MIGRATION.md.
    2. Explicit mention of legacy data retention or quarantine limits.
    """
    assert README_PATH.exists(), f"README.md must exist at {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")

    # 1. Must reference the migration guide
    assert "docs/KMS_JSONB_MIGRATION.md" in content or "KMS_JSONB_MIGRATION.md" in content, (
        "Criterion A21 failure: README.md does not reference or link to the migration guide "
        "(docs/KMS_JSONB_MIGRATION.md)."
    )

    # 2. Must state retention or quarantine boundaries
    has_quarantine_or_retention = bool(
        re.search(r"karantina|quarantine", content, re.IGNORECASE)
        or re.search(r"retensi|retention", content, re.IGNORECASE)
    )
    assert has_quarantine_or_retention, (
        "Criterion A21 failure: README.md does not describe data retention boundaries "
        "or quarantine policies."
    )


def test_a21_readme_distinguishes_tested_capabilities_from_production_activation():
    """Criterion A21: README distinguishes tested capabilities from production activation.

    Asserts that README.md documents:
    1. The configuration flag controlling KMS activation (e.g. kms_enabled or CABAI_KMS_ENABLED).
    2. The default state is disabled/false, ensuring features are not claimed active in production.
    """
    assert README_PATH.exists(), f"README.md must exist at {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")

    # 1. Must document kms_enabled configuration
    has_config_flag = bool(
        re.search(r"kms_enabled|cabai_kms_enabled", content, re.IGNORECASE)
    )
    assert has_config_flag, (
        "Criterion A21 failure: README.md does not document the kms_enabled / CABAI_KMS_ENABLED "
        "configuration flag."
    )

    # 2. Must document that default is inactive / False in production
    has_default_disabled = bool(
        re.search(r"false|nonaktif|disabled", content, re.IGNORECASE)
    )
    assert has_default_disabled, (
        "Criterion A21 failure: README.md does not specify that KMS document mode is "
        "disabled by default in production."
    )


def test_a21_project_guide_documents_jsonb_architecture_and_endpoints():
    """Criterion A21: PROJECT_GUIDE.md documents JSONB contracts, endpoints, and review actions.

    Asserts that docs/PROJECT_GUIDE.md documents:
    1. KnowledgeDocument contract and JSONB storage schema.
    2. V2 API endpoints (/runs/v2/stage, /runs/v2/{id}/commit, /documents).
    3. The 3 photo review actions (ASSIGN_EXISTING, CREATE_NEW_DOCUMENT, DISCARD).
    """
    assert PROJECT_GUIDE_PATH.exists(), f"docs/PROJECT_GUIDE.md must exist at {PROJECT_GUIDE_PATH}"
    content = PROJECT_GUIDE_PATH.read_text(encoding="utf-8")

    # 1. Must document KnowledgeDocument or JSONB document model
    has_document_contract = bool(
        re.search(r"knowledgedocument", content, re.IGNORECASE)
        or re.search(r"jsonb", content, re.IGNORECASE)
    )
    assert has_document_contract, (
        "Criterion A21 failure: docs/PROJECT_GUIDE.md does not document the KnowledgeDocument "
        "contract or JSONB document architecture."
    )

    # 2. Must document v2 endpoints
    has_v2_api = bool(
        re.search(r"/runs/v2", content)
        or re.search(r"POST /runs/v2/stage", content)
    )
    assert has_v2_api, (
        "Criterion A21 failure: docs/PROJECT_GUIDE.md does not document the v2 staging "
        "and transactional commit API endpoints."
    )

    # 3. Must document photo review actions
    has_photo_actions = (
        "ASSIGN_EXISTING" in content
        and "CREATE_NEW_DOCUMENT" in content
        and "DISCARD" in content
    )
    assert has_photo_actions, (
        "Criterion A21 failure: docs/PROJECT_GUIDE.md does not document the 3 photo review "
        "actions (ASSIGN_EXISTING, CREATE_NEW_DOCUMENT, DISCARD)."
    )


def test_a21_documentation_does_not_claim_untested_production_deployment():
    """Criterion A21: Documentation does not claim untested live production deployment.

    Ensures neither README.md nor docs/PROJECT_GUIDE.md falsely claims that
    the KMS JSONB document platform is deployed or running in production prior to
    formal Gate 4 cutover approval.
    """
    assert README_PATH.exists()
    assert PROJECT_GUIDE_PATH.exists()

    readme_content = README_PATH.read_text(encoding="utf-8")
    guide_content = PROJECT_GUIDE_PATH.read_text(encoding="utf-8")

    for doc_name, text in [("README.md", readme_content), ("docs/PROJECT_GUIDE.md", guide_content)]:
        false_deployment_claims = re.findall(
            r"(?:fitur|modul|sistem)\s+kms\s+(?:telah|sudah)\s+(?:aktif|berjalan|dideploy)\s+di\s+produksi",
            text,
            re.IGNORECASE,
        )
        assert len(false_deployment_claims) == 0, (
            f"Criterion A21 failure: {doc_name} makes premature claims of live production "
            f"deployment: {false_deployment_claims}"
        )
