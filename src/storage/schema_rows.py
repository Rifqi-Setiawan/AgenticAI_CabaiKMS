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

    # ------------------------------------------------------------------ acquisition
    def acquire(
        self, *, label: str, domain: str, examples: list[str] | None, source_label: str | None,
        run_id: str, source_sha256: str | None, actor: str, reason: str,
        allowed_domains: frozenset[str] | None = None,
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
                    "VALUES (:k, :label, :n, :d, CAST(:ex AS jsonb), '[]'::jsonb, 'provisional', :src, :sha, :run, :actor, :reason) "
                    "RETURNING seq, canonical_key, label, domain, examples, aliases, status"),
                    {"k": key, "label": label, "n": label_norm, "d": domain,
                     "ex": json.dumps([str(x) for x in (examples or [])[:5]], ensure_ascii=False),
                     "src": source_label, "sha": source_sha256, "run": run_id, "actor": actor,
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
