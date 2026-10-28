from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .contracts import RunDraft, canonical_json, digest_json, normalize_identity
from .db import transaction
from .errors import Conflict, InvalidState, NotFound
from .models import AcquisitionRun, Characteristic, CharacterValue, PlantImage, Variety


def context(session: Session, actor: str, run_id: str = '') -> None:
    if not actor.strip():
        raise InvalidState('Authenticated actor required.')
    session.execute(text("SELECT set_config('kms.actor', :a, true), set_config('kms.run_id', :r, true)"), {'a': actor, 'r': run_id})


def pair_key(name: str, characteristic: str) -> str:
    return digest_json([name, characteristic])


def variety_upsert(data: dict[str, Any]):
    table = Variety.__table__
    statement = insert(table).values(**data)
    return statement.on_conflict_do_update(
        index_elements=[table.c.canonical_name],
        set_={
            'origin_region': func.coalesce(table.c.origin_region, statement.excluded.origin_region),
            'acquisition_date': func.least(table.c.acquisition_date, statement.excluded.acquisition_date),
            'metadata': table.c.metadata.op('||')(statement.excluded.metadata),
            'updated_at': func.now(),
        },
    ).returning(table.c.id)


def value_upsert(data: dict[str, Any], expected_version: int):
    table = CharacterValue.__table__
    statement = insert(table).values(**data)
    return statement.on_conflict_do_update(
        index_elements=[table.c.variety_id, table.c.characteristic_id],
        set_={**{key: getattr(statement.excluded, key) for key in (
            'normalized_value', 'raw_source_value', 'value_type', 'is_multi_value',
            'confidence_score', 'status', 'run_id',
        )}, 'version': table.c.version + 1, 'updated_at': func.now()},
        where=table.c.version == expected_version,
    ).returning(table.c.id)


