from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.storage.config import get_settings
from .adapter import snapshot_result
from .client import KmsClient, enabled


def run_pipeline_with_kms(file_path, *, kms_source_filename=None, **kwargs):
    """Keep the existing LangGraph pipeline; add durable source/output capture."""
    from src.ui.pipeline_runner import run_pipeline_ui
    if not enabled():
        return run_pipeline_ui(file_path, **kwargs)
    settings = get_settings()
    client = KmsClient(settings)
    path = Path(file_path)
    if path.stat().st_size > settings.source_max_bytes:
        raise ValueError('Source exceeds configured byte limit.')
    source = client.source(path.read_bytes())
    if 'review_queue_path' not in kwargs:
        queue_dir = Path('data/review/kms_runs')
        queue_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
        kwargs['review_queue_path'] = queue_dir / f'{uuid.uuid4().hex}.jsonl'
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    result = run_pipeline_ui(file_path, **kwargs)
    duration = int((time.monotonic() - tick) * 1000)
    output = client.source(result.workbook_bytes)
    result._kms_context = {
        'source_sha256': source['sha256'], 'source_uri': source['storage_uri'],
        'source_filename': kms_source_filename or path.name,
        'started_at': started, 'duration_ms': duration,
        'provider_manifest': json.loads(os.getenv('KMS_PROVIDER_MANIFEST_JSON', '{}')),
        'original_result': snapshot_result(result, output['sha256']),
    }
    from src.schema.canonical import CanonicalSchema
    from src.agents.schema_matching import review_queue
    from .adapter import build_draft, load_overrides
    from .streamlit_commit import image_links
    draft = build_draft(result, result, CanonicalSchema.from_template(),
                        review_queue.list_for_run(result.run_id, result.review_queue_path),
                        source_filename=kms_source_filename or path.name,
                        source_scope=os.getenv('KMS_SOURCE_SCOPE', 'cabai-research'),
                        context=result._kms_context, images=image_links(result), overrides=load_overrides())
    saved = client.request('POST', '/runs/stage', json={'draft': draft.ordered_payload(), 'expected_revision': 0})
    result._kms_revision = saved['revision']
    return result
