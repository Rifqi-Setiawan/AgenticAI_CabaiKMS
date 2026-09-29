from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from src.storage.config import get_settings
from src.storage.contracts import ImageInput, canonical_json
from src.storage.errors import InvalidState
from .adapter import build_draft, load_overrides, snapshot_result
from .client import enabled, ui_client


def image_links(result) -> list[ImageInput]:
    links = []
    for row in result.vision_rows:
        if row.get('status') != 'KNOWN' or not row.get('write_applied'):
            continue
        if not row.get('asset_id'):
            raise InvalidState('Legacy vision has no immutable asset identity. Re-run with the storage vision hook; filename is not an ID.')
        links.append(ImageInput(variety_name=row['matched_variety'], organ_part=row['identified_part'].lower(),
                                asset_id=row['asset_id'], vision_confidence=row['confidence'], vision_evidence=row))
    return links


def persist_current_draft(original, schema, items, last_inputs, *, queue_path=None):
    from src.ui.review_replay import apply_review_corrections
    client = ui_client()
    context = getattr(original, '_kms_context', {})
    if not context.get('original_result'):
        output = client.source(original.workbook_bytes)
        context = {**context, 'original_result': snapshot_result(original, output['sha256'])}
        original._kms_context = context
    resolved = all(item.status != 'pending' for item in items)
    selected = apply_review_corrections(original, queue_path=queue_path) if items and resolved else original
    draft = build_draft(original, selected, schema, items,
                        source_filename=last_inputs.get('filename') or context.get('source_filename') or 'legacy.xlsx',
                        source_scope=os.getenv('KMS_SOURCE_SCOPE', 'cabai-research'), context=context,
                        images=image_links(original), overrides=load_overrides())
    saved = client.request('POST', '/runs/stage', json={'draft': draft.ordered_payload(),
                            'expected_revision': getattr(original, '_kms_revision', 0)})
    original._kms_revision = saved['revision']
    return saved


def render_commit_panel(original, schema, current_run_items, last_inputs):
    import streamlit as st
    if not enabled():
        return
    st.divider()
    st.subheader('PostgreSQL KMS')
    settings = get_settings()
    if settings.kms_api_token is None:
        st.text_input('Token reviewer KMS', type='password', key='kms_reviewer_token')
        if not st.session_state.get('kms_reviewer_token'):
            st.info('Masukkan token reviewer. Token tidak dimasukkan ke URL atau workbook.')
            return
    try:
        saved = persist_current_draft(original, schema, current_run_items, last_inputs)
        pending = sum(item.status == 'pending' for item in current_run_items)
        st.caption(f"Draft pusat: {saved['run_id']} | revisi {saved['revision']} | {pending} review tertunda")
        if not getattr(original, '_kms_context', {}).get('source_uri'):
            st.warning('Run lama: file sumber belum diarsipkan. Commit ditolak secara default; unggah ulang sumber asli atau gunakan migrasi legacy yang disetujui administrator.')
        if st.button('\U0001f4be Commit & Sinkronkan ke PostgreSQL KMS', disabled=bool(pending), type='primary'):
            receipt = ui_client().request('POST', f'/runs/{original.run_id}/commit',
                                         json={'expected_revision': saved['revision'], 'payload_sha256': saved['payload_sha256']})
            st.session_state['kms_commit_receipt'] = receipt
        receipt = st.session_state.get('kms_commit_receipt') or saved.get('receipt')
        if receipt and receipt['run_id'] == original.run_id:
            prefix = 'Commit sudah tercatat; tidak ada penulisan ulang.' if receipt.get('replayed') else 'Commit berhasil.'
            st.success(f"{prefix} {receipt['rows_upserted']} baris proyeksi, {receipt['observations_inserted']} observasi, "
                       f"{receipt['images_linked']} foto. {receipt['reviewed_values_protected']} nilai terverifikasi dilindungi.")
            st.page_link('pages/4_KMS.py', label='Inspect data PostgreSQL KMS')
    except Exception as error:
        # Never render an exception repr containing DSNs, HTTP headers or raw SQL.
        from src.storage.errors import KmsError
        message = str(error) if isinstance(error, KmsError) else type(error).__name__
        st.error('Sinkronisasi belum diakui KMS. Hasil asli tetap tersedia. ' + message)


