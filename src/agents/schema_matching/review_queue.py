"""Fase 3e — NULL handling & Manual Review Queue.

A SchemaMapping needs a human to look at it when the LLM reranker (Fase 3c)
either couldn't find a confident canonical row (target_canonical_row ==
NULL) or picked one but wasn't sure (confidence below a configurable
threshold). Such mappings are appended to a JSONL queue at data/review/
instead of being silently accepted, and the reason is recorded into
GlobalState.error_trace for traceability.

The queue file is append-only, event-log style: enqueue/approve/revise each
append a new JSON line rather than rewriting existing ones. The "current"
state of an item is always its *latest* line by that item_id — this avoids
in-place file mutation entirely, at the cost of the file growing over time
(acceptable at this project's scale).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from src.schema.contracts import NULL_ROW, SchemaMapping
from src.schema.state import GlobalState

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "review" / "manual_review_queue.jsonl"
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

ReviewStatus = Literal["pending", "approved", "revised"]


class ReviewItem(BaseModel):
    item_id: str
    created_at: datetime
    status: ReviewStatus
    reason: str
    mapping: SchemaMapping
    resolved_by: str | None = None
    resolved_at: datetime | None = None


def needs_review(
    mapping: SchemaMapping, *, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
) -> bool:
    return mapping.target_canonical_row == NULL_ROW or mapping.confidence < confidence_threshold


def _reason_for(mapping: SchemaMapping, confidence_threshold: float) -> str:
    if mapping.target_canonical_row == NULL_ROW:
        return (
            f'atribut "{mapping.source_attribute}" tidak punya padanan baris kanonik '
            f"yang meyakinkan (target=NULL); reasoning LLM: {mapping.reasoning}"
        )
    return (
        f'atribut "{mapping.source_attribute}" -> {mapping.target_canonical_row} punya '
        f"confidence {mapping.confidence:.2f} di bawah ambang {confidence_threshold}"
    )


def _append_line(queue_path: Path, record: dict[str, Any]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read_all(queue_path: Path) -> list[ReviewItem]:
    if not queue_path.exists():
        return []
    items = []
    with queue_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(ReviewItem.model_validate_json(line))
    return items


def _latest_per_item(items: list[ReviewItem]) -> dict[str, ReviewItem]:
    latest: dict[str, ReviewItem] = {}
    for item in items:  # later lines override earlier ones for the same item_id
        latest[item.item_id] = item
    return latest


def enqueue(
    mapping: SchemaMapping,
    *,
    reason: str,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> ReviewItem:
    item = ReviewItem(
        item_id=uuid.uuid4().hex,
        created_at=datetime.now(timezone.utc),
        status="pending",
        reason=reason,
        mapping=mapping,
    )
    _append_line(Path(queue_path), json.loads(item.model_dump_json()))
    return item


def submit_for_review(
    mapping: SchemaMapping,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> ReviewItem | None:
    """Enqueues `mapping` if (and only if) it needs review. Returns the
    ReviewItem, or None if no review was needed."""
    if not needs_review(mapping, confidence_threshold=confidence_threshold):
        return None
    reason = _reason_for(mapping, confidence_threshold)
    return enqueue(mapping, reason=reason, queue_path=queue_path)


def append_error_trace(state: GlobalState, reason: str) -> dict[str, Any]:
    """GlobalState patch — same append-don't-overwrite convention the
    orchestrator's stub nodes use (src/orchestrator/graph.py)."""
    trace = list(state.get("error_trace", []))
    trace.append(reason)
    return {"error_trace": trace}


def process_mapping(
    mapping: SchemaMapping,
    state: GlobalState,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> dict[str, Any]:
    """One call for an orchestrator node: enqueue `mapping` if it needs
    review and return the GlobalState patch recording why. Returns {} if no
    review was needed — nothing to patch."""
    item = submit_for_review(mapping, confidence_threshold=confidence_threshold, queue_path=queue_path)
    if item is None:
        return {}
    return append_error_trace(state, item.reason)


# -- simple human-facing API --------------------------------------------


def list_pending(queue_path: Path | str = DEFAULT_QUEUE_PATH) -> list[ReviewItem]:
    items = _latest_per_item(_read_all(Path(queue_path)))
    return [item for item in items.values() if item.status == "pending"]


def _get_pending_or_raise(item_id: str, queue_path: Path) -> ReviewItem:
    latest = _latest_per_item(_read_all(queue_path))
    item = latest.get(item_id)
    if item is None:
        raise KeyError(f"no review item with id {item_id!r}")
    if item.status != "pending":
        raise ValueError(f"review item {item_id!r} is already {item.status!r}, not pending")
    return item


def approve(
    item_id: str,
    *,
    resolved_by: str | None = None,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> ReviewItem:
    """A human confirms the original mapping was correct after all."""
    queue_path = Path(queue_path)
    item = _get_pending_or_raise(item_id, queue_path)
    resolved = item.model_copy(
        update={
            "status": "approved",
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc),
        }
    )
    _append_line(queue_path, json.loads(resolved.model_dump_json()))
    return resolved


def revise(
    item_id: str,
    corrected_mapping: SchemaMapping,
    *,
    resolved_by: str | None = None,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> ReviewItem:
    """A human replaces the mapping with a corrected one."""
    queue_path = Path(queue_path)
    item = _get_pending_or_raise(item_id, queue_path)
    resolved = item.model_copy(
        update={
            "mapping": corrected_mapping,
            "status": "revised",
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc),
        }
    )
    _append_line(queue_path, json.loads(resolved.model_dump_json()))
    return resolved
