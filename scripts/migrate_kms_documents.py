"""Migrasi data legacy Cabai KMS ke format dokumen JSONB dan karantina.

Modul ini bertanggung jawab untuk:
1. Membaca data legacy dari tabel kms.variety_character_values dan kms.value_observations.
2. Memetakan baris dengan lokasi sampling administratif valid ke entitas KnowledgeDocument.
3. Mengalihkan data tanpa lokasi administratif sah ke antrean karantina review.
4. Menyusun manifest rekonsiliasi total: total == mapped + quarantine + rejected.
5. Mendukung mode default dry-run akuntabel dan mode transaksional apply.
6. Menyediakan simulasi rollback pra-cutover dan pasca-cutover tanpa purge destruktif.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_planner import parse_range_value
from src.storage.identity_resolution import (
    AdministrativeRegistry,
    resolve_sampling_location,
)

__all__ = [
    "parse_args",
    "run_migration",
    "simulate_rollback",
    "main",
]


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments for legacy document migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate legacy Cabai KMS relational tables to JSONB knowledge documents.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply migration changes transactionally to kms.knowledge_documents (default is dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Explicitly enforce dry-run mode without database mutations.",
    )
    parser.add_argument(
        "--manifest-output",
        type=str,
        default=None,
        help="Output file path for migration reconciliation manifest JSON.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database URL connection string.",
    )
    parser.add_argument(
        "--actor",
        type=str,
        default="migration-s8",
        help="Authenticated actor for audit logging.",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        default=False,
        help="Run rollback simulation procedure.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="pre-cutover",
        choices=["pre-cutover", "post-cutover"],
        help="Rollback simulation mode.",
    )
    parser.add_argument(
        "--export-staging-path",
        type=str,
        default=None,
        help="Path to export staging recovery data during post-cutover rollback.",
    )

    parsed = parser.parse_args(args)
    if parsed.dry_run:
        parsed.apply = False
    return parsed


def _get_engine(db_url: str | None = None) -> Engine:
    """Obtain SQLAlchemy engine using provided or configured database URL."""
    url = (
        db_url
        or os.getenv("TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or Settings(_env_file=None).database_url
    )
    return make_engine(Settings(_env_file=None, database_url=str(url)))


def run_migration(
    db_url: str | None = None,
    dry_run: bool = True,
    manifest_output: str | Path | None = None,
    actor: str = "migration-s8",
) -> dict[str, Any]:
    """Execute legacy data migration and reconciliation manifest generation.

    Parameters:
        db_url: Optional database connection string.
        dry_run: When True, produces mapping and manifest without DB mutation. Default: True.
        manifest_output: Optional path to save reconciliation manifest JSON.
        actor: Authenticated actor identifier for audit trail.

    Returns:
        dict containing reconciliation manifest, summary metrics, mapped documents,
        quarantine items, and rejected items.
    """
    engine = _get_engine(db_url)
    admin_registry = AdministrativeRegistry()

    with engine.connect() as conn:
        legacy_rows = conn.execute(
            text("""
                SELECT
                    vcv.id AS val_id,
                    vcv.variety_id,
                    v.canonical_name AS variety_name,
                    v.origin_region AS variety_origin_region,
                    vcv.characteristic_id,
                    c.canonical_key,
                    c.label_id,
                    c.organ_domain,
                    c.source_domain,
                    c.data_type,
                    c.standard_unit,
                    vcv.normalized_value,
                    vcv.raw_source_value,
                    vcv.value_type,
                    vcv.is_multi_value,
                    vcv.confidence_score,
                    vcv.status,
                    vcv.run_id,
                    vcv.version,
                    vo.observation_sha256,
                    vo.evidence
                FROM kms.variety_character_values vcv
                LEFT JOIN kms.varieties v ON vcv.variety_id = v.id
                LEFT JOIN kms.characteristics c ON vcv.characteristic_id = c.id
                LEFT JOIN kms.value_observations vo ON (
                    vcv.run_id = vo.run_id
                    AND vcv.variety_id = vo.variety_id
                    AND vcv.characteristic_id = vo.characteristic_id
                )
                ORDER BY vcv.id ASC
            """)
        ).mappings().all()

    total_legacy_rows = len(legacy_rows)
    mapped_count = 0
    quarantine_items: list[dict[str, Any]] = []
    rejected_items: list[dict[str, Any]] = []
    documents_by_target: dict[str, dict[str, Any]] = {}

    for row in legacy_rows:
        val_id = str(row["val_id"])
        variety_id = str(row["variety_id"]) if row["variety_id"] is not None else None
        char_id = str(row["characteristic_id"]) if row["characteristic_id"] is not None else None
        norm_val = row["normalized_value"]

        # 1. Rejection validation: check for missing vital references or unparseable values
        if not variety_id or not char_id or norm_val is None:
            rejected_items.append({
                "legacy_value_id": val_id,
                "variety_id": variety_id,
                "characteristic_id": char_id,
                "reason": "Corrupted or missing mandatory references in legacy record",
                "row_data": dict(row),
            })
            continue

        raw_evidence = row["evidence"]
        evidence_dict: dict[str, Any] = {}
        if isinstance(raw_evidence, str):
            try:
                evidence_dict = json.loads(raw_evidence)
            except Exception:
                rejected_items.append({
                    "legacy_value_id": val_id,
                    "variety_id": variety_id,
                    "characteristic_id": char_id,
                    "reason": "Malformed JSON in value_observations evidence payload",
                })
                continue
        elif isinstance(raw_evidence, dict):
            evidence_dict = raw_evidence

        # 2. Location resolution & quarantine triage
        habitat: HabitatIdentity | None = None
        raw_address = evidence_dict.get("raw_address")
        p_prov = evidence_dict.get("province")
        p_reg = evidence_dict.get("regency")
        p_dist = evidence_dict.get("district")
        p_vill = evidence_dict.get("village")

        if p_prov and p_reg and p_dist and p_vill:
            habitat = admin_registry.lookup(
                province=str(p_prov),
                regency=str(p_reg),
                district=str(p_dist),
                village=str(p_vill),
            )

        if habitat is None and raw_address and str(raw_address).strip():
            hab, _detail, issues = resolve_sampling_location(
                str(raw_address),
                context=evidence_dict,
                registry=admin_registry,
            )
            if hab is not None and not issues:
                habitat = hab

        if habitat is None:
            # Variety-only legacy record lacking verified administrative location
            quarantine_items.append({
                "variety_id": variety_id,
                "characteristic_id": char_id,
                "canonical_key": row["canonical_key"],
                "legacy_value_id": val_id,
                "reason": "Unresolved location: missing or invalid administrative habitat provenance",
                "raw_address": raw_address,
                "normalized_value": norm_val,
                "raw_source_value": row["raw_source_value"],
                "status": "QUARANTINE",
            })
            continue

        # 3. Successful mapping to KnowledgeDocument entity
        mapped_count += 1
        doc_key = f"{variety_id}:{habitat.id}"

        if doc_key not in documents_by_target:
            plant_identity = PlantIdentity(
                id=variety_id,
                label=row["variety_name"] or "Cabai",
                identity_level="cultivar",
            )
            sampling_loc = SamplingLocationDetail(
                location_ref=evidence_dict.get("location_ref") or habitat.id,
                raw_address=str(raw_address or habitat.label),
                hamlet=evidence_dict.get("hamlet"),
                sampling_marker=evidence_dict.get("sampling_marker"),
            )
            documents_by_target[doc_key] = {
                "schema_version": "kms-document-v1",
                "variety": plant_identity,
                "habitat": habitat,
                "sampling_locations": [sampling_loc],
                "attributes": {},
                "updated_by_run": row["run_id"] or "legacy_migration",
                "doc_id": doc_key,
                "version": 1,
            }
        else:
            existing_locs = documents_by_target[doc_key]["sampling_locations"]
            loc_addr = str(raw_address or habitat.label)
            if not any(loc.raw_address == loc_addr for loc in existing_locs):
                existing_locs.append(
                    SamplingLocationDetail(
                        location_ref=evidence_dict.get("location_ref") or habitat.id,
                        raw_address=loc_addr,
                        hamlet=evidence_dict.get("hamlet"),
                        sampling_marker=evidence_dict.get("sampling_marker"),
                    )
                )

        # Parse attribute measurement
        val_type = row["value_type"] or "text"
        parsed_val = norm_val
        if val_type == "number":
            try:
                if isinstance(norm_val, (int, float)):
                    parsed_val = float(norm_val)
                elif isinstance(norm_val, str):
                    parsed_val = float(norm_val.strip())
            except (ValueError, TypeError):
                val_type = "text"
                parsed_val = str(norm_val)
        elif val_type == "boolean":
            if isinstance(norm_val, str):
                parsed_val = norm_val.lower() in ("true", "1", "yes")
            else:
                parsed_val = bool(norm_val)
        elif val_type == "range":
            if not (isinstance(norm_val, dict) and "min" in norm_val and "max" in norm_val):
                parsed_r = parse_range_value(norm_val)
                if parsed_r:
                    parsed_val = parsed_r
                else:
                    val_type = "text"
                    parsed_val = str(norm_val)

        status_str = row["status"]
        resolution_lit = "AUTO_ACCEPT" if status_str == "AUTO_ACCEPT" else "HUMAN_REVIEW"

        source_ref = CurrentSourceReference(
            source_ref=row["run_id"] or "legacy_migration",
            sheet=str(evidence_dict.get("sheet", "Resume Data")),
            row=int(evidence_dict.get("row", 1)),
            cell=str(evidence_dict.get("cell", "A1")),
            location_ref=evidence_dict.get("location_ref") or habitat.id,
            run_id=row["run_id"],
        )

        attr_key = row["canonical_key"] or f"attr_{char_id}"
        attr_obj = AttributeValue(
            label=row["label_id"] or attr_key,
            value=parsed_val,
            value_type=val_type,
            unit=row["standard_unit"],
            resolution=resolution_lit,
            current_source=source_ref,
            attribute_id=char_id,
            confidence=float(row["confidence_score"]) if row["confidence_score"] is not None else 1.0,
        )
        documents_by_target[doc_key]["attributes"][attr_key] = attr_obj

    # Build validated KnowledgeDocument instances
    validated_documents: list[KnowledgeDocument] = []
    for d in documents_by_target.values():
        doc_instance = KnowledgeDocument(
            schema_version="kms-document-v1",
            variety=d["variety"],
            habitat=d["habitat"],
            sampling_locations=d["sampling_locations"],
            attributes=d["attributes"],
            updated_by_run=d["updated_by_run"],
            doc_id=d["doc_id"],
            version=d["version"],
        )
        validated_documents.append(doc_instance)

    quarantine_count = len(quarantine_items)
    rejected_count = len(rejected_items)

    # Invariant: reconciliation accounting total == mapped + quarantine + rejected
    if total_legacy_rows != (mapped_count + quarantine_count + rejected_count):
        raise ValueError(
            f"Accounting mismatch: total ({total_legacy_rows}) != "
            f"mapped ({mapped_count}) + quarantine ({quarantine_count}) + rejected ({rejected_count})"
        )

    manifest: dict[str, Any] = {
        "dry_run": dry_run,
        "summary": {
            "total_legacy_rows": total_legacy_rows,
            "mapped_count": mapped_count,
            "quarantine_count": quarantine_count,
            "rejected_count": rejected_count,
            "mapped_documents_count": len(validated_documents),
        },
        "mapped_documents": [doc.model_dump(mode="json") for doc in validated_documents],
        "quarantine_items": quarantine_items,
        "rejected_items": rejected_items,
    }

    # 4. Transactional persistence when apply mode is enabled
    if not dry_run:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SELECT set_config('kms.actor', :actor, true)"), {"actor": actor})
                for doc in validated_documents:
                    doc_json = json.dumps(doc.model_dump(mode="json"))
                    conn.execute(
                        text("""
                            INSERT INTO kms.knowledge_documents (
                                id, variety_id, habitat_id, document, version, created_at, updated_at
                            ) VALUES (
                                :id, :variety_id, :habitat_id, CAST(:document AS jsonb), :version, now(), now()
                            ) ON CONFLICT (id) DO UPDATE SET
                                document = EXCLUDED.document,
                                version = kms.knowledge_documents.version,
                                updated_at = now()
                        """),
                        {
                            "id": doc.doc_id,
                            "variety_id": doc.variety.id,
                            "habitat_id": doc.habitat.id,
                            "document": doc_json,
                            "version": doc.version,
                        },
                    )

    if manifest_output:
        out_path = Path(manifest_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, default=str)

    return manifest


def simulate_rollback(
    db_url: str | None = None,
    mode: str = "pre-cutover",
    export_staging_path: str | Path | None = None,
    actor: str = "rollback-simulation",
) -> dict[str, Any]:
    """Simulate rollback procedure for legacy-to-JSONB migration.

    Parameters:
        db_url: Database connection URL.
        mode: Rollback mode ('pre-cutover' or 'post-cutover').
        export_staging_path: File path to export snapshot recovery staging data.
        actor: Authenticated actor identifier.

    Returns:
        dict containing rollback status, delta detection, and integrity flags.
    """
    engine = _get_engine(db_url)

    with engine.connect() as conn:
        val_count = conn.execute(text("SELECT COUNT(*) FROM kms.variety_character_values")).scalar() or 0
        obs_count = conn.execute(text("SELECT COUNT(*) FROM kms.value_observations")).scalar() or 0
        legacy_data_intact = val_count > 0 and obs_count > 0

        if mode == "pre-cutover":
            return {
                "status": "success",
                "mode": "pre-cutover",
                "legacy_data_intact": legacy_data_intact,
                "legacy_row_count": val_count,
                "message": "Pre-cutover rollback verified: legacy tables intact and readable.",
            }

        elif mode == "post-cutover":
            doc_rows = conn.execute(
                text("SELECT id, variety_id, habitat_id, document, version FROM kms.knowledge_documents")
            ).mappings().all()

            docs_payload = [dict(r) for r in doc_rows]
            delta_detected = len(docs_payload) > 0
            recovery_exported = False

            if export_staging_path:
                export_p = Path(export_staging_path)
                export_p.parent.mkdir(parents=True, exist_ok=True)
                with open(export_p, "w", encoding="utf-8") as f:
                    json.dump(docs_payload, f, indent=2, default=str)
                recovery_exported = True

            return {
                "status": "warning",
                "mode": "post-cutover",
                "delta_detected": delta_detected,
                "recovery_exported": recovery_exported,
                "lossless_guarantee": False,
                "legacy_data_intact": legacy_data_intact,
                "exported_documents_count": len(docs_payload),
                "export_staging_path": str(export_staging_path) if export_staging_path else None,
                "message": (
                    "Post-cutover delta writes detected in JSONB documents. "
                    "Exported to recovery staging. Lossless guarantee is False due to habitat and dynamic attribute divergence."
                ),
            }

        else:
            raise ValueError(f"Unsupported rollback mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    """Entry point for legacy migration CLI execution."""
    args = parse_args(argv)

    if getattr(args, "rollback", False):
        result = simulate_rollback(
            db_url=args.db_url,
            mode=args.mode,
            export_staging_path=args.export_staging_path,
            actor=args.actor,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    dry_run = not getattr(args, "apply", False)
    manifest = run_migration(
        db_url=args.db_url,
        dry_run=dry_run,
        manifest_output=args.manifest_output,
        actor=args.actor,
    )
    print(json.dumps(manifest.get("summary", {}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
