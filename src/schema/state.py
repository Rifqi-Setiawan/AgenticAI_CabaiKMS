"""Lightweight agent/reliability state contracts.

The serializable production checkpoint contract is ``RuntimeGraphState`` in
``src.orchestrator.graph``. ``GlobalState`` remains the small patch shape used
by reliability wrappers and deterministic review helpers.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .contracts import ImageMetadata, SchemaMapping, VisionResult


class GlobalState(TypedDict, total=False):
    """total=False: a node only needs to have populated the keys relevant to
    the step it just ran — not every key is present at every point in the
    graph."""

    raw_spreadsheet: Any  # legacy helper state; production graph stores source identity
    drive_url: str
    image_metadata: list[ImageMetadata]
    classification_results: list[VisionResult]
    updated_spreadsheet: Any  # pandas.DataFrame
    schema_mapping: list[SchemaMapping]
    error_trace: list[str]
