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
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.schema.contracts import NULL_ROW, SchemaMapping
from src.schema.state import GlobalState

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "review" / "manual_review_queue.jsonl"
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

ReviewStatus = Literal["pending", "approved", "revised", "no_match"]


class AcceptanceStatus(str, Enum):
    """The only statuses the canonical write path is allowed to act on."""

    AUTO_ACCEPT = "AUTO_ACCEPT"
    REVIEW = "REVIEW"
    NO_WRITE = "NO_WRITE"


@dataclass(frozen=True)
class MappingAcceptance:
    status: AcceptanceStatus
    reason: str

    @property
    def allows_canonical_write(self) -> bool:
        return self.status is AcceptanceStatus.AUTO_ACCEPT


class ReviewItem(BaseModel):
    item_id: str
    created_at: datetime
    status: ReviewStatus
    reason: str
    mapping: SchemaMapping
    original_mapping: SchemaMapping | None = None
    run_id: str | None = None
    mapping_item_id: str | None = None
    source_file_name: str | None = None
    source_file_sha256: str | None = None
    source_sheet: str | None = None
    source_format: str | None = None
    source_attribute_display: str | None = None
    source_attribute_id: str | None = None
    mapping_identity_kind: str | None = None
    mapping_identity_value: str | None = None
    schema_version: str | None = None
    template_hash: str | None = None
    proposed_canonical_key: str | None = None
    mapping_method: str | None = None
    verifier_status: str | None = None
    verifier_warnings: list[str] = Field(default_factory=list)
    verifier_hard_issues: list[str] = Field(default_factory=list)
    sample_values: list[str] = Field(default_factory=list)
    raw_values_by_variety: dict[str, list[str]] = Field(default_factory=dict)
    source_cells_by_variety: dict[str, list[str]] = Field(default_factory=dict)
    source_header_cells: list[str] = Field(default_factory=list)
    source_ir_version: str | None = None
    final_canonical_key: str | None = None
    resolution_notes: str | None = None
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


