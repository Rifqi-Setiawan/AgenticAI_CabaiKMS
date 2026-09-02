"""Fase 3c — LLM reranker: given a source attribute profile and the k
candidate canonical rows Fase 3b retrieved, pick the single best match (or
decide NULL — no confident match) and produce a Fase 1 SchemaMapping.

`llm_call` is injected (defaults to src.llm.providers.call_with_fallback) so
this module never has to talk to a real network in tests: a mock plays the
LLM's role, still going through real Pydantic validation on SchemaMapping —
which is exactly the "constrained decoding" contract this sub-task is about.
target_canonical_row is restricted to {r_1..r_N, NULL} by SchemaMapping's
own validator (src/schema/contracts.py); nothing here re-implements that
check, so there is exactly one place it can drift out of sync with the
canonical schema.
"""

from __future__ import annotations

from typing import Callable

from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile
from src.llm.providers import call_with_fallback
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping

LLMCall = Callable[..., SchemaMapping]

SYSTEM_PROMPT = (
    "Anda adalah asisten pemetaan skema untuk data varietas cabai (CABAI-KMS). "
    "Diberi satu atribut dari spreadsheet lapangan dan beberapa kandidat baris "
    "kanonik, pilih SATU baris kanonik yang paling tepat sebagai "
    "target_canonical_row. Bernalar singkat (chain-of-thought singkat, 1-3 "
    'kalimat) lalu simpulkan di field "reasoning". Jika TIDAK ADA kandidat '
    f'yang cocok secara meyakinkan, keluarkan target_canonical_row="{NULL_ROW}" '
    "daripada menebak."
)


def _format_candidates(candidates: list[RetrievalHit], schema: CanonicalSchema) -> str:
    lines = []
    for hit in candidates:
        row = schema.row_by_id(hit.row_id)
        if row is None:
            continue
        contoh = ", ".join(row.contoh_nilai) if row.contoh_nilai else "-"
        alts = ", ".join(row.alt_labels) if row.alt_labels else "-"
        lines.append(
            f'- {row.id}: label="{row.label}" domain={row.domain} '
            f"contoh_nilai=[{contoh}] altLabels=[{alts}]"
        )
    return "\n".join(lines) if lines else "(tidak ada kandidat)"


def build_messages(
    profile: SourceAttributeProfile,
    candidates: list[RetrievalHit],
    schema: CanonicalSchema,
    source_format: str,
) -> list[dict[str, str]]:
    user_prompt = (
        f'Atribut sumber: "{profile.attribute_name}"\n'
        f"Konteks struktural: {profile.structural_context or '-'}\n"
        f"Contoh nilai: {', '.join(profile.sample_values) or '-'}\n"
        f"Tipe data terdeteksi: {profile.data_type}\n"
        f"Format sumber: {source_format}\n\n"
        f"Kandidat baris kanonik:\n{_format_candidates(candidates, schema)}\n\n"
        f'Jika tidak ada kandidat yang cocok, set target_canonical_row="{NULL_ROW}".'
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def rerank(
    profile: SourceAttributeProfile,
    candidates: list[RetrievalHit],
    *,
    source_format: str,
    schema: CanonicalSchema | None = None,
    llm_call: LLMCall = call_with_fallback,
) -> SchemaMapping:
    """Returns a validated SchemaMapping. Propagates whatever the LLM
    call/validation raises (LLMCallError if both providers fail;
    pydantic.ValidationError if the model — real or mocked — produces a
    target_canonical_row outside {r_1..r_N, NULL})."""
    schema = schema or CanonicalSchema.from_template()
    messages = build_messages(profile, candidates, schema, source_format)
    mapping = llm_call(response_model=SchemaMapping, messages=messages)
    if not isinstance(mapping, SchemaMapping):
        raise TypeError(f"llm_call must return a SchemaMapping, got {type(mapping)!r}")
    return mapping
