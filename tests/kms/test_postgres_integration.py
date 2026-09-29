"""Real PostgreSQL tests, never replaced with SQLite. Database name MUST end in _test."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from src.storage.config import Settings
from src.storage.contracts import RunDraft
from src.storage.db import make_engine, transaction
from src.storage.errors import Conflict, InvalidState
from src.storage.learning import LearningRepository
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository, context

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL not configured; a real disposable PostgreSQL server is required.')
    if not (make_url(url).database or '').endswith('_test'):
        pytest.fail('Refusing integration tests on a database whose name does not end with _test.')
    pytest.importorskip('psycopg')
    admin_url = os.getenv('TEST_DATABASE_ADMIN_URL', url)
    if make_url(admin_url).database != make_url(url).database:
        pytest.fail('Runtime/admin test URLs must target the same disposable database.')
    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


@pytest.fixture
def ready(db, draft):
    repo = KmsRepository(db)
    source = repo.register_source('a'*64, 'cas:///sources/aa/aa/' + 'a'*64 + '.xlsx', 123, actor='test-reviewer')
    payload = draft.model_dump()
    payload.update(run_id=uuid4().hex, source_uri=source['storage_uri'], metadata={})
    payload['varieties'][0]['canonical_name'] = 'test_' + uuid4().hex
    payload['values'][0]['variety_name'] = payload['varieties'][0]['canonical_name']
    return repo, RunDraft.model_validate(payload)


def do_commit(repo, draft):
    result = repo.stage(draft, expected_revision=0, actor='test-reviewer')
    return repo.commit(draft.run_id, result['revision'], result['payload_sha256'], actor='test-reviewer')


def test_commit_replay_and_single_outbox(db, ready):
    repo, draft = ready
    first = do_commit(repo, draft)
    second = do_commit(repo, draft)
    assert first['replayed'] is False and second['replayed'] is True
    with db.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM kms.outbox_events WHERE run_id=:r'), {'r': draft.run_id}) == 1
        assert conn.scalar(text('SELECT count(*) FROM kms.value_observations WHERE run_id=:r'), {'r': draft.run_id}) == 1


def test_concurrent_same_commit_is_idempotent(ready):
    repo, draft = ready
    stage = repo.stage(draft, expected_revision=0, actor='test-reviewer')
    def attempt(_):
        return repo.commit(draft.run_id, stage['revision'], stage['payload_sha256'], actor='test-reviewer')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(item['replayed'] for item in results) == [False, True]


def test_stale_draft_rejected(ready):
    repo, draft = ready
    repo.stage(draft, expected_revision=0, actor='test-reviewer')
    modified = draft.model_dump()
    modified['metadata']['comment'] = 'new annotation'
    with pytest.raises(Conflict):
        repo.stage(RunDraft.model_validate(modified), expected_revision=0, actor='test-reviewer')


def test_pending_review_blocks_all_writes(db, ready):
    repo, draft = ready
    payload = draft.model_dump()
    payload.update(total_attributes=2)
    payload['reviews'] = [dict(item_id='p1', source_label='unknown', status='pending')]
    pending = RunDraft.model_validate(payload)
    with pytest.raises(InvalidState):
        do_commit(repo, pending)
    with db.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM kms.value_observations WHERE run_id=:r'), {'r': pending.run_id}) == 0


def test_two_runs_projection_conflict_rolls_back(db, ready):
    repo, one = ready
    payload = one.model_dump()
    payload['run_id'] = uuid4().hex
    payload['values'][0]['normalized_value'] = 6.0
    two = RunDraft.model_validate(payload)
    staged = repo.stage(two, expected_revision=0, actor='test-reviewer')
    do_commit(repo, one)
    with pytest.raises(Conflict):
        repo.commit(two.run_id, staged['revision'], staged['payload_sha256'], actor='test-reviewer')
    with db.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM kms.value_observations WHERE run_id=:r'), {'r': two.run_id}) == 0
    rebased = repo.rebase(two.run_id, staged['revision'], 'Reviewed both observations; replace current projection.', actor='test-curator')
    assert repo.commit(two.run_id, rebased['revision'], rebased['payload_sha256'], actor='test-curator')['replayed'] is False


def test_human_projection_not_demoted(db, ready):
    repo, draft = ready
    payload = draft.model_dump()
    payload['values'][0]['status'] = 'HUMAN_REVIEW'
    human = RunDraft.model_validate(payload)
    do_commit(repo, human)
    payload = draft.model_dump()
    payload['run_id'] = uuid4().hex
    auto = RunDraft.model_validate(payload)
    receipt = do_commit(repo, auto)
    assert receipt['reviewed_values_protected'] == 1
    with db.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM kms.value_observations WHERE run_id=:r'), {'r': auto.run_id}) == 1


def test_review_is_monotone(ready):
    repo, draft = ready
    payload = draft.model_dump()
    payload.update(total_attributes=2)
    payload['reviews'] = [dict(item_id='p1', source_label='fruit len', status='pending')]
    pending = RunDraft.model_validate(payload)
    saved = repo.stage(pending, expected_revision=0, actor='test-reviewer')
    final = pending.model_dump()
    final['reviews'][0].update(status='revised', final_canonical_key='panjang_buah')
    final['reviewed_count'] = 1
    resolved = repo.stage(RunDraft.model_validate(final), expected_revision=saved['revision'], actor='test-reviewer')
    with pytest.raises(Conflict):
        repo.stage(pending, expected_revision=resolved['revision'], actor='test-reviewer')


def test_append_only_trigger(db, ready):
    repo, draft = ready
    do_commit(repo, draft)
    with pytest.raises(DBAPIError):
        with transaction(db) as session:
            context(session, 'test-reviewer', draft.run_id)
            session.execute(text("UPDATE kms.value_observations SET evidence='{}'::jsonb WHERE run_id=:r"), {'r': draft.run_id})


def test_gold_alias_promotion_and_scoping(db, ready):
    repo, draft = ready
    payload = draft.model_dump()
    label = 'length_' + uuid4().hex
    payload.update(total_attributes=2, reviewed_count=1)
    payload['reviews'] = [dict(item_id='g1', source_label=label, source_context='fruit', status='revised', final_canonical_key='panjang_buah')]
    reviewed = RunDraft.model_validate(payload)
    do_commit(repo, reviewed)
    with db.connect() as conn:
        gold = conn.scalar(text('SELECT id FROM kms.gold_examples WHERE run_id=:r'), {'r': reviewed.run_id})
    learning = LearningRepository(db)
    alias_id = learning.promote(gold, 'evaluation:heldout-test-suite-v1', 'Curator approved exact scoped alias after evaluation.', actor='test-curator')
    assert alias_id
    assert learning.resolve(reviewed.source_scope, reviewed.template_hash, label, 'fruit', schema_version=reviewed.schema_version) == 'panjang_buah'
    assert learning.resolve('different-team', reviewed.template_hash, label, 'fruit', schema_version=reviewed.schema_version) is None


def test_missing_source_rejected_by_default(ready):
    repo, draft = ready
    payload = draft.model_dump()
    payload['source_uri'] = None
    payload['metadata'] = {'legacy_source_unavailable': True}
    with pytest.raises(InvalidState):
        do_commit(repo, RunDraft.model_validate(payload))