def restore_from_saved(saved: dict, client):
    import pandas as pd
    from src.schema.provenance import CellProvenanceRecord
    from src.schema.canonical import CanonicalSchema
    from src.agents.schema_matching.review_queue import ReviewItem
    from src.ui.pipeline_runner import PipelineRunResult
    draft = saved['draft']
    active = CanonicalSchema.from_template()
    if active.template_hash != draft['template_hash'] or active.schema_version != draft['schema_version']:
        raise InvalidState('Install the matching versioned canonical template before recovering this run.')
    context = draft['metadata']['context']
    snapshot = context.get('original_result')
    if not snapshot:
        raise InvalidState('This legacy draft has no recoverable original snapshot.')
    payload = client.request('GET', '/sources/' + snapshot['workbook_sha256'])
    import hashlib
    if hashlib.sha256(payload).hexdigest() != snapshot['workbook_sha256']:
        raise InvalidState('Recovered workbook checksum mismatch.')
    queue_dir = Path('data/review/kms_recovered')
    queue_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    queue = queue_dir / f'{uuid.uuid4().hex}.jsonl'
    with queue.open('x', encoding='utf-8') as output:
        os.chmod(queue, 0o600)
        for review in draft['reviews']:
            item = ReviewItem.model_validate(review['evidence'])
            output.write(item.model_dump_json() + '\n')
        output.flush()
        os.fsync(output.fileno())
    def frame(data):
        return pd.DataFrame(data['data'], columns=data['columns'], index=data['index'])
    result = PipelineRunResult(mapping_df=frame(snapshot['mapping']), canonical_df=frame(snapshot['canonical']),
                               workbook_bytes=payload, vision_rows=snapshot['vision_rows'],
                               provenance_records=[CellProvenanceRecord.model_validate(p) for p in snapshot['provenance']],
                               review_queue_path=str(queue), **snapshot['info'])
    result._kms_context, result._kms_revision = context, saved['revision']
    return result


def render_inspector():
    import streamlit as st
    st.set_page_config(page_title='KMS tersimpan', layout='wide')
    st.title('Data KMS tersimpan')
    if not enabled():
        st.info('KMS_ENABLED belum aktif.')
        return
    if get_settings().kms_api_token is None:
        st.text_input('Token reviewer KMS', type='password', key='kms_reviewer_token')
    try:
        client = ui_client()
        offset = st.number_input('Offset data', min_value=0, value=0, step=100)
        data = client.request('GET', f'/values?limit=100&offset={offset}')
        st.dataframe(data['items'], width='stretch')
        run_id = st.text_input('Run ID untuk inspeksi / pemulihan')
        if st.button('Buka run tersimpan', disabled=not bool(run_id)):
            from src.storage.contracts import RunDraft
            saved = client.request('GET', '/runs/' + run_id)
            RunDraft.model_validate(saved['draft'])
            st.session_state['kms_saved_run'] = saved
        saved = st.session_state.get('kms_saved_run')
        if saved:
            st.json({k: v for k, v in saved.items() if k not in {'draft','base_versions'}})
            if st.button('Pulihkan ke halaman Hasil'):
                from src.ui import state
                result = restore_from_saved(saved, client)
                state.set_result(result)
                state.clear_corrected_result()
                state.set_last_inputs(filename=saved['draft']['source_filename'], source_format='recovered', drive_url='')
                st.success('Snapshot asli dan review dipulihkan; model tidak dijalankan ulang.')
                st.page_link('pages/3_Hasil.py', label='Buka Hasil')
    except Exception as error:
        from src.storage.errors import KmsError
        st.error(str(error) if isinstance(error, KmsError) else type(error).__name__)
