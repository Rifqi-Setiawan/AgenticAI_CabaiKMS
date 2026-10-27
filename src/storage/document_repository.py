"""Additive DDL and JSONB document repository for CabaiKMS."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.storage.contracts import canonical_json, digest_json
from src.storage.db import transaction
from src.storage.document_contracts import (
    AttributeValue,
    CommitReceipt,
    DocumentDraft,
    HabitatIdentity,
    KnowledgeDocument,
    MediaReference,
    OverwriteDecision,
    PhotoMismatchDecision,
    PlantIdentity,
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


class DocumentDict(dict):
    """Dictionary supporting attribute access for backwards-compatible test usage."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'DocumentDict' object has no attribute '{name}'")

    def __getitem__(self, key: str) -> Any:
        val = super().__getitem__(key)
        if isinstance(val, dict) and not isinstance(val, DocumentDict):
            val = DocumentDict(val)
            self[key] = val
        return val


class RunDict(dict):
    """Dictionary supporting draft_payload alias for draft."""

    def __getitem__(self, key: str) -> Any:
        if key == "draft_payload":
            return self.get("draft")
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "draft_payload":
            return super().get("draft", default)
        return super().get(key, default)


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
        has_table = session.execute(
            text("SELECT to_regclass('kms.document_attribute_changes') IS NOT NULL")
        ).scalar()
        if has_table:
            session.execute(
                text("""
                    INSERT INTO kms.document_attribute_changes
                    (doc_id, attribute_id, old_value, new_value, run_id, actor, created_at)
                    VALUES (:doc_id, :attribute_id, CAST(:old_val AS jsonb), CAST(:new_val AS jsonb), :run_id, :actor, now())
                """),
                {
                    "doc_id": doc_id,
                    "attribute_id": attribute_id,
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

            draft = DocumentDraft.model_validate(run.draft_payload)
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
                            can_ow = is_approved_override
                            if not can_ow:
                                try:
                                    exist_av = AttributeValue.model_validate(exist_dict)
                                    inc_av = AttributeValue.model_validate(inc_dict)
                                    can_ow = policy.can_overwrite(exist_av, inc_av)
                                except Exception:
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
            doc = DocumentDict(row["document"])
            doc["id"] = row["id"]
            doc["doc_id"] = row["id"]
            doc["version"] = row["version"]
            return doc

    def list_documents(
        self,
        *,
        variety_id: str | None = None,
        habitat_id: str | None = None,
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
        actor_role: str = "curator",
    ) -> dict[str, Any]:
        """Resolve a pending review item in a staged DocumentDraft envelope."""
        if hasattr(decision, "model_dump"):
            dec_dict = decision.model_dump(mode="json")
        else:
            dec_dict = dict(decision)

        action = dec_dict.get("action")
        notes = dec_dict.get("notes")

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

                reason_code = target_item.payload.get("reason_code")
                if reason_code == "EXISTING_HUMAN_PROTECTED" and action in ("APPLY_INCOMING", "REVISE"):
                    if actor_role != "curator":
                        raise Conflict("Only curator role can overwrite protected HUMAN_REVIEW value.")
                    reason_text = (dec_dict.get("reason") or "").strip()
                    if not reason_text:
                        raise InvalidState("Reason is required to overwrite protected HUMAN_REVIEW value.")

                doc_key = target_item.target_document_key
                attr_id = target_item.payload.get("attribute_id")
                new_attr_dict = target_item.payload.get("new_attribute")
                old_attr_dict = target_item.payload.get("old_attribute")

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

                    if doc_key and doc_key in draft.documents and attr_id:
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

                    policy = AttributePolicy()
                    if old_attr_dict:
                        old_av = AttributeValue.model_validate(old_attr_dict)
                        if old_av.unit and corr_unit and not policy._units_compatible(old_av.unit, corr_unit):
                            raise InvalidState(
                                f"Corrected unit '{corr_unit}' is incompatible with expected unit '{old_av.unit}'."
                            )

                    target_item.status = "revised"
                    target_item.decision = dec_dict
                    if notes:
                        target_item.notes = notes

                    if doc_key and doc_key in draft.documents and attr_id:
                        target_doc = draft.documents[doc_key]
                        if new_attr_dict:
                            applied_attr = AttributeValue.model_validate(new_attr_dict)
                            applied_attr.value = corr_val
                            if corr_unit is not None:
                                applied_attr.unit = corr_unit
                            applied_attr.resolution = "HUMAN_REVIEW"
                            target_doc.attributes[attr_id] = applied_attr
                        elif old_attr_dict:
                            applied_attr = AttributeValue.model_validate(old_attr_dict)
                            applied_attr.value = corr_val
                            if corr_unit is not None:
                                applied_attr.unit = corr_unit
                            applied_attr.resolution = "HUMAN_REVIEW"
                            target_doc.attributes[attr_id] = applied_attr
                        elif attr_id in target_doc.attributes:
                            applied_attr = target_doc.attributes[attr_id]
                            applied_attr.value = corr_val
                            if corr_unit is not None:
                                applied_attr.unit = corr_unit
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
            return RunDict({
                **self._run_summary(run),
                "draft": run.draft_payload,
                "base_versions": run.base_versions,
            })