class KmsRepository:
    def __init__(self, engine: Engine, *, allow_legacy_sourceless_runs: bool = False):
        self.engine = engine
        self.allow_legacy_sourceless_runs = allow_legacy_sourceless_runs

    def _base_versions(self, session: Session, draft: RunDraft) -> dict[str, int]:
        names = [v.canonical_name for v in draft.varieties]
        keys = [c.canonical_key for c in draft.characteristics]
        rows = session.execute(
            select(Variety.canonical_name, Characteristic.canonical_key, CharacterValue.version)
            .select_from(CharacterValue).join(Variety).join(Characteristic)
            .where(Variety.canonical_name.in_(names), Characteristic.canonical_key.in_(keys))
        ).all()
        known = {pair_key(row[0], row[1]): row[2] for row in rows}
        return {pair_key(v.variety_name, v.canonical_key): known.get(pair_key(v.variety_name, v.canonical_key), 0) for v in draft.values}

    @staticmethod
    def _lock(session: Session, run_id: str) -> None:
        session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key': 'run:' + run_id})

    @staticmethod
    def _archive_draft(session: Session, run: AcquisitionRun, actor: str) -> None:
        session.execute(text('''INSERT INTO kms.draft_revisions
          (run_id,revision,payload_sha256,payload,base_versions,actor)
          VALUES (:r,:v,:h,CAST(:p AS jsonb),CAST(:b AS jsonb),:a)'''),
          {'r': run.run_id, 'v': run.revision, 'h': run.payload_sha256,
           'p': canonical_json(run.draft_payload), 'b': canonical_json(run.base_versions), 'a': actor})

    def stage(self, draft: RunDraft, *, expected_revision: int, actor: str) -> dict[str, Any]:
        payload, checksum = draft.ordered_payload(), draft.fingerprint()
        with transaction(self.engine) as session:
            context(session, actor, draft.run_id)
            self._lock(session, draft.run_id)
            existing = session.get(AcquisitionRun, draft.run_id)
            if existing is not None:
                if existing.payload_sha256 == checksum:
                    return self._run_summary(existing)
                if existing.status == 'COMMITTED':
                    raise Conflict('Run already committed. Create a new amendment run_id.')
                if existing.revision != expected_revision:
                    raise Conflict('Draft revision changed. Reload the saved draft before editing.')
                previous = RunDraft.model_validate(existing.draft_payload)
                for field in ('source_filename', 'file_sha256', 'source_uri', 'source_scope',
                              'schema_version', 'template_hash', 'config_fingerprint',
                              'total_attributes', 'auto_accepted_count', 'executed_at', 'execution_duration_ms'):
                    if getattr(previous, field) != getattr(draft, field):
                        raise Conflict('Source/schema/config/run identity cannot change inside one run.')
                new_reviews = {review.item_id: review for review in draft.reviews}
                if set(new_reviews) != {review.item_id for review in previous.reviews}:
                    raise Conflict('Review membership cannot change inside an existing run.')
                for review in previous.reviews:
                    incoming = new_reviews[review.item_id]
                    if review.status != 'pending' and incoming.model_dump(mode='json') != review.model_dump(mode='json'):
                        raise Conflict('A persisted review cannot be reverted. Recover the saved draft or create an amendment run.')
                existing.revision += 1
                existing.draft_payload = payload
                existing.payload_sha256 = checksum
                existing.reviewed_count = draft.reviewed_count
                # New pairs capture a baseline; existing pair baselines never silently advance.
                fresh = self._base_versions(session, draft)
                existing.base_versions = {key: existing.base_versions.get(key, value) for key, value in fresh.items()}
                session.flush()
                self._archive_draft(session, existing, actor)
                return self._run_summary(existing)
            if expected_revision != 0:
                raise Conflict('New runs must use expected_revision=0.')
            if draft.source_uri:
                source = session.execute(text('SELECT storage_uri FROM kms.source_artifacts WHERE sha256=:h'), {'h': draft.file_sha256}).scalar_one_or_none()
                if source != draft.source_uri:
                    raise InvalidState('Source artifact is not registered, or checksum/URI mismatch.')
            fields = {key: getattr(draft, key) for key in (
                'run_id','source_filename','file_sha256','source_uri','schema_version','template_hash',
                'config_fingerprint','total_attributes','auto_accepted_count','reviewed_count',
                'execution_duration_ms','executed_at',
            )}
            run = AcquisitionRun(**fields, status='STAGED', revision=1, payload_sha256=checksum,
                                 draft_payload=payload, base_versions=self._base_versions(session, draft))
            session.add(run)
            session.flush()
            self._archive_draft(session, run, actor)
            return self._run_summary(run)

    @staticmethod
    def _run_summary(run: AcquisitionRun) -> dict[str, Any]:
        return {'run_id': run.run_id, 'status': run.status, 'revision': run.revision,
                'payload_sha256': run.payload_sha256, 'receipt': run.receipt}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            run = session.get(AcquisitionRun, run_id)
            if run is None:
                raise NotFound('Run not found.')
            return {**self._run_summary(run), 'draft': run.draft_payload, 'base_versions': run.base_versions}

    def rebase(self, run_id: str, expected_revision: int, reason: str, *, actor: str) -> dict[str, Any]:
        with transaction(self.engine) as session:
            context(session, actor, run_id)
            self._lock(session, run_id)
            run = session.get(AcquisitionRun, run_id)
            if run is None:
                raise NotFound('Run not found.')
            if run.status != 'STAGED' or run.revision != expected_revision:
                raise Conflict('Rebase requires the current STAGED revision.')
            run.base_versions = self._base_versions(session, RunDraft.model_validate(run.draft_payload))
            run.revision += 1
            session.flush()
            self._archive_draft(session, run, actor)
            session.execute(text('''INSERT INTO kms.audit_trace(run_id,actor,event_type,entity_type,new_data)
               VALUES(:r,:a,'EXPLICIT_REBASE','acquisition_runs',CAST(:d AS jsonb))'''),
               {'r': run_id, 'a': actor, 'd': canonical_json({'reason': reason, 'revision': run.revision})})
            return self._run_summary(run)

    def _catalog(self, session: Session, draft: RunDraft) -> dict[str, UUID]:
        definition = draft.ordered_payload()['characteristics']
        catalog_hash = digest_json(definition)
        session.execute(text('''INSERT INTO kms.catalog_versions(schema_version,template_hash,catalog_hash,definition)
          VALUES(:s,:t,:h,CAST(:d AS jsonb)) ON CONFLICT DO NOTHING'''),
          {'s': draft.schema_version, 't': draft.template_hash, 'h': catalog_hash, 'd': canonical_json(definition)})
        stored = session.execute(text('SELECT catalog_hash FROM kms.catalog_versions WHERE schema_version=:s AND template_hash=:t'),
                                 {'s': draft.schema_version, 't': draft.template_hash}).scalar_one()
        if stored != catalog_hash:
            raise Conflict('Canonical catalog changed without a new schema version/template identity.')
        ids: dict[str, UUID] = {}
        for characteristic in sorted(draft.characteristics, key=lambda x: x.canonical_key):
            table = Characteristic.__table__
            data = characteristic.model_dump()
            statement = insert(table).values(**data).on_conflict_do_nothing(index_elements=[table.c.canonical_key])
            session.execute(statement)
            current = session.execute(select(Characteristic).where(Characteristic.canonical_key == characteristic.canonical_key).with_for_update()).scalar_one()
            for field in ('organ_domain','data_type','standard_unit'):
                if getattr(current, field) != data[field]:
                    raise Conflict(f'Curated catalog migration required for {characteristic.canonical_key}: {field}.')
            # Display metadata is versioned in catalog_versions; stable key remains unchanged.
            current.label_id = characteristic.label_id
            current.description = characteristic.description
            ids[characteristic.canonical_key] = current.id
        session.flush()
        return ids

    def commit(self, run_id: str, revision: int, payload_sha256: str, *, actor: str) -> dict[str, Any]:
        with transaction(self.engine) as session:
            context(session, actor, run_id)
            self._lock(session, run_id)
            run = session.get(AcquisitionRun, run_id)
            if run is None:
                raise NotFound('Run not found.')
            if run.revision != revision or run.payload_sha256 != payload_sha256:
                raise Conflict('Commit revision/digest no longer matches the reviewed draft.')
            if run.status == 'COMMITTED':
                return {**run.receipt, 'replayed': True}
            draft = RunDraft.model_validate(run.draft_payload)
            if any(review.status == 'pending' for review in draft.reviews):
                raise InvalidState('Resolve every pending review before committing.')
            if not draft.source_uri and not (self.allow_legacy_sourceless_runs and draft.metadata.get('legacy_source_unavailable', False)):
                raise InvalidState('Archive the original source before committing a new run.')
            characteristic_ids = self._catalog(session, draft)
            variety_ids: dict[str, UUID] = {}
            for variety in sorted(draft.varieties, key=lambda x: x.canonical_name):
                data = variety.model_dump(exclude={'local_aliases'})
                variety_id = session.execute(variety_upsert(data)).scalar_one()
                variety_ids[variety.canonical_name] = variety_id
                for alias in sorted({normalize_identity(a) for a in variety.local_aliases if a.strip()}):
                    session.execute(text('INSERT INTO kms.variety_aliases(variety_id,alias) VALUES (:v,:a) ON CONFLICT DO NOTHING'),
                                    {'v': variety_id, 'a': alias})
            upserted = observations = protected = 0
            for value in sorted(draft.values, key=lambda v: (v.variety_name, v.canonical_key)):
                variety_id, characteristic_id = variety_ids[value.variety_name], characteristic_ids[value.canonical_key]
                # Consistent ordering plus per-pair advisory locks protects absent-row races.
                key = pair_key(value.variety_name, value.canonical_key)
                session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:k,0))'), {'k': 'value:' + key})
                current = session.execute(select(CharacterValue).where(
                    CharacterValue.variety_id == variety_id, CharacterValue.characteristic_id == characteristic_id
                ).with_for_update()).scalar_one_or_none()
                for evidence in value.provenance:
                    row = session.execute(text('''INSERT INTO kms.value_observations
                       (run_id,variety_id,characteristic_id,observation_sha256,evidence)
                       VALUES(:r,:v,:c,:h,CAST(:e AS jsonb)) ON CONFLICT DO NOTHING RETURNING id'''),
                       {'r': run_id, 'v': variety_id, 'c': characteristic_id, 'h': digest_json(evidence), 'e': canonical_json(evidence)}).first()
                    observations += int(row is not None)
                # Never demote a reviewed current fact to an AI-only current fact.
                if current is not None and current.status == 'HUMAN_REVIEW' and value.status == 'AUTO_ACCEPT':
                    protected += 1
                    continue
                expected = run.base_versions[key]
                if (current.version if current else 0) != expected:
                    raise Conflict('Current values changed since review. Inspect differences and explicitly rebase.')
                data = value.model_dump(exclude={'variety_name','canonical_key','provenance'})
                data.update(variety_id=variety_id, characteristic_id=characteristic_id, run_id=run_id, version=1)
                row = session.execute(value_upsert(data, expected)).first()
                if row is None:
                    raise Conflict('Concurrent projection update detected; transaction rolled back.')
                upserted += 1
            for review in draft.reviews:
                characteristic_id = characteristic_ids.get(review.final_canonical_key)
                evidence = review.model_dump(mode='json')
                session.execute(text('''INSERT INTO kms.review_decisions
                   (run_id,item_id,decision,characteristic_id,actor,evidence)
                   VALUES(:r,:i,:d,:c,:a,CAST(:e AS jsonb))'''),
                   {'r': run_id, 'i': review.item_id, 'd': review.status, 'c': characteristic_id, 'a': actor, 'e': canonical_json(evidence)})
                session.execute(text('''INSERT INTO kms.gold_examples
                   (run_id,item_id,source_scope,schema_version,template_hash,source_label_normalized,context_hash,characteristic_id,decision,example,actor)
                   VALUES(:r,:i,:s,:sv,:t,:l,:h,:c,:d,CAST(:e AS jsonb),:a)'''),
                   {'r': run_id, 'i': review.item_id, 's': draft.source_scope, 'sv': draft.schema_version, 't': draft.template_hash,
                    'l': normalize_identity(review.source_label), 'h': digest_json(normalize_identity(review.source_context)),
                    'c': characteristic_id, 'd': review.status, 'e': canonical_json(evidence), 'a': actor})
            image_count = 0
            for image in draft.images:
                found = session.execute(text('SELECT id FROM kms.media_assets WHERE id=:i'), {'i': image.asset_id}).scalar_one_or_none()
                if found is None:
                    raise InvalidState('Image asset must be durably registered before commit.')
                data = image.model_dump(exclude={'variety_name','classification_status'})
                data.update(run_id=run_id, variety_id=variety_ids[image.variety_name])
                statement = insert(PlantImage.__table__).values(**data).on_conflict_do_nothing().returning(PlantImage.id)
                image_count += int(session.execute(statement).first() is not None)
            receipt = {'run_id': run_id, 'revision': revision, 'rows_upserted': upserted,
                       'observations_inserted': observations, 'reviewed_values_protected': protected,
                       'images_linked': image_count, 'gold_examples_inserted': len(draft.reviews), 'replayed': False}
            session.execute(text('''INSERT INTO kms.outbox_events(run_id,event_type,payload)
              VALUES(:r,'KMS_COMMITTED',CAST(:p AS jsonb))'''),
              {'r': run_id, 'p': canonical_json({'run_id': run_id, 'revision': revision, 'payload_sha256': payload_sha256})})
            run.status, run.receipt, run.committed_at = 'COMMITTED', receipt, datetime.now(timezone.utc)
            session.flush()
            return receipt

    def register_source(self, sha256: str, uri: str, size: int, *, actor: str) -> dict[str, Any]:
        with transaction(self.engine) as session:
            context(session, actor)
            session.execute(text('''INSERT INTO kms.source_artifacts(sha256,storage_uri,file_size)
               VALUES(:h,:u,:s) ON CONFLICT DO NOTHING'''), {'h': sha256, 'u': uri, 's': size})
            row = session.execute(text('SELECT sha256,storage_uri,file_size FROM kms.source_artifacts WHERE sha256=:h'), {'h': sha256}).mappings().one()
            if row['file_size'] != size:
                raise Conflict('Source checksum collision or corrupt registry.')
            return dict(row)

    def get_source(self, sha256: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.execute(text('SELECT * FROM kms.source_artifacts WHERE sha256=:h'), {'h': sha256}).mappings().first()
            if row is None:
                raise NotFound('Source artifact not found.')
            return dict(row)

    def register_asset(self, asset: dict[str, Any], *, actor: str) -> dict[str, Any]:
        columns = ('id','original_sha256','transform_profile','original_uri','storage_uri','thumbnail_uri',
                   'image_sha256','thumbnail_sha256','mime_type','file_size','original_size','thumbnail_size','width','height')
        if set(asset) != set(columns):
            raise InvalidState('Unexpected asset metadata contract.')
        with transaction(self.engine) as session:
            context(session, actor)
            session.execute(text('INSERT INTO kms.media_assets (' + ','.join(columns) + ') VALUES (' +
                                 ','.join(':' + name for name in columns) + ') ON CONFLICT DO NOTHING'), asset)
            stored = session.execute(text('SELECT * FROM kms.media_assets WHERE id=:i'), {'i': asset['id']}).mappings().one()
            if any(stored[key] != asset[key] for key in ('image_sha256','thumbnail_sha256','original_sha256')):
                raise Conflict('Asset profile mismatch; do not overwrite immutable media.')
            return {key: stored[key] for key in columns}

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.execute(text('SELECT * FROM kms.media_assets WHERE id=:i'), {'i': asset_id}).mappings().first()
            if row is None:
                raise NotFound('Asset not found.')
            return dict(row)

    def inspect_values(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            rows = session.execute(text('''SELECT v.canonical_name,c.canonical_key,c.label_id,c.standard_unit,
              x.normalized_value,x.status,x.confidence_score,x.version,x.run_id
              FROM kms.variety_character_values x JOIN kms.varieties v ON v.id=x.variety_id
              JOIN kms.characteristics c ON c.id=x.characteristic_id
              ORDER BY v.canonical_name,c.canonical_key LIMIT :l OFFSET :o'''), {'l': limit, 'o': offset}).mappings()
            return [dict(row) for row in rows]
