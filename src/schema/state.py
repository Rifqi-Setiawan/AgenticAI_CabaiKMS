"""LangGraph shared state for the acquisition graph (Fase 1 boundary spec —
the orchestrator that actually threads this through nodes lands in Fase 4).
"""

from __future__ import annotations

from typing import Any, TypedDict

from .contracts import ImageMetadata, SchemaMapping, VisionResult


class GlobalState(TypedDict, total=False):
    """total=False: a node only needs to have populated the keys relevant to
    the step it just ran — not every key is present at every point in the
    graph."""

    raw_spreadsheet: Any  # pandas.DataFrame once ingestion lands (Fase 2)
    drive_url: str
    image_metadata: list[ImageMetadata]
    classification_results: list[VisionResult]
    updated_spreadsheet: Any  # pandas.DataFrame
    schema_mapping: list[SchemaMapping]
    error_trace: list[str]
