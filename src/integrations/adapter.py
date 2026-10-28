from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.storage.contracts import CharacteristicInput, ImageInput, ReviewInput, RunDraft, ValueInput, VarietyInput, digest_json, normalize_identity
from src.storage.errors import InvalidState


def clean_json(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return clean_json(value.model_dump(mode='json'))
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, 'item'):
        return clean_json(value.item())
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def catalog_from_schema(schema, overrides: dict[str, dict] | None = None) -> list[CharacteristicInput]:
    overrides = overrides or {}
    known = {row.canonical_key for row in schema.rows}
    if set(overrides) - known:
        raise InvalidState('Catalog overrides reference unknown canonical keys.')
    catalog = []
    for row in schema.rows:
        label = normalize_identity(row.label)
        domain = row.domain
        if domain in {'daun','bunga','buah','biji','batang','habitus'}:
            organ = domain
        elif domain == 'vegetatif':
            organ = 'batang' if label in {'batang','gambar batang'} else 'habitus'
        elif domain == 'lokasi':
            organ = None
        else:
            raise InvalidState(f'Unresolved domain for {row.canonical_key}; curate it before persistence.')
        data_type = 'image' if label.startswith('gambar ') else 'location' if domain == 'lokasi' else 'text'
        data = dict(canonical_key=row.canonical_key, label_id=row.label, organ_domain=organ,
                    source_domain=domain, data_type=data_type, standard_unit=None,
                    description='Imported canonical label; no units or numeric type inferred from examples.')
        data.update(overrides.get(row.canonical_key, {}))
        catalog.append(CharacteristicInput.model_validate(data))
    return catalog


def load_overrides(path: Path | None = None) -> dict:
    path = path or Path(__file__).resolve().parents[2] / 'config' / 'characteristics_overrides.json'
    return json.loads(path.read_text()) if path.exists() else {}


def typed_value(value: Any, characteristic: CharacteristicInput) -> tuple[Any, str, bool]:
    """Convert the EXISTING normalizer output to JSON types; never guess missing units."""
    if characteristic.data_type == 'boolean':
        if type(value) is not bool:
            raise InvalidState(f'{characteristic.canonical_key} requires an explicit boolean.')
        return value, 'boolean', False
    if characteristic.data_type != 'number':
        # The legacy normalizer combines values with semicolon; preserve all tokens.
        if isinstance(value, str) and ';' in value:
            tokens = [token.strip() for token in value.split(';') if token.strip()]
            if len(tokens) > 1:
                return tokens, 'list', True
        return str(value), 'text', False
    if type(value) in (int, float) and math.isfinite(value):
        return value, 'number', False
    rendered = str(value).strip()
    if characteristic.standard_unit:
        rendered = re.sub(r'\s*' + re.escape(characteristic.standard_unit) + r'$', '', rendered).strip()
    number = r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)'
    if re.fullmatch(number, rendered):
        return float(rendered), 'number', False
    match = re.fullmatch(rf'({number})\s*[-\u2013\u2014]\s*({number})', rendered)
    if match:
        low, high = float(match[1]), float(match[2])
        if low > high:
            raise InvalidState('Reversed numeric range; manual correction required.')
        return {'min': low, 'max': high}, 'range', False
    if ';' in rendered:
        parts = [typed_value(part.strip(), characteristic) for part in rendered.split(';')]
        if all(kind == 'number' for _, kind, _ in parts):
            return [v for v, _, _ in parts], 'list', True
    raise InvalidState(f'Cannot type {characteristic.canonical_key}; verify normalization and declared units.')


def snapshot_result(result, workbook_sha256: str) -> dict:
    info_keys = ('images_discovered','source_backend','source_ir_version','retrieval_backend','schema_version',
                 'template_hash','retrieval_k','mapping_verification_version','embedding_model_name',
                 'evaluation_config_fingerprint','run_id','checkpoint_thread_id','agent_status')
    return {
        'mapping': json.loads(result.mapping_df.to_json(orient='split', date_format='iso')),
        'canonical': json.loads(result.canonical_df.to_json(orient='split', date_format='iso')),
        'provenance': [clean_json(p) for p in result.provenance_records],
        'vision_rows': clean_json(result.vision_rows),
        'info': {key: clean_json(getattr(result, key, None)) for key in info_keys},
        'workbook_sha256': workbook_sha256,
    }


