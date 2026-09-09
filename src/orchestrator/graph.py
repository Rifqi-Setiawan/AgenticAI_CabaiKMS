"""Real LangGraph coordinator for the acquisition runtime."""
from __future__ import annotations

import hashlib, io, json, sqlite3, uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict
import openpyxl
from langgraph.graph import END, StateGraph
from src.agents.drive_crawler import DriveCrawlerError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT_DB = PROJECT_ROOT / "data" / ".checkpoints" / "orchestrator.sqlite"
NODE_ORDER = ("source_ingestion", "schema_matching_tabular", "drive_crawler", "vision_classification", "finalization")

class RuntimeGraphState(TypedDict, total=False):
    run_id: str; runtime_identity: str; source_path: str; source_file_name: str
    source_file_sha256: str; source_format: str; sheet_name: str; header_rows: int | None
    drive_folder_id: str; max_images: int; source_backend: str; retrieval_backend: str
    retrieval_k: int; schema_version: str; template_hash: str
    evaluation_config_fingerprint: str; source_ir_version: str | None
    review_queue_path: str; error_trace: list[str]; agent_status: dict[str, str]
    mapping_json: str; workbook_bytes: bytes; variety_names: list[str]
    vision_rows: list[dict[str, Any]]; provenance_records: list[dict[str, Any]]
    mapping_verifications: list[dict[str, Any]]; structure_shadow: dict[str, Any] | None
    image_metadata: list[dict[str, Any]]; completed: bool
    enable_structure_shadow: bool; embedding_model_name: str | None
    mapping_verification_version: str
    prepared_source_bundle: Any

@dataclass
class RuntimeResources:
    on_progress: Callable[[str], None]
    text_rate_limiter: Any = None; vision_rate_limiter: Any = None
    structure_llm_call: Callable | None = None; embedding_encode_call: Callable | None = None
    prepared_source_bundle: Any = None

_ACTIVE_RESOURCES: dict[str, RuntimeResources] = {}

def _resources(config):
    key = config["configurable"]["runtime_resources_id"]
    if key not in _ACTIVE_RESOURCES:
        raise RuntimeError("runtime resources unavailable; resume with a runtime context")
    return _ACTIVE_RESOURCES[key]

