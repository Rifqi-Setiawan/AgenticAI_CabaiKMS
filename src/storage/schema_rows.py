"""Persistence for acquired canonical rows (dynamic schema).

Acquisition is idempotent and duplicate-averse: a label (or alias) that already exists, in the template or in the
acquired rows, never creates a second row; the existing row is returned instead.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.schema.canonical import CanonicalSchema
from src.storage.attribute_policy import normalize_label, slugify_attribute_key
from src.storage.db import transaction
from src.storage.document_repository import context
from src.storage.errors import Conflict, InvalidState

ACTIVE_STATUSES = ("provisional", "approved")


class SchemaRowRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ------------------------------------------------------------------ reads
    def list_rows(self) -> dict[str, Any]:
        """Rows that belong in the schema (provisional or approved) plus aliases of template and acquired rows."""
        with Session(self.engine) as session:
            rows = session.execute(text(
                "SELECT seq, canonical_key, label, domain, examples, aliases, status FROM kms.schema_rows_ext "
                "WHERE status IN ('provisional','approved') ORDER BY seq")).mappings().all()
            aliases = session.execute(text(
                "SELECT alias, target_key FROM kms.schema_aliases_ext ORDER BY created_at, alias_norm")).mappings().all()
        return {"rows": [dict(r) for r in rows], "aliases": [dict(a) for a in aliases]}


    # ------------------------------------------------------------------ curation
    def _event(self, session: Session, key: str, event: str, actor: str, run_id: str, detail: dict[str, Any]) -> None:
        session.execute(text(
            "INSERT INTO kms.schema_row_events (canonical_key, event, actor, run_id, detail) "
            "VALUES (:k, :e, :a, :r, CAST(:d AS jsonb))"),
            {"k": key, "e": event, "a": actor, "r": run_id or None, "d": json.dumps(detail, ensure_ascii=False)})

    def _active(self, session: Session, key: str) -> dict[str, Any]:
        row = session.execute(text(
            "SELECT seq, canonical_key, label, label_norm, aliases, status FROM kms.schema_rows_ext WHERE canonical_key = :k"),
            {"k": key}).mappings().first()
        if row is None:
            raise InvalidState(f"Unknown acquired row '{key}'.")
        if row["status"] not in ACTIVE_STATUSES:
            raise InvalidState(f"Row '{key}' is already {row['status']}.")
        return dict(row)

    @staticmethod
    def _need_reason(reason: str) -> str:
        reason = (reason or "").strip()
        if len(reason) < 10:
            raise InvalidState("Reason (min 10 characters) is required.")
        return reason

    def set_status(self, key: str, status: str, *, actor: str, reason: str) -> dict[str, Any]:
        """approve (provisional to approved) or discard (row leaves the schema and its label is remembered)."""
        if status not in ("approved", "discarded"):
            raise InvalidState("status must be approved or discarded")
        reason = self._need_reason(reason)
        with transaction(self.engine) as session:
            context(session, actor, "")
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('schema:rows', 0))"))
            row = self._active(session, key)
            if status == "approved" and row["status"] == "approved":
                raise InvalidState(f"Row '{key}' is already approved.")
            session.execute(text(
                "UPDATE kms.schema_rows_ext SET status = :s, updated_by = :a, updated_at = now() WHERE canonical_key = :k"),
                {"s": status, "a": actor, "k": key})
            self._event(session, key, status.upper(), actor, "", {"reason": reason})
        return {"canonical_key": key, "status": status}

    def merge(self, key: str, into_key: str, *, actor: str, reason: str) -> dict[str, Any]:
        """Merge a duplicate into another row (template or acquired); its label and aliases become aliases of the target."""
        reason = self._need_reason(reason)
        if key == into_key:
            raise InvalidState("A row cannot be merged into itself.")
        template_keys = {r.canonical_key for r in CanonicalSchema.from_template().rows}
        with transaction(self.engine) as session:
            context(session, actor, "")
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('schema:rows', 0))"))
            row = self._active(session, key)
            if into_key not in template_keys:
                self._active(session, into_key)
            names = {row["label_norm"], *[str(a) for a in row["aliases"]]}
            for name in sorted(names):
                display = row["label"] if name == row["label_norm"] else name
                session.execute(text(
                    "INSERT INTO kms.schema_aliases_ext (alias_norm, alias, target_key, created_from_run, created_by, reason) "
                    "VALUES (:n, :a, :t, :r, :actor, :reason) ON CONFLICT (alias_norm) DO NOTHING"),
                    {"n": name, "a": display, "t": into_key, "r": "curation", "actor": actor, "reason": reason})
                stored = session.execute(text("SELECT target_key FROM kms.schema_aliases_ext WHERE alias_norm = :n"), {"n": name}).scalar_one()
                if stored != into_key:
                    raise Conflict(f"Alias '{display}' already points to '{stored}'.")
            session.execute(text(
                "UPDATE kms.schema_rows_ext SET status = 'merged', merged_into_key = :t, updated_by = :a, updated_at = now() "
                "WHERE canonical_key = :k"), {"t": into_key, "a": actor, "k": key})
            self._event(session, key, "MERGED", actor, "", {"into": into_key, "reason": reason})
        return {"canonical_key": key, "status": "merged", "merged_into_key": into_key}

    def list_all(self) -> list[dict[str, Any]]:
        """Every acquired row with its status (for the curator panel)."""
        with Session(self.engine) as session:
            rows = session.execute(text(
                "SELECT seq, canonical_key, label, domain, examples, aliases, status, merged_into_key, source_label, "
                "created_from_run, created_by, reason, created_at FROM kms.schema_rows_ext ORDER BY seq")).mappings().all()
        return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]

    # ------------------------------------------------------------------ acquisition
    def acquire(
        self, *, label: str, domain: str, examples: list[str] | None, source_label: str | None,
        run_id: str, source_sha256: str | None, actor: str, reason: str,
        allowed_domains: frozenset[str] | None = None, aliases: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a provisional row unless the meaning already exists. Returns {created, row, duplicate_of}."""
        label = (label or "").strip()
        if not label:
            raise InvalidState("label is required")
        template = CanonicalSchema.from_template()
        domains = allowed_domains or template.domains
        if domain not in domains:
            raise InvalidState(f"domain must be one of {sorted(domains)}")
        label_norm = normalize_label(label)
        keys_taken = {r.canonical_key for r in template.rows}

        for row in template.rows:
            names = [row.label, *row.alt_labels]
            if label_norm in {normalize_label(n) for n in names}:
                return {"created": False, "duplicate_of": row.canonical_key, "row": None}

        with transaction(self.engine) as session:
            context(session, actor, run_id)
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('schema:rows', 0))"))
            discarded = session.execute(text(
                "SELECT canonical_key FROM kms.schema_rows_ext WHERE status = 'discarded' AND label_norm = :n"),
                {"n": label_norm}).scalar()
            if discarded is not None:
                return {"created": False, "duplicate_of": None, "rejected": True, "row": None}
            hit = session.execute(text(
                "SELECT canonical_key FROM kms.schema_rows_ext WHERE status IN ('provisional','approved') AND "
                "(label_norm = :n OR aliases @> CAST(:nj AS jsonb))"),
                {"n": label_norm, "nj": json.dumps([label_norm])}).scalar()
            if hit is None:
                hit = session.execute(text(
                    "SELECT target_key FROM kms.schema_aliases_ext WHERE alias_norm = :n"), {"n": label_norm}).scalar()
            if hit is not None:
                return {"created": False, "duplicate_of": hit, "row": None}
            keys_taken |= set(session.execute(text("SELECT canonical_key FROM kms.schema_rows_ext")).scalars().all())
            known_names = {normalize_label(n) for r in template.rows for n in (r.label, *r.alt_labels)}
            for stored_label, stored_aliases in session.execute(text(
                    "SELECT label_norm, aliases FROM kms.schema_rows_ext WHERE status IN ('provisional','approved')")).all():
                known_names |= {stored_label, *stored_aliases}
            known_names |= set(session.execute(text("SELECT alias_norm FROM kms.schema_aliases_ext")).scalars().all())
            alias_norms = sorted({normalize_label(a) for a in (aliases or []) if normalize_label(a)} - {label_norm} - known_names)
            base_key = slugify_attribute_key(label) or "atribut_baru"
            if not base_key[0].isalpha():
                base_key = "a_" + base_key
            key, n = base_key, 2
            while key in keys_taken:
                key, n = f"{base_key}_{n}", n + 1
            try:
                row = session.execute(text(
                    "INSERT INTO kms.schema_rows_ext (canonical_key, label, label_norm, domain, examples, aliases, status, "
                    "source_label, source_file_sha256, created_from_run, created_by, reason) "
                    "VALUES (:k, :label, :n, :d, CAST(:ex AS jsonb), CAST(:al AS jsonb), 'provisional', :src, :sha, :run, :actor, :reason) "
                    "RETURNING seq, canonical_key, label, domain, examples, aliases, status"),
                    {"k": key, "label": label, "n": label_norm, "d": domain,
                     "ex": json.dumps([str(x) for x in (examples or [])[:5]], ensure_ascii=False),
                     "al": json.dumps(alias_norms, ensure_ascii=False), "src": source_label, "sha": source_sha256, "run": run_id, "actor": actor,
                     "reason": reason}).mappings().one()
            except IntegrityError as error:
                raise Conflict("Row conflicts with an existing acquired row.") from error
            session.execute(text(
                "INSERT INTO kms.schema_row_events (canonical_key, event, actor, run_id, detail) "
                "VALUES (:k, 'ACQUIRED', :actor, :run, CAST(:d AS jsonb))"),
                {"k": key, "actor": actor, "run": run_id,
                 "d": json.dumps({"label": label, "source_label": source_label, "reason": reason},
                                               ensure_ascii=False)})
            return {"created": True, "duplicate_of": None, "row": dict(row)}