def decide_mapping_acceptance(
    mapping: SchemaMapping | None,
    *,
    reliability_patch: dict[str, Any] | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> MappingAcceptance:
    """Return the single, deterministic commit decision for one mapping.

    Fail closed: an absent mapping, a mapping covered by the existing review
    rules, or any reliability-layer patch cannot reach canonical mutation.
    The patch check also protects callers when a wrapper adds a new review
    condition without simultaneously changing this function.
    """
    trace = list((reliability_patch or {}).get("error_trace", []))
    patch_reason = trace[-1] if trace else None

    if mapping is None:
        return MappingAcceptance(
            AcceptanceStatus.NO_WRITE,
            patch_reason or "reliability layer produced no valid schema mapping",
        )
    if needs_review(mapping, confidence_threshold=confidence_threshold):
        return MappingAcceptance(
            AcceptanceStatus.REVIEW,
            patch_reason or _reason_for(mapping, confidence_threshold),
        )
    if reliability_patch:
        return MappingAcceptance(
            AcceptanceStatus.REVIEW,
            patch_reason or "reliability layer requires manual review",
        )
    return MappingAcceptance(
        AcceptanceStatus.AUTO_ACCEPT,
        f"valid non-NULL mapping with confidence {mapping.confidence:.2f}",
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
    **context: Any,
) -> ReviewItem:
    run_id = context.get("run_id")
    mapping_item_id = context.get("mapping_item_id")
    source_attribute_id = context.get("source_attribute_id")
    if run_id and (mapping_item_id or source_attribute_id):
        identity = mapping_item_id or source_attribute_id
        item_id = hashlib.sha256(f"{run_id}|{identity}".encode("utf-8")).hexdigest()
    else:
        item_id = uuid.uuid4().hex
    item = ReviewItem(
        item_id=item_id,
        created_at=datetime.now(timezone.utc),
        status="pending",
        reason=reason,
        mapping=mapping,
        original_mapping=mapping,
        **context,
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
    decision = decide_mapping_acceptance(mapping, confidence_threshold=confidence_threshold)
    if decision.status is not AcceptanceStatus.REVIEW:
        return {}
    item = enqueue(mapping, reason=decision.reason, queue_path=queue_path)
    return append_error_trace(state, item.reason)


# -- simple human-facing API --------------------------------------------


def list_for_run(
    run_id: str, queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> list[ReviewItem]:
    items = _latest_per_item(_read_all(Path(queue_path)))
    return [item for item in items.values() if item.run_id == run_id]


def list_pending(
    queue_path: Path | str = DEFAULT_QUEUE_PATH, *, run_id: str | None = None,
) -> list[ReviewItem]:
    items = _latest_per_item(_read_all(Path(queue_path)))
    return [
        item for item in items.values()
        if item.status == "pending" and (run_id is None or item.run_id == run_id)
    ]


def _get_pending_or_raise(
    item_id: str, queue_path: Path, expected_run_id: str | None = None,
) -> ReviewItem:
    latest = _latest_per_item(_read_all(queue_path))
    item = latest.get(item_id)
    if item is None:
        raise KeyError(f"no review item with id {item_id!r}")
    if item.status != "pending":
        raise ValueError(f"review item {item_id!r} is already {item.status!r}, not pending")
    if expected_run_id is not None and item.run_id != expected_run_id:
        raise ValueError(
            f"review item {item_id!r} belongs to run {item.run_id!r}, not {expected_run_id!r}"
        )
    return item


def approve(
    item_id: str,
    *,
    resolved_by: str | None = None,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
    expected_run_id: str | None = None,
    notes: str | None = None,
) -> ReviewItem:
    """A human confirms the original mapping was correct after all."""
    queue_path = Path(queue_path)
    item = _get_pending_or_raise(item_id, queue_path, expected_run_id)
    if item.run_id is not None and not item.proposed_canonical_key:
        raise ValueError(
            "a run-bound review item without a proposed canonical target cannot be "
            "approved; revise it to a valid canonical key or mark it NO_MATCH"
        )
    resolved = item.model_copy(
        update={
            "status": "approved",
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc),
            "final_canonical_key": item.proposed_canonical_key,
            "resolution_notes": notes,
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
    expected_run_id: str | None = None,
    final_canonical_key: str | None = None,
    schema=None,
    notes: str | None = None,
) -> ReviewItem:
    """A human replaces the mapping with a corrected one."""
    queue_path = Path(queue_path)
    item = _get_pending_or_raise(item_id, queue_path, expected_run_id)
    original = item.original_mapping or item.mapping
    if corrected_mapping.source_attribute != original.source_attribute:
        raise ValueError("corrected mapping must retain the review item's source attribute")
    if item.run_id is not None:
        if not final_canonical_key:
            raise ValueError("a run-bound revised review item requires a final canonical key")
        if schema is None:
            from src.schema.canonical import CanonicalSchema

            schema = CanonicalSchema.from_template()
        target = schema.row_by_key(final_canonical_key)
        if target is None:
            raise ValueError(f"unknown canonical_key: {final_canonical_key!r}")
        if corrected_mapping.target_canonical_row != target.id:
            raise ValueError(
                "corrected mapping target does not match the supplied final canonical key"
            )
    resolved = item.model_copy(
        update={
            "mapping": corrected_mapping,
            "status": "revised",
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc),
            "final_canonical_key": final_canonical_key,
            "resolution_notes": notes,
        }
    )
    _append_line(queue_path, json.loads(resolved.model_dump_json()))
    return resolved


def revise_to_canonical_key(
    item_id: str,
    canonical_key: str,
    *,
    schema,
    resolved_by: str | None = None,
    notes: str | None = None,
    expected_run_id: str | None = None,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> ReviewItem:
    """Resolve a pending item to a validated key from the active schema."""
    target = schema.row_by_key(canonical_key)
    if target is None:
        raise ValueError(f"unknown canonical_key: {canonical_key!r}")
    item = _get_pending_or_raise(item_id, Path(queue_path), expected_run_id)
    original = item.original_mapping or item.mapping
    corrected = original.model_copy(update={
        "target_canonical_row": target.id,
        "reasoning": f"Human review selected canonical key {canonical_key!r}.",
    })
    return revise(
        item_id, corrected, resolved_by=resolved_by, queue_path=queue_path,
        expected_run_id=expected_run_id, final_canonical_key=canonical_key,
        schema=schema, notes=notes,
    )


def mark_no_match(
    item_id: str,
    *,
    resolved_by: str | None = None,
    notes: str | None = None,
    expected_run_id: str | None = None,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
) -> ReviewItem:
    """Resolve a pending item explicitly as having no canonical target."""
    queue = Path(queue_path)
    item = _get_pending_or_raise(item_id, queue, expected_run_id)
    resolved = item.model_copy(update={
        "status": "no_match", "resolved_by": resolved_by,
        "resolved_at": datetime.now(timezone.utc), "final_canonical_key": None,
        "resolution_notes": notes,
    })
    _append_line(queue, json.loads(resolved.model_dump_json()))
    return resolved
