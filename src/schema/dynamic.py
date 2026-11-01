"""Dynamic canonical schema: the template rows plus acquired rows appended after them.

Acquired rows never change an existing row id or order. A row's id is derived from its stored sequence number
(`r_{template rows + seq}`), so merging or discarding one row never renumbers the others. Merge aliases are applied
to the target row's alternative labels. The feature is off unless KMS_DYNAMIC_SCHEMA is set.
"""

from __future__ import annotations

import dataclasses
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


@dataclass(frozen=True)
class ExtensionAlias:
    """A merged label that now resolves to `target_key` (a template or an acquired row)."""

    target_key: str
    alias: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ExtensionAlias":
        return cls(target_key=str(data["target_key"]), alias=str(data["alias"]).strip())


def extension_hash(rows, aliases=()) -> str:
    if not rows and not aliases:
        return ""
    source = "\n".join(
        [f"{r.seq}|{r.canonical_key}|{r.label}|{r.domain}|{','.join(r.contoh_nilai)}|{','.join(r.alt_labels)}"
         for r in sorted(rows, key=lambda r: r.seq)]
        + sorted(f"alias|{a.target_key}|{a.alias.lower()}" for a in aliases)
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def extend_schema(base: CanonicalSchema, rows=(), aliases=()) -> CanonicalSchema:
    """Return base + acquired rows (+ merge aliases). Nothing to add: the base schema object itself."""
    rows = sorted(rows, key=lambda r: r.seq)
    n = len(base.rows)
    taken_keys = {r.canonical_key for r in base.rows}
    taken_labels = {r.label.strip().lower() for r in base.rows}
    extra: list[CanonicalRow] = []
    for ext in rows:
        if not CANONICAL_KEY_RE.fullmatch(ext.canonical_key) or ext.canonical_key in taken_keys:
            continue  # defensive: a conflicting stored row never shadows an existing row
        if ext.label.strip().lower() in taken_labels:
            continue
        taken_keys.add(ext.canonical_key)
        taken_labels.add(ext.label.strip().lower())
        extra.append(CanonicalRow(
            id=f"r_{n + ext.seq}", canonical_key=ext.canonical_key, label=ext.label.strip(), domain=ext.domain,
            contoh_nilai=ext.contoh_nilai, alt_labels=ext.alt_labels,
        ))
    all_rows = [*base.rows, *extra]
    by_key = {r.canonical_key: i for i, r in enumerate(all_rows)}
    applied = False
    for alias in sorted(aliases, key=lambda a: (a.target_key, a.alias.lower())):
        index = by_key.get(alias.target_key)
        if index is None:
            continue
        row = all_rows[index]
        if alias.alias.strip().lower() in {x.lower() for x in (row.label, *row.alt_labels)}:
            continue
        all_rows[index] = dataclasses.replace(row, alt_labels=(*row.alt_labels, alias.alias.strip()))
        applied = True
    if not extra and not applied:
        return base
    digest = extension_hash(rows, aliases)[:12]
    return CanonicalSchema(
        rows=all_rows,
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
    """Row ids of acquired rows seen by this process (grows only; lets SchemaMapping accept r_61+)."""
    return frozenset(_KNOWN_EXTRA_IDS)


def fetch_extension(client: Any | None = None) -> tuple[list[ExtensionRow], list[ExtensionAlias]]:
    """Read active acquired rows and merge aliases from the KMS API; raises so callers decide how to degrade."""
    if client is None:
        from src.integrations.client import KmsClient
        from src.storage.config import get_settings

        client = KmsClient(get_settings())
    payload = client.request("GET", "/attributes/schema-rows")
    return (
        [ExtensionRow.from_mapping(item) for item in payload.get("rows", [])],
        [ExtensionAlias.from_mapping(item) for item in payload.get("aliases", [])],
    )


def fetch_extension_rows(client: Any | None = None) -> list[ExtensionRow]:
    return fetch_extension(client)[0]


def build_run_schema(rows=(), aliases=()) -> CanonicalSchema:
    base = CanonicalSchema.from_template()
    schema = extend_schema(base, rows, aliases)
    if schema is not base:
        template_ids = base.row_ids
        _KNOWN_EXTRA_IDS.update(row.id for row in schema.rows if row.id not in template_ids)
    return schema


def schema_for_result(result: Any) -> CanonicalSchema:
    """Schema of a finished run: template + the extension rows and aliases recorded on the result."""
    return build_run_schema(tuple(getattr(result, "extension_rows", ()) or ()),
                            tuple(getattr(result, "extension_aliases", ()) or ()))
