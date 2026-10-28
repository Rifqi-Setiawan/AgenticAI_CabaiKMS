"""Additive DDL and JSONB document repository for CabaiKMS."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.storage.contracts import canonical_json, digest_json
from src.storage.db import transaction
from src.storage.document_contracts import (
    AdministrativePath,
    AttributeValue,
    CommitReceipt,
    DocumentDraft,
    HabitatIdentity,
    KnowledgeDocument,
    MediaReference,
    OverwriteDecision,
    PhotoMismatchDecision,
    PlantIdentity,
    make_unknown_habitat,
    validate_document,
)
from src.storage.attribute_policy import AttributePolicy
from src.storage.errors import Conflict, InvalidState, NotFound
from src.storage.models import AcquisitionRun

__all__ = ["DocumentRepository", "context"]


def context(session: Session, actor: str, run_id: str = "") -> None:
    """Set PostgreSQL session settings for audit trail."""
    if not actor.strip():
        raise InvalidState("Authenticated actor required.")
    session.execute(
        text("SELECT set_config('kms.actor', :a, true), set_config('kms.run_id', :r, true)"),
        {"a": actor, "r": run_id},
    )


class DocumentRepository:
    """Repository managing dynamic JSONB documents, staging, and optimistic atomic commit."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _lock(session: Session, run_id: str) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "run:" + run_id},
        )

    @staticmethod
    def _archive_draft(session: Session, run: AcquisitionRun, actor: str) -> None:
        session.execute(
            text("""
                INSERT INTO kms.draft_revisions
                (run_id, revision, payload_sha256, payload, base_versions, actor)
                VALUES (:r, :v, :h, CAST(:p AS jsonb), CAST(:b AS jsonb), :a)
            """),
            {
                "r": run.run_id,
                "v": run.revision,
                "h": run.payload_sha256,
                "p": canonical_json(run.draft_payload),
                "b": canonical_json(run.base_versions),
                "a": actor,
            },
        )

    @staticmethod
    def _run_summary(run: AcquisitionRun) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "status": run.status,
            "revision": run.revision,
            "payload_sha256": run.payload_sha256,
            "receipt": run.receipt,
        }

    @staticmethod
    def _record_attribute_change(
        session: Session,
        doc_id: str,
        attribute_id: str,
        old_val: Any,
        new_val: Any,
        run_id: str,
        actor: str,
    ) -> None:
        """Record attribute change to append-only kms.document_attribute_changes ledger."""
        session.execute(
            text("""
                INSERT INTO kms.document_attribute_changes
                (doc_id, attribute_id, old_value, new_value, run_id, actor)
                VALUES (:doc_id, :attr_id, CAST(:old_val AS jsonb), CAST(:new_val AS jsonb), :run_id, :actor)
            """),
            {
                "doc_id": doc_id,
                "attr_id": attribute_id,
                "old_val": canonical_json(old_val),
                "new_val": canonical_json(new_val),
                "run_id": run_id,
                "actor": actor,
            },
        )

    def register_source(
        self, sha256: str, uri: str, size: int, *, actor: str
    ) -> dict[str, Any]:
        """Register source artifact in kms.source_artifacts."""
        with transaction(self.engine) as session:
            context(session, actor)
            session.execute(
                text("""
                    INSERT INTO kms.source_artifacts (sha256, storage_uri, file_size)
                    VALUES (:h, :u, :s) ON CONFLICT DO NOTHING
                """),
                {"h": sha256, "u": uri, "s": size},
            )
            row = session.execute(
                text(
                    "SELECT sha256, storage_uri, file_size FROM kms.source_artifacts WHERE sha256 = :h"
                ),
                {"h": sha256},
            ).mappings().one()
            if row["file_size"] != size:
                raise Conflict("Source checksum collision or corrupt registry.")
            return dict(row)

    def get_source(self, sha256: str) -> dict[str, Any]:
        """Retrieve source artifact metadata."""
        with Session(self.engine) as session:
            row = session.execute(
                text("SELECT * FROM kms.source_artifacts WHERE sha256 = :h"),
                {"h": sha256},
            ).mappings().first()
            if row is None:
                raise NotFound("Source artifact not found.")
            return dict(row)

    def stage(
        self, draft: DocumentDraft, *, expected_revision: int, actor: str
    ) -> dict[str, Any]:
        """Stage or update a DocumentDraft envelope."""
        payload = draft.model_dump(mode="json")
        checksum = digest_json(payload)
        with transaction(self.engine) as session:
            context(session, actor, draft.run_id)
            self._lock(session, draft.run_id)
            existing = session.get(AcquisitionRun, draft.run_id)
            if existing is not None:
                if existing.payload_sha256 == checksum:
                    return self._run_summary(existing)
                if existing.status == "COMMITTED":
                    raise Conflict("Run already committed. Create a new amendment run_id.")
                if existing.revision != expected_revision:
                    raise Conflict("Draft revision changed. Reload the saved draft before editing.")
                previous = DocumentDraft.model_validate(existing.draft_payload)
                for field in (
                    "source_filename",
                    "file_sha256",
                    "source_uri",
                    "source_scope",
                    "schema_version",
                    "template_hash",
                    "config_fingerprint",
                ):
                    if getattr(previous, field) != getattr(draft, field):
                        raise Conflict("Source/schema/config/run identity cannot change inside one run.")
                new_reviews = {review.item_id: review for review in draft.reviews}
                if set(new_reviews) != {review.item_id for review in previous.reviews}:
                    raise Conflict("Review membership cannot change inside an existing run.")
                for review in previous.reviews:
                    incoming = new_reviews[review.item_id]
                    if review.status != "pending" and incoming.model_dump(mode="json") != review.model_dump(mode="json"):
                        raise Conflict("A persisted review cannot be reverted.")

                auto_accepted = sum(
                    1
                    for d in draft.documents.values()
                    for a in d.attributes.values()
                    if a.resolution == "AUTO_ACCEPT"
                )
                reviewed = sum(
                    1
                    for d in draft.documents.values()
                    for a in d.attributes.values()
                    if a.resolution != "AUTO_ACCEPT"
                ) + len([r for r in draft.reviews if r.status != "pending"])
                total_attrs = max(
                    len(draft.reviews) + sum(len(d.attributes) for d in draft.documents.values()),
                    auto_accepted + reviewed,
                )

                existing.revision += 1
                existing.draft_payload = payload
                existing.payload_sha256 = checksum
                existing.auto_accepted_count = auto_accepted
                existing.reviewed_count = reviewed
                existing.total_attributes = total_attrs

                merged_bv = dict(existing.base_versions)
                if draft.base_versions:
                    merged_bv.update(draft.base_versions)
                existing.base_versions = merged_bv

                session.flush()
                self._archive_draft(session, existing, actor)
                return self._run_summary(existing)

            if expected_revision != 0:
                raise Conflict("New runs must use expected_revision=0.")
            if draft.source_uri:
                source = session.execute(
                    text("SELECT storage_uri FROM kms.source_artifacts WHERE sha256 = :h"),
                    {"h": draft.file_sha256},
                ).scalar_one_or_none()
                if source != draft.source_uri:
                    raise InvalidState("Source artifact is not registered, or checksum/URI mismatch.")

            auto_accepted = sum(
                1
                for d in draft.documents.values()
                for a in d.attributes.values()
                if a.resolution == "AUTO_ACCEPT"
            )
            reviewed = sum(
                1
                for d in draft.documents.values()
                for a in d.attributes.values()
                if a.resolution != "AUTO_ACCEPT"
            ) + len([r for r in draft.reviews if r.status != "pending"])
            total_attrs = max(
                len(draft.reviews) + sum(len(d.attributes) for d in draft.documents.values()),
                auto_accepted + reviewed,
            )

            run = AcquisitionRun(
                run_id=draft.run_id,
                source_filename=draft.source_filename,
                file_sha256=draft.file_sha256,
                source_uri=draft.source_uri,
                schema_version=draft.schema_version,
                template_hash=draft.template_hash,
                config_fingerprint=draft.config_fingerprint,
                total_attributes=total_attrs,
                auto_accepted_count=auto_accepted,
                reviewed_count=reviewed,
                status="STAGED",
                revision=1,
                payload_sha256=checksum,
                draft_payload=payload,
                base_versions=draft.base_versions or {},
            )
            session.add(run)
            session.flush()
            self._archive_draft(session, run, actor)
            return self._run_summary(run)

    def commit(
        self, run_id: str, revision: int, payload_sha256: str, *, actor: str
    ) -> CommitReceipt:
        """Atomically commit a staged DocumentDraft into kms.knowledge_documents."""
        with transaction(self.engine) as session:
            context(session, actor, run_id)
            self._lock(session, run_id)
            run = session.get(AcquisitionRun, run_id)
            if run is None:
                raise NotFound("Run not found.")
            if run.revision != revision or run.payload_sha256 != payload_sha256:
                raise Conflict("Commit revision/digest no longer matches the reviewed draft.")
            if run.status == "COMMITTED":
                receipt_dict = copy.deepcopy(run.receipt)
                if isinstance(receipt_dict, dict):
                    receipt_dict["replayed"] = True
                    return CommitReceipt.model_validate(receipt_dict)
                return receipt_dict

            try:
                draft = DocumentDraft.model_validate(run.draft_payload)
            except Exception as e:
                from pydantic import ValidationError
                if isinstance(e, ValidationError):
                    attr_err = ""
                    for err in e.errors():
                        loc_str = ".".join(str(x) for x in err.get("loc", []))
                        if "attributes" in loc_str:
                            segments = loc_str.split(".")
                            idx = segments.index("attributes")
                            if idx + 1 < len(segments):
                                attr_err = f" in attribute '{segments[idx+1]}'"
                                break
                    raise InvalidState(f"Invalid draft payload{attr_err}: {e}")
                raise
            if any(review.status == "pending" for review in draft.reviews):
                raise Conflict("Resolve every pending review before committing.")
            if not draft.source_uri:
                raise InvalidState("Archive the original source before committing a new run.")

            sorted_keys = sorted(draft.documents.keys())

            # Advisory lock per document to serialize concurrent writers deterministically
            for doc_key in sorted_keys:
                session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                    {"k": "doc:" + doc_key},
                )

            # Optimistic concurrency check against database versions
            for doc_key in sorted_keys:
                row = session.execute(
                    text("SELECT version FROM kms.knowledge_documents WHERE id = :id"),
                    {"id": doc_key},
                ).mappings().first()
                current_ver = row["version"] if row is not None else 0
                expected_ver = run.base_versions.get(
                    doc_key, draft.base_versions.get(doc_key, 0)
                )
                if current_ver != expected_ver:
                    raise Conflict(
                        f"Document {doc_key} base version {expected_ver} does not match database version {current_ver}."
                    )

            created_count = 0
            updated_count = 0
            attributes_committed = 0
            prohibited_history_keys = (
                "previous_value",
                "previous_values",
                "observations",
                "history",
                "raw_history",
            )

            for doc_key in sorted_keys:
                incoming_doc = draft.documents[doc_key]
                incoming_dict = incoming_doc.model_dump(mode="json")
                row = session.execute(
                    text("SELECT version, document FROM kms.knowledge_documents WHERE id = :id"),
                    {"id": doc_key},
                ).mappings().first()
                current_ver = row["version"] if row is not None else 0
                expected_ver = run.base_versions.get(
                    doc_key, draft.base_versions.get(doc_key, 0)
                )

                if current_ver == 0:
                    doc_data = copy.deepcopy(incoming_dict)
                    doc_data["version"] = 1
                    doc_data["updated_by_run"] = run_id
                    doc_data["doc_id"] = doc_key

                    for p in prohibited_history_keys:
                        doc_data.pop(p, None)
                    for attr in doc_data.get("attributes", {}).values():
                        if isinstance(attr, dict):
                            for p in prohibited_history_keys:
                                attr.pop(p, None)

                    session.execute(
                        text("""
                            INSERT INTO kms.knowledge_documents
                            (id, variety_id, habitat_id, document, version, created_at, updated_at)
                            VALUES (:id, :v_id, :h_id, CAST(:doc AS jsonb), 1, now(), now())
                        """),
                        {
                            "id": doc_key,
                            "v_id": incoming_doc.variety.id,
                            "h_id": incoming_doc.habitat.id,
                            "doc": canonical_json(doc_data),
                        },
                    )
                    created_count += 1
                    attributes_committed += len(doc_data.get("attributes", {}))
                else:
                    existing_doc = row["document"]
                    new_ver = current_ver + 1

                    # Merge attributes: apply can_overwrite policy guard (A10)
                    merged_attrs = dict(existing_doc.get("attributes", {}))
                    policy = AttributePolicy()
                    approved_overrides = {
                        (r.target_document_key, (r.payload or {}).get("attribute_id"))
                        for r in draft.reviews
                        if r.category in ("OVERWRITE_BLOCKED", "UNIT_MISMATCH")
                        and r.status in ("approved", "revised")
                        and r.target_document_key
                        and (r.payload or {}).get("attribute_id")
                    }
                    for attr_id, inc_dict in incoming_dict.get("attributes", {}).items():
                        if attr_id in merged_attrs:
                            exist_dict = merged_attrs[attr_id]
                            is_approved_override = (doc_key, attr_id) in approved_overrides
                            if is_approved_override:
                                can_ow = True
                            else:
                                exist_av = AttributeValue.model_validate(exist_dict)
                                inc_av = AttributeValue.model_validate(inc_dict)
                                block_reason = policy.overwrite_block_reason(exist_av, inc_av)
                                if block_reason is not None:
                                    raise Conflict(
                                        f"OVERWRITE_BLOCKED at commit for document '{doc_key}', attribute '{attr_id}': "
                                        f"{block_reason}. Resolve review or re-stage draft."
                                    )
                                can_ow = True

                            if can_ow:
                                if exist_dict != inc_dict:
                                    self._record_attribute_change(
                                        session,
                                        doc_id=doc_key,
                                        attribute_id=attr_id,
                                        old_val=exist_dict,
                                        new_val=inc_dict,
                                        run_id=run_id,
                                        actor=actor,
                                    )
                                merged_attrs[attr_id] = inc_dict
                            else:
                                # Guard: retain existing attribute intact
                                pass
                        else:
                            # Additional new attribute on existing document
                            merged_attrs[attr_id] = inc_dict

                    # Merge sampling locations
                    loc_map = {
                        loc.get("location_ref"): loc
                        for loc in existing_doc.get("sampling_locations", [])
                        if loc.get("location_ref")
                    }
                    for loc in incoming_dict.get("sampling_locations", []):
                        ref = loc.get("location_ref")
                        if ref:
                            loc_map[ref] = loc
                    merged_locs = list(loc_map.values())

                    # Merge media refs
                    media_map = {
                        m.get("asset_id"): m
                        for m in existing_doc.get("media_refs", [])
                        if m.get("asset_id")
                    }
                    for m in incoming_dict.get("media_refs", []):
                        aid = m.get("asset_id")
                        if aid:
                            media_map[aid] = m
                    merged_media = list(media_map.values())

                    doc_data = copy.deepcopy(existing_doc)
                    doc_data["schema_version"] = incoming_dict.get(
                        "schema_version", existing_doc.get("schema_version", "kms-document-v1")
                    )
                    doc_data["variety"] = incoming_dict.get("variety", existing_doc.get("variety"))
                    doc_data["habitat"] = incoming_dict.get("habitat", existing_doc.get("habitat"))
                    doc_data["sampling_locations"] = merged_locs
                    doc_data["attributes"] = merged_attrs
                    doc_data["media_refs"] = merged_media
                    doc_data["updated_by_run"] = run_id
                    doc_data["version"] = new_ver
                    doc_data["doc_id"] = doc_key

                    for p in prohibited_history_keys:
                        doc_data.pop(p, None)
                    for attr in doc_data.get("attributes", {}).values():
                        if isinstance(attr, dict):
                            for p in prohibited_history_keys:
                                attr.pop(p, None)

                    res = session.execute(
                        text("""
                            UPDATE kms.knowledge_documents
                            SET document = CAST(:doc AS jsonb), version = :new_v, updated_at = now()
                            WHERE id = :id AND version = :exp_v
                        """),
                        {
                            "id": doc_key,
                            "doc": canonical_json(doc_data),
                            "new_v": new_ver,
                            "exp_v": current_ver,
                        },
                    )
                    if res.rowcount != 1:
                        raise Conflict(f"Concurrent update conflict on document {doc_key}.")
                    updated_count += 1
                    attributes_committed += len(doc_data.get("attributes", {}))

            # Record single sanitized outbox event
            outbox_payload = {
                "run_id": run_id,
                "revision": revision,
                "payload_sha256": payload_sha256,
                "documents_committed": sorted_keys,
            }
            session.execute(
                text("""
                    INSERT INTO kms.outbox_events (run_id, event_type, payload)
                    VALUES (:r, 'KMS_DOCUMENT_COMMITTED', CAST(:p AS jsonb))
                """),
                {"r": run_id, "p": canonical_json(outbox_payload)},
            )

            receipt = CommitReceipt(
                run_id=run_id,
                revision=revision,
                documents_created=created_count,
                documents_updated=updated_count,
                documents_unchanged=0,
                reviews_resolved=len([r for r in draft.reviews if r.status != "pending"]),
                attributes_committed=attributes_committed,
                media_linked=sum(len(d.media_refs) for d in draft.documents.values()),
                replayed=False,
                committed_at=datetime.now(timezone.utc),
                committed_documents_count=len(draft.documents),
            )
            run.status = "COMMITTED"
            run.receipt = receipt.model_dump(mode="json")
            run.committed_at = receipt.committed_at
            session.flush()
            return receipt

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Retrieve a KnowledgeDocument row by deterministic document key."""
        with Session(self.engine) as session:
            row = session.execute(
                text("SELECT id, document, version FROM kms.knowledge_documents WHERE id = :id"),
                {"id": doc_id},
            ).mappings().first()
            if row is None:
                return None
            doc = dict(row["document"])
            doc["id"] = row["id"]
            doc["doc_id"] = row["id"]
            doc["version"] = row["version"]
            return doc

    def list_documents(
        self,
        *,
        variety_id: str | None = None,
        habitat_id: str | None = None,
        habitat_unknown: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query committed KnowledgeDocuments with optional filtering and pagination."""
        query = "SELECT id, document, version FROM kms.knowledge_documents WHERE 1=1"
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if variety_id:
            query += " AND variety_id = :variety_id"
            params["variety_id"] = variety_id
        if habitat_id:
            query += " AND habitat_id = :habitat_id"
            params["habitat_id"] = habitat_id
        if habitat_unknown is not None:
            if habitat_unknown:
                query += " AND (document->>'habitat_unknown' = 'true' OR habitat_id = 'habitat_unknown')"
            else:
                query += " AND (document->>'habitat_unknown' IS NULL OR document->>'habitat_unknown' = 'false') AND habitat_id != 'habitat_unknown'"
        query += " ORDER BY id LIMIT :limit OFFSET :offset"

        with Session(self.engine) as session:
            rows = session.execute(text(query), params).mappings().all()
            result = []
            for row in rows:
                doc = dict(row["document"])
                doc["id"] = row["id"]
                doc["doc_id"] = row["id"]
                doc["version"] = row["version"]
                result.append(doc)
            return result

    def resolve_review(
        self,
        run_id: str,
        item_id: str,
        decision: dict[str, Any] | PhotoMismatchDecision | OverwriteDecision,
        *,
        actor: str,
        actor_role: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a pending review item in a staged DocumentDraft envelope."""
        if hasattr(decision, "model_dump"):
            dec_dict = decision.model_dump(mode="json")
        else:
            dec_dict = dict(decision)

        action = dec_dict.get("action")
        status = dec_dict.get("status")
        notes = dec_dict.get("notes")

        if not action and not status:
            raise InvalidState("decision requires action or status")

        with transaction(self.engine) as session:
            context(session, actor, run_id)
            self._lock(session, run_id)
            run = session.get(AcquisitionRun, run_id)
            if run is None:
                raise NotFound(f"Run {run_id} not found.")
            if run.status == "COMMITTED":
                raise Conflict("Run already committed. Create a new amendment run_id.")

            draft = DocumentDraft.model_validate(run.draft_payload)
            target_item = next((r for r in draft.reviews if r.item_id == item_id), None)
            if target_item is None:
                raise NotFound(f"Review item {item_id} not found in run {run_id}.")
            if target_item.status != "pending":
                raise Conflict(f"Review item {item_id} is already resolved ({target_item.status}).")

            if target_item.category in ("OVERWRITE_BLOCKED", "UNIT_MISMATCH"):
                if action not in ("KEEP_EXISTING", "APPLY_INCOMING", "REVISE"):
                    raise InvalidState(
                        f"Unknown action '{action}' for {target_item.category}. Must be KEEP_EXISTING, APPLY_INCOMING, or REVISE."
                    )

                doc_key = target_item.target_document_key
                attr_id = target_item.payload.get("attribute_id")
                new_attr_dict = target_item.payload.get("new_attribute")
                old_attr_dict = target_item.payload.get("old_attribute")

                if action in ("APPLY_INCOMING", "REVISE"):
                    if action == "APPLY_INCOMING" and target_item.category == "UNIT_MISMATCH":
                        raise InvalidState(
                            "Cannot apply incoming value with incompatible unit without revision/correction."
                        )

                    reason_text = (dec_dict.get("reason") or "").strip()
                    if not reason_text:
                        raise InvalidState(f"Reason is required for {action} action.")

                    reason_code = target_item.payload.get("reason_code")
                    if reason_code == "EXISTING_HUMAN_PROTECTED":
                        if actor_role != "curator":
                            raise Conflict("Only curator role can overwrite protected HUMAN_REVIEW value.")

                    if not doc_key or doc_key not in draft.documents:
                        raise InvalidState(f"Target document '{doc_key}' not found in draft.")
                    target_doc = draft.documents[doc_key]
                    if not attr_id or (attr_id not in target_doc.attributes and not new_attr_dict and not old_attr_dict):
                        raise InvalidState(f"Attribute '{attr_id}' not found in document '{doc_key}'.")

                if action == "KEEP_EXISTING":
                    target_item.status = "rejected"
                    target_item.decision = dec_dict
                    if notes:
                        target_item.notes = notes

                elif action == "APPLY_INCOMING":
                    if target_item.category == "UNIT_MISMATCH":
                        raise InvalidState(
                            "Cannot apply incoming value with incompatible unit without revision/correction."
                        )

                    target_item.status = "approved"
                    target_item.decision = dec_dict
                    if notes:
                        target_item.notes = notes

                    target_doc = draft.documents[doc_key]
                    if new_attr_dict:
                        applied_attr = AttributeValue.model_validate(new_attr_dict)
                        applied_attr.resolution = "HUMAN_REVIEW"
                        target_doc.attributes[attr_id] = applied_attr
                    elif attr_id in target_doc.attributes:
                        applied_attr = target_doc.attributes[attr_id]
                        applied_attr.value = target_item.payload.get("new_value")
                        applied_attr.unit = target_item.payload.get("new_unit")
                        applied_attr.resolution = "HUMAN_REVIEW"

                elif action == "REVISE":
                    corr_val = dec_dict.get("corrected_value")
                    corr_unit = dec_dict.get("corrected_unit")
                    if corr_val is None:
                        raise InvalidState("corrected_value is required for REVISE action.")

                    target_doc = draft.documents[doc_key]
                    expected_unit = None
                    val_type = "text"
                    if old_attr_dict:
                        try:
                            old_av = AttributeValue.model_validate(old_attr_dict)
                            expected_unit = old_av.unit
                            val_type = old_av.value_type
                        except Exception:
                            pass
                    elif attr_id in target_doc.attributes:
                        expected_unit = target_doc.attributes[attr_id].unit
                        val_type = target_doc.attributes[attr_id].value_type

                    if expected_unit is not None:
                        if not corr_unit or not str(corr_unit).strip():
                            raise InvalidState(
                                f"corrected_unit is required for attribute '{attr_id}' with expected unit '{expected_unit}'."
                            )
                        policy = AttributePolicy()
                        if not policy._units_compatible(expected_unit, str(corr_unit).strip()):
                            raise InvalidState(
                                f"Corrected unit '{corr_unit}' is incompatible with expected unit '{expected_unit}'."
                            )

                    if val_type == "number":
                        try:
                            if isinstance(corr_val, (int, float)):
                                corr_val = float(corr_val)
                            elif isinstance(corr_val, str) and corr_val.strip():
                                corr_val = float(corr_val.strip())
                            else:
                                raise ValueError
                        except (ValueError, TypeError):
                            raise InvalidState(f"Value '{corr_val}' is not a valid number for value_type 'number'.")

                    target_item.status = "revised"
                    target_item.decision = dec_dict
                    if notes:
                        target_item.notes = notes

                    if new_attr_dict:
                        applied_attr = AttributeValue.model_validate(new_attr_dict)
                        applied_attr.value = corr_val
                        if corr_unit is not None:
                            applied_attr.unit = str(corr_unit).strip()
                        applied_attr.resolution = "HUMAN_REVIEW"
                        target_doc.attributes[attr_id] = applied_attr
                    elif old_attr_dict:
                        applied_attr = AttributeValue.model_validate(old_attr_dict)
                        applied_attr.value = corr_val
                        if corr_unit is not None:
                            applied_attr.unit = str(corr_unit).strip()
                        applied_attr.resolution = "HUMAN_REVIEW"
                        target_doc.attributes[attr_id] = applied_attr
                    elif attr_id in target_doc.attributes:
                        applied_attr = target_doc.attributes[attr_id]
                        applied_attr.value = corr_val
                        if corr_unit is not None:
                            applied_attr.unit = str(corr_unit).strip()
                        applied_attr.resolution = "HUMAN_REVIEW"

            elif action == "ASSIGN_EXISTING":
                variety_id = dec_dict.get("selected_variety_id")
                habitat_id = dec_dict.get("target_habitat_id")
                target_key = (
                    f"{variety_id}:{habitat_id}"
                    if variety_id and habitat_id
                    else target_item.target_document_key
                )
                if not target_key or target_key not in draft.documents:
                    raise InvalidState(f"Target document '{target_key}' not found in draft.")

                target_doc = draft.documents[target_key]
                asset_id = target_item.payload.get("asset_id") or (
                    target_item.raw_values[0] if target_item.raw_values else ""
                )
                raw_organ = target_item.payload.get("organ_part") or "habitus"
                organ = raw_organ.lower() if isinstance(raw_organ, str) else "habitus"
                if organ not in {"habitus", "daun", "batang", "bunga", "buah", "biji"}:
                    organ = "habitus"

                if asset_id and not any(m.asset_id == asset_id for m in target_doc.media_refs):
                    media_ref = MediaReference(
                        asset_id=asset_id,
                        organ_part=organ,
                        caption=target_item.payload.get("caption"),
                        source_filename=target_item.source_label,
                        provenance_run_id=run_id,
                        assigned_via="HITL_REVIEW",
                        resolution_status="linked",
                    )
                    target_doc.media_refs.append(media_ref)

                target_item.status = "approved"
                target_item.decision = dec_dict
                target_item.target_document_key = target_key
                if notes:
                    target_item.notes = notes

            elif action == "CREATE_NEW_DOCUMENT":
                new_variety_name = dec_dict.get("new_variety_name") or "Cabai Baru"
                identity_level = dec_dict.get("identity_level") or "cultivar"
                target_habitat_id = dec_dict.get("target_habitat_id")

                matching_habitat = next(
                    (d.habitat for d in draft.documents.values() if d.habitat.id == target_habitat_id),
                    None,
                )
                if matching_habitat is None:
                    row = session.execute(
                        text("SELECT document->'habitat' FROM kms.knowledge_documents WHERE habitat_id = :h LIMIT 1"),
                        {"h": target_habitat_id},
                    ).scalar_one_or_none()
                    if row:
                        matching_habitat = HabitatIdentity.model_validate(row)
                    else:
                        raise InvalidState(f"Target habitat {target_habitat_id} not found in draft or persistent documents.")

                from src.storage.identity_resolution import _slugify

                var_slug = _slugify(new_variety_name).replace("-", "_")
                plant_id = f"plant_{var_slug}"
                variety = PlantIdentity(id=plant_id, label=new_variety_name, identity_level=identity_level)
                new_doc_key = f"{variety.id}:{matching_habitat.id}"

                sample_locs = copy.deepcopy(
                    next(
                        (d.sampling_locations for d in draft.documents.values() if d.habitat.id == target_habitat_id),
                        [],
                    )
                )
                asset_id = target_item.payload.get("asset_id") or (
                    target_item.raw_values[0] if target_item.raw_values else ""
                )
                raw_organ = target_item.payload.get("organ_part") or "habitus"
                organ = raw_organ.lower() if isinstance(raw_organ, str) else "habitus"
                if organ not in {"habitus", "daun", "batang", "bunga", "buah", "biji"}:
                    organ = "habitus"

                media_refs = []
                if asset_id:
                    media_refs.append(
                        MediaReference(
                            asset_id=asset_id,
                            organ_part=organ,
                            caption=target_item.payload.get("caption"),
                            source_filename=target_item.source_label,
                            provenance_run_id=run_id,
                            assigned_via="HITL_REVIEW",
                            resolution_status="linked",
                        )
                    )

                new_doc = KnowledgeDocument(
                    schema_version="kms-document-v1",
                    variety=variety,
                    habitat=matching_habitat,
                    sampling_locations=sample_locs,
                    attributes={},
                    media_refs=media_refs,
                    updated_by_run=run_id,
                    doc_id=new_doc_key,
                )
                draft.documents[new_doc_key] = new_doc
                if draft.base_versions is not None:
                    draft.base_versions[new_doc_key] = 0

                target_item.status = "approved"
                target_item.decision = dec_dict
                target_item.target_document_key = new_doc_key
                if notes:
                    target_item.notes = notes

            elif action == "DISCARD":
                target_item.status = "rejected"
                target_item.decision = dec_dict
                if notes:
                    target_item.notes = notes

                asset_id = target_item.payload.get("asset_id") or (
                    target_item.raw_values[0] if target_item.raw_values else None
                )
                if asset_id:
                    for d in draft.documents.values():
                        for m in d.media_refs:
                            if m.asset_id == asset_id:
                                m.resolution_status = "discarded"

            else:
                decision_status = dec_dict.get("status", "approved")
                target_item.status = "approved" if decision_status != "rejected" else "rejected"
                target_item.decision = dec_dict
                if notes:
                    target_item.notes = notes

            auto_accepted = sum(
                1
                for d in draft.documents.values()
                for a in d.attributes.values()
                if a.resolution == "AUTO_ACCEPT"
            )
            reviewed = sum(
                1
                for d in draft.documents.values()
                for a in d.attributes.values()
                if a.resolution != "AUTO_ACCEPT"
            ) + len([r for r in draft.reviews if r.status != "pending"])
            total_attrs = max(
                run.total_attributes or 0,
                len(draft.reviews) + sum(len(d.attributes) for d in draft.documents.values()),
                auto_accepted + reviewed,
            )

            run.draft_payload = draft.model_dump(mode="json")
            run.base_versions = draft.base_versions or {}
            run.auto_accepted_count = auto_accepted
            run.reviewed_count = reviewed
            run.total_attributes = total_attrs
            session.flush()

            return target_item.model_dump(mode="json")

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Retrieve run summary and draft."""
        with Session(self.engine) as session:
            run = session.get(AcquisitionRun, run_id)
            if run is None:
                raise NotFound("Run not found.")
            return {
                **self._run_summary(run),
                "draft": run.draft_payload,
                "base_versions": run.base_versions,
            }

    def add_candidate(
        self,
        *,
        asset_id: str,
        run_id: str,
        source_filename: str,
        original_sha256: str,
        organ_part: str,
        confidence: float,
        suggested_name: str | None = None,
        visual_evidence: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> dict[str, Any] | None:
        """Register a candidate image for human curation (idempotent)."""
        import uuid

        with transaction(self.engine) as session:
            context(session, actor)
            # Check if image was discarded
            discarded = session.execute(
                text("SELECT 1 FROM kms.discarded_images WHERE original_sha256 = :s"),
                {"s": original_sha256},
            ).first()
            if discarded:
                existing = session.execute(
                    text("SELECT * FROM kms.image_candidates WHERE asset_id = :a"),
                    {"a": asset_id},
                ).mappings().first()
                if existing:
                    return dict(existing)
                return None

            # Check if already exists by asset_id (idempotent)
            existing = session.execute(
                text("SELECT * FROM kms.image_candidates WHERE asset_id = :a"),
                {"a": asset_id},
            ).mappings().first()
            if existing:
                return dict(existing)

            cid = f"cand_{uuid.uuid4().hex[:16]}"
            session.execute(
                text(
                    "INSERT INTO kms.image_candidates ("
                    " candidate_id, asset_id, run_id, source_filename, original_sha256, organ_part,"
                    " suggested_name, visual_evidence, confidence, status, created_at"
                    ") VALUES ("
                    " :cid, :aid, :rid, :fn, :sha, :part, :sname, :ev, :conf, 'CANDIDATE', now()"
                    ")"
                ),
                {
                    "cid": cid,
                    "aid": asset_id,
                    "rid": run_id,
                    "fn": source_filename,
                    "sha": original_sha256,
                    "part": organ_part,
                    "sname": suggested_name,
                    "ev": json.dumps(visual_evidence or {}),
                    "conf": float(confidence),
                },
            )
            row = session.execute(
                text("SELECT * FROM kms.image_candidates WHERE candidate_id = :cid"),
                {"cid": cid},
            ).mappings().one()
            return dict(row)

    def list_candidates(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List image candidates with optional status filter."""
        query = "SELECT * FROM kms.image_candidates WHERE 1=1"
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            query += " AND status = :status"
            params["status"] = status
        query += " ORDER BY created_at ASC LIMIT :limit OFFSET :offset"
        with Session(self.engine) as session:
            rows = session.execute(text(query), params).mappings().all()
            return [dict(r) for r in rows]

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        """Get candidate by id."""
        with Session(self.engine) as session:
            row = session.execute(
                text("SELECT * FROM kms.image_candidates WHERE candidate_id = :cid"),
                {"cid": candidate_id},
            ).mappings().first()
            if row is None:
                raise NotFound(f"Candidate '{candidate_id}' not found.")
            return dict(row)

    def resolve_candidate(
        self,
        candidate_id: str,
        decision: dict[str, Any],
        *,
        actor: str,
        actor_role: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a candidate via PROMOTE, MERGE, or DISCARD."""
        if actor_role != "curator":
            raise Conflict("Only curator role can resolve image candidates.")

        action = decision.get("action")
        if action not in ("PROMOTE", "MERGE", "DISCARD"):
            raise InvalidState(f"Unknown candidate action '{action}'. Must be PROMOTE, MERGE, or DISCARD.")

        reason = (decision.get("reason") or "").strip()
        if len(reason) < 10:
            raise InvalidState("Reason is required and must be at least 10 characters.")

        with transaction(self.engine) as session:
            context(session, actor)
            row = session.execute(
                text("SELECT * FROM kms.image_candidates WHERE candidate_id = :cid FOR UPDATE"),
                {"cid": candidate_id},
            ).mappings().first()
            if row is None:
                raise NotFound(f"Candidate '{candidate_id}' not found.")
            if row["status"] != "CANDIDATE":
                raise Conflict(f"Candidate '{candidate_id}' is already decided (status={row['status']}).")

            if action == "PROMOTE":
                new_var_name = decision.get("new_variety_name")
                if not new_var_name or not str(new_var_name).strip():
                    raise InvalidState("new_variety_name is required for PROMOTE action.")
                new_var_name = str(new_var_name).strip()
                norm_id = re.sub(r"[^a-z0-9]+", "_", new_var_name.lower()).strip("_")
                var_id = f"plant_{norm_id}"
                plant = PlantIdentity(
                    id=var_id,
                    label=new_var_name,
                    identity_level=decision.get("identity_level", "cultivar"),
                )

                hab_dict = decision.get("habitat")
                hab_id_param = decision.get("habitat_id")
                if hab_dict and isinstance(hab_dict, dict):
                    habitat = HabitatIdentity.model_validate(hab_dict)
                    hab_unknown = False
                elif hab_id_param and hab_id_param != "habitat_unknown":
                    row_hab = session.execute(
                        text("SELECT document->'habitat' AS hab FROM kms.knowledge_documents WHERE habitat_id = :hid LIMIT 1"),
                        {"hid": hab_id_param},
                    ).mappings().first()
                    if row_hab is None:
                        raise InvalidState(
                            f"Habitat '{hab_id_param}' not found in registered documents; choose an existing habitat or leave empty for unknown habitat."
                        )
                    habitat = HabitatIdentity.model_validate(row_hab["hab"])
                    hab_unknown = False
                else:
                    habitat = make_unknown_habitat()
                    hab_unknown = True

                doc_key = f"{plant.id}:{habitat.id}"

                # F-2: Reject if document already exists; forbid overwriting via PROMOTE
                existing_doc = session.execute(
                    text("SELECT id FROM kms.knowledge_documents WHERE id = :id"),
                    {"id": doc_key},
                ).mappings().first()
                if existing_doc is not None:
                    raise Conflict(
                        f"Document '{doc_key}' already exists; use MERGE instead of PROMOTE to prevent overwriting."
                    )

                organ = row["organ_part"] if row["organ_part"] in ("habitus", "daun", "batang", "bunga", "buah", "biji") else "buah"
                media_ref = MediaReference(
                    asset_id=row["asset_id"],
                    organ_part=organ,
                    source_filename=row["source_filename"],
                    provenance_run_id=row["run_id"],
                    assigned_via="HITL_REVIEW",
                    resolution_status="linked",
                )
                new_doc = KnowledgeDocument(
                    variety=plant,
                    habitat=habitat,
                    attributes={},
                    media_refs=[media_ref],
                    updated_by_run=row["run_id"],
                    doc_id=doc_key,
                    version=1,
                    habitat_unknown=hab_unknown,
                )
                session.execute(
                    text(
                        "INSERT INTO kms.knowledge_documents (id, variety_id, habitat_id, document, version, created_at, updated_at) "
                        "VALUES (:id, :vid, :hid, CAST(:doc AS jsonb), 1, now(), now())"
                    ),
                    {
                        "id": doc_key,
                        "vid": plant.id,
                        "hid": habitat.id,
                        "doc": json.dumps(new_doc.model_dump(mode="json")),
                    },
                )
                new_status = "PROMOTED"

            elif action == "MERGE":
                target_doc_key = decision.get("target_doc_key")
                if not target_doc_key:
                    var_id = decision.get("variety_id")
                    hab_id = decision.get("habitat_id")
                    if var_id and hab_id:
                        target_doc_key = f"{var_id}:{hab_id}"
                if not target_doc_key:
                    raise InvalidState("target_doc_key or (variety_id, habitat_id) is required for MERGE.")

                target_row = session.execute(
                    text("SELECT document, version FROM kms.knowledge_documents WHERE id = :id FOR UPDATE"),
                    {"id": target_doc_key},
                ).mappings().first()
                if target_row is None:
                    raise NotFound(f"Target document '{target_doc_key}' not found.")

                expected_ver = decision.get("expected_version")
                if expected_ver is not None and target_row["version"] != expected_ver:
                    raise Conflict(
                        f"Target document version mismatch: expected {expected_ver}, got {target_row['version']}."
                    )

                doc_obj = KnowledgeDocument.model_validate(target_row["document"])
                organ = row["organ_part"] if row["organ_part"] in ("habitus", "daun", "batang", "bunga", "buah", "biji") else "buah"
                media_ref = MediaReference(
                    asset_id=row["asset_id"],
                    organ_part=organ,
                    source_filename=row["source_filename"],
                    provenance_run_id=row["run_id"],
                    assigned_via="HITL_REVIEW",
                    resolution_status="linked",
                )
                existing_aids = {m.asset_id for m in doc_obj.media_refs}
                if media_ref.asset_id not in existing_aids:
                    doc_obj.media_refs.append(media_ref)
                doc_obj.version = target_row["version"] + 1

                session.execute(
                    text(
                        "UPDATE kms.knowledge_documents "
                        "SET document = CAST(:doc AS jsonb), version = :v, updated_at = now() "
                        "WHERE id = :id AND version = :prev_v"
                    ),
                    {
                        "id": target_doc_key,
                        "doc": json.dumps(doc_obj.model_dump(mode="json")),
                        "v": doc_obj.version,
                        "prev_v": target_row["version"],
                    },
                )
                new_status = "MERGED"

            elif action == "DISCARD":
                session.execute(
                    text(
                        "INSERT INTO kms.discarded_images (original_sha256, reason, decided_by, decided_at, asset_id, source_filename) "
                        "VALUES (:s, :r, :a, now(), :aid, :fn) ON CONFLICT (original_sha256) DO NOTHING"
                    ),
                    {
                        "s": row["original_sha256"],
                        "r": reason,
                        "a": actor,
                        "aid": row["asset_id"],
                        "fn": row["source_filename"],
                    },
                )
                new_status = "DISCARDED"

            session.execute(
                text(
                    "UPDATE kms.image_candidates "
                    "SET status = :st, resolution = :res, decided_by = :actor, decided_at = now() "
                    "WHERE candidate_id = :cid"
                ),
                {
                    "st": new_status,
                    "res": json.dumps(decision),
                    "actor": actor,
                    "cid": candidate_id,
                },
            )
            updated = session.execute(
                text("SELECT * FROM kms.image_candidates WHERE candidate_id = :cid"),
                {"cid": candidate_id},
            ).mappings().one()
            return dict(updated)

    def set_document_habitat(
        self,
        doc_key: str,
        new_habitat: HabitatIdentity | dict[str, Any],
        *,
        actor: str,
        actor_role: str | None = None,
    ) -> dict[str, Any]:
        """Move or merge a document to a resolved habitat."""
        if actor_role != "curator":
            raise Conflict("Only curator role can set document habitat.")

        target_id = new_habitat.get("id") if isinstance(new_habitat, dict) else getattr(new_habitat, "id", None)
        if target_id == "habitat_unknown":
            raise InvalidState("Destination habitat cannot be habitat_unknown.")

        if hasattr(new_habitat, "model_dump"):
            hab_obj = new_habitat
        else:
            hab_obj = HabitatIdentity.model_validate(new_habitat)

        from src.storage.identity_resolution import compute_habitat_id

        # G-2: Server rejects administrative_path with 'Unknown' or empty tiers
        path = hab_obj.administrative_path
        if path:
            for tier_name, tier_val in [
                ("province", path.province_name),
                ("regency", path.regency_name),
                ("district", path.district_name),
                ("village", path.village_name),
            ]:
                if not tier_val or tier_val.strip().lower() in ("unknown", "", "tidak diketahui"):
                    raise InvalidState(
                        f"All administrative path tiers must be valid; '{tier_name}' cannot be empty or 'Unknown'."
                    )

            computed_id = compute_habitat_id(path)
            if not hab_obj.id or hab_obj.id == "habitat_unknown":
                hab_obj.id = computed_id
            elif hab_obj.id != computed_id:
                # A client-supplied id is only trusted when it names a habitat already registered in
                # persistent documents with exactly the same administrative path.
                with transaction(self.engine) as chk:
                    reg_row = chk.execute(
                        text("SELECT document->'habitat'->'administrative_path' AS p FROM kms.knowledge_documents WHERE habitat_id = :h LIMIT 1"),
                        {"h": hab_obj.id},
                    ).mappings().first()
                registered = reg_row["p"] if reg_row and reg_row["p"] else None
                same_path = bool(registered) and all(
                    str(registered.get(k) or "").strip().lower() == str(getattr(path, k) or "").strip().lower()
                    for k in ("province_name", "regency_name", "district_name", "village_name")
                )
                if not same_path:
                    raise InvalidState(
                        f"Habitat id '{hab_obj.id}' does not match its administrative path (expected '{computed_id}')."
                    )

        with transaction(self.engine) as session:
            context(session, actor)
            src_row = session.execute(
                text("SELECT id, document, version, variety_id, habitat_id FROM kms.knowledge_documents WHERE id = :id FOR UPDATE"),
                {"id": doc_key},
            ).mappings().first()
            if src_row is None:
                raise NotFound(f"Source document '{doc_key}' not found.")

            src_doc = KnowledgeDocument.model_validate(src_row["document"])
            dest_key = f"{src_doc.variety.id}:{hab_obj.id}"

            # F-3: Validation checks
            if dest_key == doc_key:
                raise InvalidState("Destination habitat produces the same document key as source.")
            if hab_obj.id == "habitat_unknown":
                raise InvalidState("Destination habitat cannot be habitat_unknown.")
            if not src_doc.habitat_unknown and src_doc.habitat.id != "habitat_unknown":
                raise InvalidState(
                    f"Source document '{doc_key}' already has a defined habitat; only habitat_unknown documents can be updated via set_document_habitat."
                )

            dest_row = session.execute(
                text("SELECT id, document, version FROM kms.knowledge_documents WHERE id = :id FOR UPDATE"),
                {"id": dest_key},
            ).mappings().first()

            if dest_row is not None:
                dest_doc = KnowledgeDocument.model_validate(dest_row["document"])
                # F-3: Check attribute conflicts; do not drop silently
                for aid, attr_val in src_doc.attributes.items():
                    if aid in dest_doc.attributes:
                        dest_val = dest_doc.attributes[aid]
                        if attr_val.value != dest_val.value:
                            raise Conflict(
                                f"Attribute conflict on '{aid}': source has '{attr_val.value}', destination has '{dest_val.value}'. Manual review required."
                            )
                    else:
                        dest_doc.attributes[aid] = attr_val

                dest_aids = {m.asset_id for m in dest_doc.media_refs}
                for m in src_doc.media_refs:
                    if m.asset_id not in dest_aids:
                        dest_doc.media_refs.append(m)
                dest_doc.version = dest_row["version"] + 1
                final_doc = dest_doc
                session.execute(
                    text("UPDATE kms.knowledge_documents SET document = CAST(:doc AS jsonb), version = :v, updated_at = now() WHERE id = :id"),
                    {"id": dest_key, "doc": json.dumps(final_doc.model_dump(mode="json")), "v": final_doc.version},
                )
                session.execute(
                    text("DELETE FROM kms.knowledge_documents WHERE id = :id"),
                    {"id": doc_key},
                )
            else:
                src_doc.habitat = hab_obj
                src_doc.habitat_unknown = False
                src_doc.doc_id = dest_key
                src_doc.version = src_row["version"] + 1
                final_doc = src_doc
                # In-place UPDATE on source row! Changes id, habitat_id, document, version.
                # Avoids delete+insert, requires only UPDATE privilege!
                session.execute(
                    text(
                        "UPDATE kms.knowledge_documents "
                        "SET id = :dest_key, habitat_id = :hid, document = CAST(:doc AS jsonb), version = :v, updated_at = now() "
                        "WHERE id = :src_key"
                    ),
                    {
                        "dest_key": dest_key,
                        "src_key": doc_key,
                        "hid": hab_obj.id,
                        "doc": json.dumps(final_doc.model_dump(mode="json")),
                        "v": final_doc.version,
                    },
                )

            # G-6: Write relational audit trace entry linking old doc_key to new dest_key
            session.execute(
                text(
                    "INSERT INTO kms.document_attribute_changes (doc_id, attribute_id, old_value, new_value, run_id, actor, created_at) "
                    "VALUES (:doc, 'habitat_migration_relink', :old_val, :new_val, :run, :actor, now())"
                ),
                {
                    "doc": doc_key,
                    "old_val": json.dumps({"doc_id": doc_key, "habitat_id": src_doc.habitat.id}),
                    "new_val": json.dumps({"doc_id": dest_key, "habitat_id": hab_obj.id}),
                    "run": src_row["document"].get("updated_by_run") or "set_document_habitat",
                    "actor": actor,
                },
            )

            return final_doc.model_dump(mode="json")

    def list_distinct_varieties(self) -> list[str]:
        """List distinct canonical variety names from all persistent knowledge documents."""
        with transaction(self.engine) as session:
            rows = session.execute(
                text(
                    "SELECT DISTINCT document->'variety'->>'label' AS name "
                    "FROM kms.knowledge_documents "
                    "WHERE document->'variety'->>'label' IS NOT NULL"
                )
            ).scalars().all()
            return sorted(r for r in rows if r)

    def stage_direct_document(
        self,
        doc_key: str,
        doc: KnowledgeDocument,
        *,
        run_id: str,
        actor: str,
    ) -> dict[str, Any]:
        """Helper to stage a single document directly in a run."""
        from src.storage.repository import KmsRepository

        sha = hashlib.sha256(doc_key.encode()).hexdigest()
        kms_repo = KmsRepository(self.engine)
        kms_repo.register_source(sha, f"cas:///sources/{run_id}.xlsx", 1000, actor=actor)

        draft = DocumentDraft(
            run_id=run_id,
            source_filename=f"{run_id}.xlsx",
            file_sha256=sha,
            source_uri=f"cas:///sources/{run_id}.xlsx",
            source_scope="test",
            schema_version="kms-document-v1",
            template_hash="0" * 64,
            config_fingerprint="cfg",
            revision=1,
            documents={doc_key: doc},
            reviews=[],
            base_versions={},
        )
        return self.stage(draft, expected_revision=0, actor=actor)