def runtime_identity(values):
    keys = ("run_id", "source_file_sha256", "source_format", "sheet_name", "header_rows",
            "drive_folder_id", "max_images", "source_backend", "retrieval_backend", "retrieval_k",
            "schema_version", "template_hash", "evaluation_config_fingerprint",
            "enable_structure_shadow", "review_queue_path")
    return hashlib.sha256(json.dumps({k: values.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()

def _prepare_source(state, resources):
    from src.ui import pipeline_runner as r
    path, backend = Path(state["source_path"]), state["source_backend"]
    if backend == "legacy":
        bundle = r.prepare_legacy_runtime_source(path, state["sheet_name"], source_format=state["source_format"],
            header_rows=state.get("header_rows"), anchor_detector=r.detect_anchor)
        status = "legacy — authoritative parser"
    elif backend == "source-ir-gated":
        bundle = r.prepare_gated_runtime_source(path, state["sheet_name"], source_format=state["source_format"],
            header_rows=state.get("header_rows"), llm_call=resources.structure_llm_call,
            anchor_detector=r.detect_anchor)
        status = "source-ir-gated — promoted after MATCH parity"
    else:
        raise ValueError(f"unknown source backend {backend!r}; expected one of: legacy, source-ir-gated")
    if not bundle.variety_names:
        raise ValueError("Tidak ada varietas untuk keluaran. Periksa header dan isi data sumber.")
    return bundle, status

def source_ingestion(state, config):
    resources, status_map = _resources(config), dict(state.get("agent_status", {}))
    bundle, status = _prepare_source(state, resources)
    resources.prepared_source_bundle = bundle; status_map["source_ingestion"] = status
    if bundle.migration_report: status_map["structure_shadow"] = bundle.migration_report.summary
    resources.on_progress(f"source_ingestion: {status}")
    return {"agent_status": status_map,
            "prepared_source_bundle": bundle,
            "source_ir_version": bundle.source_ir.ir_version if bundle.source_ir else None,
            "structure_shadow": bundle.migration_report.model_dump(mode="json") if bundle.migration_report else None}

def schema_matching_tabular(state, config):
    from src.ui import pipeline_runner as r
    resources = _resources(config)
    if resources.prepared_source_bundle is None:
        resources.prepared_source_bundle = state.get("prepared_source_bundle")
    if resources.prepared_source_bundle is None:
        resources.prepared_source_bundle, _ = _prepare_source(state, resources)
    result = r._run_tabular_stage_impl(Path(state["source_path"]), source_format=state["source_format"],
        sheet_name=state["sheet_name"], header_rows=state.get("header_rows"),
        k=state["retrieval_k"], on_progress=resources.on_progress,
        enable_structure_shadow=state.get("enable_structure_shadow", False),
        structure_llm_call=resources.structure_llm_call, source_backend=state["source_backend"],
        retrieval_backend=state["retrieval_backend"], embedding_encode_call=resources.embedding_encode_call,
        review_queue_path=state["review_queue_path"], text_rate_limiter=resources.text_rate_limiter,
        _prepared_source_bundle=resources.prepared_source_bundle, _run_id=state["run_id"])
    status = dict(state.get("agent_status", {})); status.update(result.agent_status)
    status["orchestrator"] = "schema/tabular selesai; checkpoint LangGraph"
    return {"mapping_json": result.mapping_df.to_json(orient="table"), "workbook_bytes": result.workbook_bytes,
        "variety_names": list(result.canonical_df.columns[2:]), "vision_rows": [],
        "provenance_records": [x.model_dump(mode="json") for x in result.provenance_records],
        "mapping_verifications": [x.model_dump(mode="json") for x in result.mapping_verifications],
        "error_trace": list(result.error_trace), "agent_status": status,
        "structure_shadow": result.structure_shadow.model_dump(mode="json") if result.structure_shadow else None,
        "source_ir_version": result.source_ir_version}

def route_after_tabular(state): return "drive" if state.get("drive_folder_id", "").strip() else "finalize"

def drive_crawler(state, config):
    from src.ui import pipeline_runner as r
    resources, status = _resources(config), dict(state.get("agent_status", {})); folder = state["drive_folder_id"].strip()
    try: images = r.list_images(r.normalize_folder_id(folder))[:state["max_images"]]
    except DriveCrawlerError as exc:
        status["drive_crawler"] = f"gagal: {exc}"; status["vision_classification"] = "dilewati (Drive gagal)"; resources.on_progress(f"drive_crawler: GAGAL — {exc}")
        return {"image_metadata": [], "agent_status": status}
    resources.on_progress(f"drive_crawler: {len(images)} citra ditemukan")
    status["drive_crawler"] = f"selesai — {len(images)} citra ditemukan"
    if not images: status["vision_classification"] = "dilewati (folder Drive kosong, tidak ada citra)"
    return {"image_metadata": [x.model_dump(mode="json") for x in images], "agent_status": status}

def route_after_drive(state): return "vision" if state.get("image_metadata") else "finalize"

def vision_classification(state, config):
    from src.schema.contracts import ImageMetadata
    from src.ui import pipeline_runner as r
    resources = _resources(config); wb = openpyxl.load_workbook(io.BytesIO(state["workbook_bytes"])); ws = wb[r.SHEET_NAME]
    session = r.VisionSession(); trace = {"error_trace": list(state.get("error_trace", []))}; rows=[]; written=uncertain=classified=0
    for raw in state.get("image_metadata", []):
        image = ImageMetadata.model_validate(raw)
        result, patch = r.safe_classify_image(image, session.knowledge_source_text, session.varieties, trace,
                                              vision_rate_limiter=resources.vision_rate_limiter)
        trace.update(patch)
        if result is None:
            rows.append({"filename": image.filename, "status": "FAILED", "matched_variety": None,
                "identified_part": None, "confidence": None, "visual_evidence": None,
                "write_applied": False, "write_reason": "classification failed; see Advanced / Debug trace"})
            continue
        classified += 1
        uncertain += result.classification_status == "UNCERTAIN"; update = r.apply_vision_result_to_worksheet(ws, image, result)
        written += update.applied
        if not update.applied and update.reason:
            warning=f"vision_non_write: file_id={image.file_id!r}: {update.reason}"
            trace.update(r.review_queue.append_error_trace(trace, warning))
        rows.append({"filename": image.filename, "status": result.classification_status,
            "matched_variety": result.matched_variety, "identified_part": result.identified_part,
            "confidence": result.confidence, "visual_evidence": result.visual_evidence,
            "write_applied": update.applied, "write_reason": update.reason})
    status=dict(state.get("agent_status", {})); status["vision_classification"]=(
        f"selesai — {classified} citra diklasifikasi, {written} ditulis ke sel, {uncertain} UNCERTAIN")
    payload=r._deterministic_workbook_bytes(wb); wb.close()
    return {"workbook_bytes":payload, "vision_rows":rows, "error_trace":trace["error_trace"], "agent_status":status}

def finalization(state, config):
    resources=_resources(config); status=dict(state.get("agent_status", {}))
    if not state.get("drive_folder_id", "").strip():
        status["drive_crawler"]="dilewati (tidak ada folder Drive)"; status["vision_classification"]="dilewati (tidak ada folder Drive)"
    status["orchestrator"]=f"LangGraph runtime selesai (thread_id={state['run_id']})"; resources.on_progress("finalization: selesai")
    return {"agent_status":status, "completed":True}

def build_graph(checkpointer=None, *, interrupt_after=None):
    g=StateGraph(RuntimeGraphState)
    for name,node in (("source_ingestion",source_ingestion),("schema_matching_tabular",schema_matching_tabular),
        ("drive_crawler",drive_crawler),("vision_classification",vision_classification),("finalization",finalization)): g.add_node(name,node)
    g.set_entry_point("source_ingestion"); g.add_edge("source_ingestion","schema_matching_tabular")
    g.add_conditional_edges("schema_matching_tabular",route_after_tabular,{"drive":"drive_crawler","finalize":"finalization"})
    g.add_conditional_edges("drive_crawler",route_after_drive,{"vision":"vision_classification","finalize":"finalization"})
    g.add_edge("vision_classification","finalization"); g.add_edge("finalization",END)
    return g.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)

@contextmanager
def _sqlite_checkpointer(db_path):
    from langgraph.checkpoint.sqlite import SqliteSaver
    path=Path(db_path); path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(str(path),check_same_thread=False)) as conn: yield SqliteSaver(conn)

def _invoke(state, resources, *, db_path, thread_id, interrupt_after=None):
    key=uuid.uuid4().hex; _ACTIVE_RESOURCES[key]=resources
    try:
        with _sqlite_checkpointer(db_path) as cp:
            app=build_graph(cp,interrupt_after=interrupt_after)
            return app.invoke(state,config={"configurable":{"thread_id":thread_id,"runtime_resources_id":key}})
    finally: _ACTIVE_RESOURCES.pop(key,None)

def run_pipeline(initial_state, resources, *, db_path=DEFAULT_CHECKPOINT_DB, interrupt_after=None):
    return _invoke(initial_state,resources,db_path=db_path,thread_id=initial_state["run_id"],interrupt_after=interrupt_after)

def resume_pipeline(expected_state, resources, *, db_path=DEFAULT_CHECKPOINT_DB):
    thread_id=expected_state["run_id"]
    with _sqlite_checkpointer(db_path) as cp: saved=cp.get({"configurable":{"thread_id":thread_id}})
    if saved is None: raise ValueError(f"no checkpoint exists for thread_id={thread_id!r}")
    if saved["channel_values"].get("runtime_identity") != expected_state["runtime_identity"]:
        raise ValueError("resume source/config identity does not match checkpoint")
    return _invoke(None,resources,db_path=db_path,thread_id=thread_id)
