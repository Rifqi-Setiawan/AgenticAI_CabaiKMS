from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .client import enabled


class ReviewQueueProxy:
    """DB acknowledgement first, append-only JSONL projection second; no global monkeypatch."""
    def __getattr__(self, name):
        from src.agents.schema_matching import review_queue as original_queue
        function = getattr(original_queue, name)
        if name not in {'approve','revise_to_canonical_key','mark_no_match'}:
            return function

        def wrapped(*args, **kwargs):
            if not enabled():
                return function(*args, **kwargs)
            import fcntl
            from src.ui import state
            from src.schema.canonical import CanonicalSchema
            from .streamlit_commit import persist_current_draft
            original = state.get_result()
            destination = Path(kwargs.get('queue_path') or original.review_queue_path)
            items = original_queue.list_for_run(original.run_id, destination)
            with tempfile.TemporaryDirectory(prefix='kms-review-') as directory:
                temporary = Path(directory) / 'review.jsonl'
                temporary.write_text(''.join(item.model_dump_json() + '\n' for item in items), encoding='utf-8')
                resolved = function(*args, **{**kwargs, 'queue_path': temporary})
                new_items = original_queue.list_for_run(original.run_id, temporary)
                persist_current_draft(original, CanonicalSchema.from_template(), new_items, state.get_last_inputs(), queue_path=temporary)
            # A crash after DB commit is recoverable from the saved revision, even before this projection.
            destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            fd = os.open(destination, os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as output:
                fcntl.flock(output, fcntl.LOCK_EX)
                output.write(resolved.model_dump_json() + '\n')
                output.flush()
                os.fsync(output.fileno())
            return resolved
        return wrapped


review_queue = ReviewQueueProxy()
