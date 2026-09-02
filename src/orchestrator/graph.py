"""Fase 2 — orchestrator skeleton (LangGraph StateGraph).

All nodes are stubs: they log, then fill GlobalState with dummy-but-valid
contract objects (SchemaMapping/ImageMetadata/VisionResult from Fase 1). No
node in this module calls an LLM, a vision model, or the Drive API — that
wiring lands once the real agents exist. The point of this fase is the
graph shape, the state flow, the verify-then-revise conditional edge, and
checkpoint/resume, all provable without any network calls.

Node order (per the proposal):
    schema_matching -> drive_crawler -> vision_classification
        -> [conditional: retry / manual_review / continue]
        -> tabular_update -> finalization
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.schema.canonical import CanonicalSchema
from src.schema.contracts import ImageMetadata, SchemaMapping, VisionResult
from src.schema.state import GlobalState

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT_DB = PROJECT_ROOT / "data" / ".checkpoints" / "orchestrator.sqlite"

# verify-then-revise thresholds
LOW_CONFIDENCE_THRESHOLD = 0.6
MAX_VISION_RETRIES = 2

NODE_ORDER = (
    "schema_matching",
    "drive_crawler",
    "vision_classification",
    "tabular_update",
    "finalization",
)

# --------------------------------------------------------------------------
# Nodes (stub)
# --------------------------------------------------------------------------


def schema_matching(state: GlobalState) -> dict[str, Any]:
    logger.info("schema_matching: raw_spreadsheet=%s", state.get("raw_spreadsheet"))
    schema = CanonicalSchema.from_template()
    dummy_row = schema.rows[0]
    mapping = SchemaMapping(
        source_attribute="stub_attribute",
        source_context="Fase 2 stub — no LLM call",
        source_format="row-oriented",
        target_canonical_row=dummy_row.id,
        confidence=0.95,
        reasoning="stub node, dummy mapping to exercise graph shape only",
        normalization_required=False,
    )
    return {"schema_mapping": [mapping]}


def drive_crawler(state: GlobalState) -> dict[str, Any]:
    logger.info("drive_crawler: drive_url=%s", state.get("drive_url"))
    image = ImageMetadata(
        file_id="stub-file-id",
        filename="stub.jpg",
        mime_type="image/jpeg",
        size=0,
        created_time=datetime.now(timezone.utc),
    )
    return {"image_metadata": [image]}


def vision_classification(state: GlobalState) -> dict[str, Any]:
    n_images = len(state.get("image_metadata", []))
    logger.info("vision_classification: n_images=%d", n_images)
    result = VisionResult(
        classification_status="KNOWN",
        matched_variety="stub-varietas",
        identified_part="DAUN",
        confidence=0.9,
        visual_evidence="stub node, no vision model call",
    )
    return {"classification_results": [result]}


def manual_review(state: GlobalState) -> dict[str, Any]:
    trace = list(state.get("error_trace", []))
    trace.append("flagged for manual_review: low confidence or retries exhausted")
    logger.warning("manual_review: %s", trace[-1])
    return {"error_trace": trace}


def tabular_update(state: GlobalState) -> dict[str, Any]:
    logger.info("tabular_update: n_mappings=%d", len(state.get("schema_mapping", [])))
    return {"updated_spreadsheet": {"stub": True, "source": state.get("raw_spreadsheet")}}


def finalization(state: GlobalState) -> dict[str, Any]:
    logger.info("finalization: error_trace=%s", state.get("error_trace", []))
    return {"error_trace": state.get("error_trace", [])}


# --------------------------------------------------------------------------
# Conditional edge: verify-then-revise after the risky node
# --------------------------------------------------------------------------


def route_after_vision(state: GlobalState) -> Literal["retry", "manual_review", "continue"]:
    """Decide what happens after vision_classification, based on
    error_trace (things already flagged upstream) and the classification's
    own confidence — never by re-running the model to "see if it feels ok"."""
    error_trace = state.get("error_trace", [])
    if len(error_trace) >= MAX_VISION_RETRIES:
        return "manual_review"

    results = state.get("classification_results", [])
    low_confidence = bool(results) and results[-1].confidence < LOW_CONFIDENCE_THRESHOLD
    if error_trace or low_confidence:
        return "retry"

    return "continue"


# --------------------------------------------------------------------------
# Graph assembly
# --------------------------------------------------------------------------


def build_graph(checkpointer: Any = None, *, interrupt_after: list[str] | None = None):
    graph = StateGraph(GlobalState)

    graph.add_node("schema_matching", schema_matching)
    graph.add_node("drive_crawler", drive_crawler)
    graph.add_node("vision_classification", vision_classification)
    graph.add_node("manual_review", manual_review)
    graph.add_node("tabular_update", tabular_update)
    graph.add_node("finalization", finalization)

    graph.set_entry_point("schema_matching")
    graph.add_edge("schema_matching", "drive_crawler")
    graph.add_edge("drive_crawler", "vision_classification")
    graph.add_conditional_edges(
        "vision_classification",
        route_after_vision,
        {
            "retry": "vision_classification",
            "manual_review": "manual_review",
            "continue": "tabular_update",
        },
    )
    graph.add_edge("manual_review", "tabular_update")
    graph.add_edge("tabular_update", "finalization")
    graph.add_edge("finalization", END)

    return graph.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


# Fase 1 contract models get put straight into GlobalState by the stub nodes
# above, so the checkpoint serializer needs to know it's fine to
# msgpack/unpack them — otherwise a future langgraph version blocks it by
# default (see LANGGRAPH_STRICT_MSGPACK).
_ALLOWED_CHECKPOINT_TYPES = {
    ("src.schema.contracts", "SchemaMapping"),
    ("src.schema.contracts", "VisionResult"),
    ("src.schema.contracts", "ImageMetadata"),
}


@contextmanager
def _sqlite_checkpointer(db_path: Path):
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path.parent.mkdir(parents=True, exist_ok=True)
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_CHECKPOINT_TYPES)
    with closing(sqlite3.connect(str(db_path), check_same_thread=False)) as conn:
        yield SqliteSaver(conn, serde=serde)


def run_pipeline(
    spreadsheet_path: str,
    drive_url: str,
    *,
    db_path: str | Path = DEFAULT_CHECKPOINT_DB,
    thread_id: str = "default",
    interrupt_after: list[str] | None = None,
) -> GlobalState:
    """Run the stub pipeline from scratch for `thread_id`, checkpointing to
    a local SQLite file at every node. If `interrupt_after` is given, the
    graph stops after that node — resume with `resume_pipeline` using the
    same db_path/thread_id."""
    with _sqlite_checkpointer(Path(db_path)) as checkpointer:
        app = build_graph(checkpointer, interrupt_after=interrupt_after)
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: GlobalState = {
            "raw_spreadsheet": spreadsheet_path,
            "drive_url": drive_url,
            "error_trace": [],
        }
        result = app.invoke(initial_state, config=config)
    return result


def resume_pipeline(
    *,
    db_path: str | Path = DEFAULT_CHECKPOINT_DB,
    thread_id: str = "default",
) -> GlobalState:
    """Continue a previously interrupted/checkpointed run for `thread_id`
    from its last saved checkpoint through to finalization."""
    with _sqlite_checkpointer(Path(db_path)) as checkpointer:
        app = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        result = app.invoke(None, config=config)
    return result
