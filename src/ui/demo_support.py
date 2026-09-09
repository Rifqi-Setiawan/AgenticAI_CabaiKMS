"""Deterministic presentation helpers for the Streamlit demo UI."""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import openpyxl

from src.agents.drive_crawler import normalize_folder_id
from src.reliability.rate_limit import RuntimeRateLimitConfig


@dataclass(frozen=True)
class WorkbookPreflight:
    sheet_names: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.error is None and bool(self.sheet_names)


def inspect_xlsx_upload(filename: str, content: bytes) -> WorkbookPreflight:
    if Path(filename).suffix.lower() != ".xlsx":
        return WorkbookPreflight(error="Format tidak didukung. Unggah workbook .xlsx.")
    if not content:
        return WorkbookPreflight(error="Berkas kosong. Pilih workbook .xlsx yang berisi data.")
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            names = tuple(workbook.sheetnames)
        finally:
            workbook.close()
    except Exception:  # noqa: BLE001 - malformed archives must not leak parser internals
        return WorkbookPreflight(error="Workbook tidak dapat dibuka. Pastikan berkas merupakan .xlsx yang valid.")
    if not names:
        return WorkbookPreflight(error="Workbook tidak memiliki worksheet yang dapat diproses.")
    return WorkbookPreflight(sheet_names=names)


def validate_drive_input(value: str) -> str | None:
    if not value.strip():
        return None
    normalized = normalize_folder_id(value)
    if not normalized or re.fullmatch(r"[A-Za-z0-9_-]+", normalized) is None:
        return "URL atau ID folder Drive tidak dapat dikenali."
    return None


def runtime_readiness(environ: Mapping[str, str] | None = None, *, drive_requested: bool) -> dict[str, str]:
    source = os.environ if environ is None else environ
    text = "Groq key configured" if source.get("GROQ_API_KEY") else "Groq key not configured"
    text += "; fallback Ollama possible (reachability not checked)"
    vision = "enabled for this run" if drive_requested else "skipped until a Drive folder is provided"
    vision += "; Google key configured" if source.get("GOOGLE_API_KEY") else "; Google key not configured"
    try:
        limits = RuntimeRateLimitConfig.from_env(source)
        rate = (
            f"text {'enabled' if limits.text_rpm is not None else 'disabled'}; "
            f"vision {'enabled' if limits.vision_rpm is not None else 'disabled'}"
        )
    except ValueError:
        rate = "invalid rate-limit configuration"
    return {"Text provider": text, "Vision": vision, "Rate limit": rate}


def stage_state(status: str | None) -> str:
    value = (status or "").lower()
    if not value:
        return "SKIPPED"
    # Explicitly skipped stages remain skipped even when their reason names an
    # upstream failure, for example "dilewati (Drive gagal)".
    if any(token in value for token in ("dilewati", "skipped", "tidak ada folder", "folder drive kosong")):
        return "SKIPPED"
    if any(token in value for token in ("gagal", "failed", "error")):
        return "FAILED"
    if any(token in value for token in ("warning", "peringatan")):
        return "WARNING"
    counted_warnings = re.findall(r"\b(\d+)\s+(?:review|uncertain)\b", value)
    if any(int(count) > 0 for count in counted_warnings):
        return "WARNING"
    return "SUCCESS"


def run_summary(result: Any, last_inputs: Mapping[str, Any], *, unresolved_review_count: int) -> dict[str, Any]:
    mapping = result.mapping_df
    acceptance = mapping["acceptance_status"].value_counts() if "acceptance_status" in mapping else {}
    methods = mapping["mapping_method"].value_counts() if "mapping_method" in mapping else {}
    vision_rows = list(result.vision_rows)
    writes = sum(bool(row.get("write_applied")) for row in vision_rows)
    discovered = getattr(result, "images_discovered", len(vision_rows))
    return {
        "Source": last_inputs.get("filename", "-"),
        "Sheet": last_inputs.get("sheet_name", "-"),
        "Run ID": (result.run_id or result.checkpoint_thread_id or "-")[:12],
        "Source backend": result.source_backend,
        "Retrieval backend": result.retrieval_backend,
        "Mapped attributes": len(mapping),
        "AUTO_ACCEPT": int(acceptance.get("AUTO_ACCEPT", 0)),
        "REVIEW": int(acceptance.get("REVIEW", 0)),
        "NO_WRITE": int(acceptance.get("NO_WRITE", 0)),
        "Exact-name": int(methods.get("exact_name", 0)),
        "Retrieve-rerank": int(methods.get("retrieve_rerank", 0)),
        "Images discovered": discovered,
        "Vision processed": len(vision_rows),
        "Vision writes": writes,
        "Vision non-writes": len(vision_rows) - writes,
        "Unresolved reviews": unresolved_review_count,
    }


def safe_download_stem(filename: str) -> str:
    stem = Path(filename or "hasil").stem
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return sanitized[:80] or "hasil"


def user_error_message(exc: Exception) -> str:
    text = str(exc).lower()
    if any(token in text for token in ("anchor", "varietas", "header")):
        return "Struktur workbook belum dapat diproses. Periksa sheet, orientasi, header, dan kolom varietas."
    if "drive" in text or "folder" in text:
        return "Folder Drive tidak dapat diakses. Periksa ID/URL, kredensial, dan izin Viewer."
    if any(token in text for token in ("api_key", "authentication", "authorization", "credentials", "model")):
        return "Konfigurasi provider belum siap. Periksa variabel API/model pada environment."
    return "Pipeline tidak dapat diselesaikan. Lihat Progres atau Advanced / Debug untuk kategori kegagalan."
