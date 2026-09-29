from __future__ import annotations

import hashlib
import io

from .client import KmsClient
from src.storage.config import get_settings
from src.storage.errors import InvalidState


def vision_classification_with_storage(state, config):
    """Persist first; inference consumes the exact scrubbed derivative recorded in evidence."""
    import openpyxl
    from src.orchestrator.graph import _resources
    from src.schema.contracts import ImageMetadata
    from src.ui import pipeline_runner as runner

    resources = _resources(config)
    client = KmsClient(get_settings())
    workbook = openpyxl.load_workbook(io.BytesIO(state['workbook_bytes']))
    try:
        worksheet = workbook[runner.SHEET_NAME]
        vision = runner.VisionSession()
        trace = {'error_trace': list(state.get('error_trace', [])), 'provider_trace': list(state.get('provider_trace', []))}
        rows, written = [], 0
        for raw in state.get('image_metadata', []):
            image = ImageMetadata.model_validate(raw)
            # Failure is visible as a failed node; never silently persist a DB reference to a missing file.
            asset = client.request('POST', '/assets/drive/' + image.file_id)
            image_bytes = client.request('GET', f"/media/{asset['id']}/image")
            if hashlib.sha256(image_bytes).hexdigest() != asset['image_sha256']:
                raise InvalidState('Inference media checksum mismatch.')
            model_image = image.model_copy(update={'mime_type': 'image/webp'})
            result, patch = runner.safe_classify_image(
                model_image, vision.knowledge_source_text, vision.varieties, trace,
                image_bytes=image_bytes, vision_rate_limiter=resources.vision_rate_limiter,
            )
            trace.update(patch)
            if result is None:
                rows.append({'filename': image.filename, 'file_id': image.file_id, 'asset_id': asset['id'],
                             'status': 'FAILED', 'write_applied': False, 'write_reason': 'Vision provider/contract failed.'})
                continue
            update = runner.apply_vision_result_to_worksheet(worksheet, image, result)
            written += int(update.applied)
            rows.append({
                'filename': image.filename, 'file_id': image.file_id, 'status': result.classification_status,
                'matched_variety': result.matched_variety, 'identified_part': result.identified_part,
                'confidence': result.confidence, 'visual_evidence': result.visual_evidence,
                'write_applied': update.applied, 'write_reason': update.reason,
                'asset_id': asset['id'], 'original_sha256': asset['original_sha256'],
                'inference_sha256': asset['image_sha256'], 'transform_profile': asset['transform_profile'],
            })
        status = dict(state.get('agent_status', {}))
        status['vision_classification'] = f'{len(rows)} classifications; {written} writes; immutable media captured'
        return {'workbook_bytes': runner._deterministic_workbook_bytes(workbook), 'vision_rows': rows,
                'error_trace': trace['error_trace'], 'provider_trace': trace.get('provider_trace', []), 'agent_status': status}
    finally:
        workbook.close()
