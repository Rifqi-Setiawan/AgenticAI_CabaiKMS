"""Dynamic canonical schema: the template rows plus acquired rows appended after them.

Acquired rows never change an existing row id or order (ids continue r_{N+1}, r_{N+2}, ... by acquisition order),
so template-only outputs stay identical. The feature is off unless KMS_DYNAMIC_SCHEMA is set.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any

from src.schema.canonical import CANONICAL_KEY_RE, CanonicalRow, CanonicalSchema

ENV_FLAG = "KMS_DYNAMIC_SCHEMA"


def dynamic_schema_enabled() -> bool:
    return os.getenv(ENV_FLAG, "false").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class ExtensionRow:
    """One acquired canonical row as stored in kms.schema_rows_ext."""

    canonical_key: str
    label: str
    domain: str
    seq: int
    contoh_nilai: tuple[str, ...] = ()
    alt_labels: tuple[str, ...] = ()
    status: str = "provisional"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ExtensionRow":
        return cls(
            canonical_key=str(data["canonical_key"]),
            label=str(data["label"]).strip(),
            domain=str(data["domain"]),
            seq=int(data["seq"]),
            contoh_nilai=tuple(str(x) for x in (data.get("examples") or data.get("contoh_nilai") or ())),
            alt_labels=tuple(str(x) for x in (data.get("aliases") or data.get("alt_labels") or ())),
            status=str(data.get("status") or "provisional"),
        )


def extension_hash(rows: list[ExtensionRow] | tuple[ExtensionRow, ...]) -> str:
    if not rows:
        return ""
    source = "\n".join(
        f"{r.seq}|{r.canonical_key}|{r.label}|{r.domain}|{','.join(r.contoh_nilai)}|{','.join(r.alt_labels)}"
        for r in sorted(rows, key=lambda r: r.seq)
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def extend_schema(base: CanonicalSchema, rows: list[ExtensionRow] | tuple[ExtensionRow, ...]) -> CanonicalSchema:
    """Return base + acquired rows. With no rows the base schema is returned unchanged (same object)."""
    rows = sorted(rows, key=lambda r: r.seq)
    if not rows:
        return base
    taken_keys = {r.canonical_key for r in base.rows}
    taken_labels = {r.label.strip().lower() for r in base.rows}
    extra: list[CanonicalRow] = []
    for position, ext in enumerate(rows, start=len(base.rows) + 1):
        if not CANONICAL_KEY_RE.fullmatch(ext.canonical_key) or ext.canonical_key in taken_keys:
            continue  # defensive: a conflicting stored row is skipped, never allowed to shadow a template row
        if ext.label.strip().lower() in taken_labels:
            continue
        taken_keys.add(ext.canonical_key)
        taken_labels.add(ext.label.strip().lower())
        extra.append(CanonicalRow(
            id=f"r_{position}", canonical_key=ext.canonical_key, label=ext.label.strip(), domain=ext.domain,
            contoh_nilai=ext.contoh_nilai, alt_labels=ext.alt_labels,
        ))
    if not extra:
        return base
    digest = extension_hash(rows)[:12]
    return CanonicalSchema(
        rows=[*base.rows, *extra],
        template_hash=base.template_hash,
        template_path=base.template_path,
        schema_version=f"{base.schema_version}+ext.{digest}",
        varietas=list(base.varietas),
        cells=dict(base.cells),
    )


def collection_name_for(schema: CanonicalSchema) -> str:
    """Chroma collection for this schema; the template-only schema keeps the original shared collection."""
    from src.agents.schema_matching.indexing import COLLECTION_NAME

    match = re.search(r"\+ext\.([0-9a-f]{12})$", schema.schema_version or "")
    return f"{COLLECTION_NAME}_x{match.group(1)}" if match else COLLECTION_NAME


# ----------------------------------------------------------------------------- loading

_KNOWN_EXTRA_IDS: set[str] = set()


def known_extension_row_ids() -> frozenset[str]:
    """Row ids of acquired rows seen by this process (grows only; used so SchemaMapping accepts r_61+)."""
    return frozenset(_KNOWN_EXTRA_IDS)


def remember_extension_ids(schema: CanonicalSchema, base_rows: int) -> None:
    for row in schema.rows[base_rows:]:
        _KNOWN_EXTRA_IDS.add(row.id)


def fetch_extension_rows(client: Any | None = None) -> list[ExtensionRow]:
    """Read acquired rows (not merged) from the KMS API; raises on failure so callers can decide how to degrade."""
    if client is None:
        from src.integrations.client import KmsClient
        from src.storage.config import get_settings

        client = KmsClient(get_settings())
    payload = client.request("GET", "/attributes/schema-rows")
    return [ExtensionRow.from_mapping(item) for item in payload.get("rows", [])]


def build_run_schema(rows: list[ExtensionRow] | tuple[ExtensionRow, ...] = ()) -> CanonicalSchema:
    base = CanonicalSchema.from_template()
    schema = extend_schema(base, rows)
    if schema is not base:
        remember_extension_ids(schema, len(base.rows))
    return schema


def schema_for_result(result: Any) -> CanonicalSchema:
    """Schema of a finished run: template + the extension rows recorded on the result."""
    return build_run_schema(tuple(getattr(result, "extension_rows", ()) or ()))
