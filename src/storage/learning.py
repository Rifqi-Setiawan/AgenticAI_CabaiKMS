from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .contracts import digest_json, normalize_identity
from .db import transaction
from .errors import Conflict, InvalidState, NotFound
from .repository import context


class LearningRepository:
    """Gold is automatic; exact aliases require explicit, evaluated curator promotion."""
    def __init__(self, engine: Engine):
        self.engine = engine

    def promote(self, gold_id: UUID, evaluation_reference: str, reason: str, *, actor: str) -> str:
        with transaction(self.engine) as session:
            context(session, actor)
            gold = session.execute(text('SELECT * FROM kms.gold_examples WHERE id=:i'), {'i': gold_id}).mappings().first()
            if gold is None:
                raise NotFound('Gold example not found.')
            if gold['characteristic_id'] is None:
                raise InvalidState('NO_MATCH is negative evidence, not an exact alias.')
            scope = {k: gold[k] for k in ('source_scope','schema_version','template_hash','source_label_normalized','context_hash')}
            lock = digest_json(scope)
            session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:k,0))'), {'k': 'alias:' + lock})
            conflict = session.execute(text('''SELECT count(*) FROM kms.gold_examples
              WHERE source_scope=:source_scope AND schema_version=:schema_version AND template_hash=:template_hash
              AND source_label_normalized=:source_label_normalized AND context_hash=:context_hash
              AND characteristic_id IS DISTINCT FROM :target'''), {**scope, 'target': gold['characteristic_id']}).scalar_one()
            if conflict:
                raise Conflict('Contradictory gold evidence exists; resolve scope/taxonomy first.')
            existing = session.execute(text('''SELECT id,characteristic_id FROM kms.canonical_aliases
              WHERE source_scope=:source_scope AND schema_version=:schema_version AND template_hash=:template_hash
              AND source_label_normalized=:source_label_normalized AND context_hash=:context_hash
              AND revoked_at IS NULL'''), scope).mappings().first()
            if existing:
                if existing['characteristic_id'] != gold['characteristic_id']:
                    raise Conflict('Conflicting active alias.')
                return str(existing['id'])
            return str(session.execute(text('''INSERT INTO kms.canonical_aliases
              (source_scope,schema_version,template_hash,source_label_normalized,context_hash,characteristic_id,gold_id,evaluation_reference,reason,promoted_by)
              VALUES(:source_scope,:schema_version,:template_hash,:source_label_normalized,:context_hash,:c,:g,:e,:r,:a) RETURNING id'''),
              {**scope, 'c': gold['characteristic_id'], 'g': gold_id, 'e': evaluation_reference, 'r': reason, 'a': actor}).scalar_one())

    def resolve(self, source_scope: str, template_hash: str, label: str, header_context: str, *, schema_version: str) -> str | None:
        with Session(self.engine) as session:
            result = session.execute(text('''SELECT c.canonical_key FROM kms.canonical_aliases a
              JOIN kms.characteristics c ON c.id=a.characteristic_id
              WHERE a.source_scope=:s AND a.schema_version=:sv AND a.template_hash=:t AND a.source_label_normalized=:l
              AND a.context_hash=:h AND a.revoked_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM kms.gold_examples g
                WHERE g.source_scope=a.source_scope AND g.schema_version=a.schema_version
                  AND g.template_hash=a.template_hash
                  AND g.source_label_normalized=a.source_label_normalized
                  AND g.context_hash=a.context_hash
                  AND g.characteristic_id IS DISTINCT FROM a.characteristic_id
              )'''),
              {'s': source_scope, 'sv': schema_version, 't': template_hash, 'l': normalize_identity(label),
               'h': digest_json(normalize_identity(header_context))}).scalars().all()
            return result[0] if len(result) == 1 else None

    def revoke(self, alias_id: UUID, reason: str, *, actor: str) -> None:
        if len(reason.strip()) < 10:
            raise InvalidState('Revocation needs an explanatory reason.')
        with transaction(self.engine) as session:
            context(session, actor)
            row = session.execute(text('''UPDATE kms.canonical_aliases SET revoked_at=now(), revoked_by=:a,revoke_reason=:r
              WHERE id=:i AND revoked_at IS NULL RETURNING id'''), {'i': alias_id, 'a': actor, 'r': reason}).first()
            if row is None:
                raise NotFound('Active alias not found.')
