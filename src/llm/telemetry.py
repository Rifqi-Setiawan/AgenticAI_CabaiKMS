"""In-process, sanitized provider-call metadata for pipeline traces."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_provider_calls: ContextVar[list[dict[str, Any]]] = ContextVar("provider_calls", default=[])


def record_provider_call(record: dict[str, Any]) -> None:
    # Copy-on-write prevents ContextVar's mutable default leaking across contexts.
    records = _provider_calls.get()
    normalized = dict(record)
    normalized["attempt"] = 1 + sum(
        item.get("gateway") == normalized.get("gateway")
        and item.get("role") == normalized.get("role")
        for item in records
    )
    _provider_calls.set([*records, normalized])


def drain_provider_calls() -> list[dict[str, Any]]:
    records = _provider_calls.get()
    _provider_calls.set([])
    return records