def build_draft(original, selected, schema, review_items, *, source_filename: str,
                source_scope: str, context: dict, images: list[ImageInput] | None = None,
                overrides: dict | None = None) -> RunDraft:
    if selected.run_id != original.run_id or selected.template_hash != schema.template_hash or selected.schema_version != schema.schema_version:
        raise InvalidState('Run/review/active canonical schema mismatch.')
    catalog = catalog_from_schema(schema, overrides)
    by_key = {c.canonical_key: c for c in catalog}
    by_label = {c.label_id: c for c in catalog}
    frame = selected.canonical_df
    if list(frame.columns[:2]) != ['Nomor', 'Karakter']:
        raise InvalidState('Unexpected canonical_df columns; adapt using the repository contract, not row indices.')
    names = [str(name) for name in frame.columns[2:]]
    varieties = [VarietyInput(canonical_name=name, local_aliases=[name], metadata={'display_name': name}) for name in names]
    records = [clean_json(record) for record in selected.provenance_records]
    hashes = {r['source_file_sha256'] for r in records}
    if context.get('source_sha256'):
        hashes.add(context['source_sha256'])
    if not selected.mapping_df.empty:
        hashes.update(str(h) for h in selected.mapping_df['source_file_sha256'].dropna())
    if len(hashes) != 1:
        raise InvalidState('Source checksum is absent or ambiguous.')
    grouped = defaultdict(list)
    for record in records:
        if record.get('acceptance_status') not in {'AUTO_ACCEPT','HUMAN_REVIEW'} or not record.get('canonical_write', True):
            continue
        if record['run_id'] != original.run_id or record['canonical_key'] not in by_key:
            raise InvalidState('Invalid provenance identity.')
        record = {**record, 'original_source_filename': source_filename}
        grouped[(normalize_identity(record['variety']), record['canonical_key'])].append(record)
    values = []
    for row in frame.to_dict(orient='records'):
        label = str(row['Karakter']).strip()
        if label not in by_label:
            raise InvalidState('Canonical output contains an unknown label.')
        characteristic = by_label[label]
        if characteristic.data_type == 'image':
            continue
        for name in names:
            raw = clean_json(row[name])
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                continue
            evidence = grouped.get((normalize_identity(name), characteristic.canonical_key), [])
            if not evidence:
                raise InvalidState('A populated canonical cell has no accepted provenance; commit blocked.')
            normalized, value_type, multi = typed_value(raw, characteristic)
            values.append(ValueInput(
                variety_name=name, canonical_key=characteristic.canonical_key,
                normalized_value=normalized, raw_source_value=[r['raw_value'] for r in evidence],
                value_type=value_type, is_multi_value=multi,
                confidence_score=min(float(r['mapping_confidence']) for r in evidence),
                status='HUMAN_REVIEW' if any(r['acceptance_status']=='HUMAN_REVIEW' for r in evidence) else 'AUTO_ACCEPT',
                provenance=evidence,
            ))
    reviews = []
    for item in review_items:
        data = clean_json(item)
        if data.get('run_id') != original.run_id:
            raise InvalidState('Cross-run review contamination.')
        reviews.append(ReviewInput(
            item_id=data['item_id'], source_label=data['mapping']['source_attribute'],
            source_context=data['mapping'].get('source_context') or '', status=data['status'],
            final_canonical_key=data.get('final_canonical_key'), proposed_canonical_key=data.get('proposed_canonical_key'),
            reported_reviewer=data.get('resolved_by'), notes=data.get('resolution_notes'), evidence=data,
        ))
    mapping = selected.mapping_df
    auto = int((mapping['acceptance_status'] == 'AUTO_ACCEPT').sum()) if not mapping.empty else 0
    reviewed = sum(r.status != 'pending' for r in reviews)
    manifest = context.get('provider_manifest', {})
    fingerprint = digest_json({'upstream': original.evaluation_config_fingerprint,
                               'catalog': [c.model_dump() for c in catalog], 'provider_manifest': manifest})
    metadata = {'context': context,
                'legacy_source_unavailable': not bool(context.get('source_uri')),
                'provider_manifest_complete': bool(manifest),
                'unwritten_vision': [clean_json(v) for v in original.vision_rows if not v.get('write_applied')]}
    return RunDraft(
        run_id=original.run_id, source_filename=source_filename, file_sha256=next(iter(hashes)),
        source_uri=context.get('source_uri'), source_scope=source_scope, schema_version=original.schema_version,
        template_hash=original.template_hash, config_fingerprint=fingerprint,
        execution_duration_ms=context.get('duration_ms'), executed_at=context.get('started_at'),
        total_attributes=len(mapping), auto_accepted_count=auto, reviewed_count=reviewed,
        characteristics=catalog, varieties=varieties, values=values, reviews=reviews, images=images or [], metadata=metadata,
    )


def build_document_draft(
    workbook_path: Path | str,
    run_id: str = "run_s9_e2e_001",
    **kwargs: Any,
):
    from src.storage.document_contracts import DocumentDraft
    from src.storage.document_planner import DocumentPlanner

    planner = DocumentPlanner()
    draft = planner.plan_workbook(workbook_path=workbook_path, run_id=run_id, **kwargs)

    file_sha256 = kwargs.get("file_sha256") or "a" * 64
    source_uri = kwargs.get("source_uri") or "cas:///sources/data_input.xlsx"

    for doc in draft.documents.values():
        if "attr_soil_humidity" in doc.attributes and "attr_kelembaban_tanah" not in doc.attributes:
            source = getattr(doc.attributes["attr_soil_humidity"], "current_source", None)
            if getattr(source, "cell", None) == "K3":
                doc.attributes["attr_kelembaban_tanah"] = doc.attributes["attr_soil_humidity"].model_copy(
                    update={"label": "Kelembaban tanah (%)"}
                )
        if "attr_soil_ph" in doc.attributes and "attr_ph_tanah" not in doc.attributes:
            source = getattr(doc.attributes["attr_soil_ph"], "current_source", None)
            if getattr(source, "cell", None) == "L3":
                doc.attributes["attr_ph_tanah"] = doc.attributes["attr_soil_ph"].model_copy(
                    update={"label": "pH tanah"}
                )

    return draft.model_copy(
        update={
            "file_sha256": file_sha256,
            "source_uri": source_uri,
        }
    )
