"""Acquisition of new canonical rows for attributes the matcher left unmapped (dynamic schema, stage 2).

Flow per run (only when KMS_DYNAMIC_SCHEMA is on):
  1. candidates = attributes whose final mapping is NULL and that pass a cheap deterministic guard;
  2. ONE LLM call judges all candidates together: is it a measurable plant/environment characteristic, which domain,
     a concise canonical label, which candidates share one meaning (group), and whether it is the same as one of the
     nearest existing rows;
  3. each group becomes at most one new row through the idempotent acquisition endpoint; anything that is the same as
     an existing row, or already known by label or alias, is never created (reported as DUPLICATE_OF).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from src.llm.providers import call_with_fallback
from src.schema.dynamic import ExtensionRow

ACQUIRE_DOMAINS = ("biji", "buah", "bunga", "daun", "vegetatif")
NULL_REF = "NULL"

# identity / bookkeeping columns that are never characteristics
_IGNORED = {
    "no", "nomor", "number", "lokasi", "lokasi sampling", "alamat", "address", "location", "koordinat", "coordinates",
    "latitude", "longitude", "s", "e", "varietas", "variety", "jenis cabai", "sample code", "kode sampel", "kode",
    "catatan", "keterangan", "notes", "note", "remarks", "tanggal", "date", "timestamp", "id", "nama", "name",
    "elevation", "ketinggian lahan", "ketinggian lahan sampling",
}

# a column whose name STARTS with one of these words is bookkeeping ("Catatan Surveyor", "Kode Plot", "Alamat Lengkap")
_IGNORED_HEADS = {
    "catatan", "keterangan", "notes", "note", "remarks", "koordinat", "coordinates", "alamat", "address", "lokasi",
    "location", "tanggal", "date", "nomor", "no", "kode", "id", "nama", "name",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", (text or "").lower())).strip()


def passes_guard(display_name: str, sample_values: list[str]) -> bool:
    """Cheap deterministic guard: skip identity/bookkeeping columns and columns without data."""
    name = _norm(display_name)
    last = name.split("/")[-1].strip()
    if name in _IGNORED or last in _IGNORED:
        return False
    if any(part.split(" ")[0] in _IGNORED_HEADS for part in (name, last) if part):
        return False
    return any(str(v).strip() for v in sample_values)


class AcquisitionItem(BaseModel):
    index: int
    is_characteristic: bool = Field(description="True only for a measurable or observable plant or growing-condition characteristic")
    canonical_label: str = Field(description="Concise canonical label in Indonesian, singular, without units in parentheses")
    domain: Literal["biji", "buah", "bunga", "daun", "vegetatif"]
    group: int = Field(description="Items with the same group number have the same meaning")
    same_as_existing: str = Field(default=NULL_REF, description="Row id (e.g. r_12) of an existing row with the same meaning, else NULL")
    reasoning: str = ""


class AcquisitionPlan(BaseModel):
    items: list[AcquisitionItem]


SYSTEM_PROMPT = (
    "Anda membantu memperluas skema kanonik data varietas cabai (CABAI-KMS). Setiap atribut di bawah TIDAK menemukan "
    "padanan pada baris kanonik yang ada menurut pemeta sebelumnya. Untuk setiap atribut: (1) tentukan apakah ia "
    "karakter yang dapat diukur atau diamati pada tanaman atau kondisi tumbuhnya (bukan identitas, lokasi, nomor, "
    "tanggal, atau catatan bebas); (2) pilih domain dari {biji, buah, bunga, daun, vegetatif} (pakai 'vegetatif' untuk "
    "karakter tanaman keseluruhan atau lingkungan); (3) tulis label kanonik ringkas berbahasa Indonesia; (4) beri nomor "
    "group yang SAMA untuk atribut yang bermakna sama (sinonim, beda bahasa, beda satuan); (5) bila atribut bermakna "
    "sama dengan salah satu baris yang ada pada daftar 'terdekat', isi same_as_existing dengan id barisnya, selain itu NULL. "
    "Jangan membuat atribut baru bila sudah ada baris yang bermakna sama."
)


@dataclass
class Candidate:
    index: int
    display_name: str
    context: str
    samples: list[str]
    nearest: list[str] = field(default_factory=list)  # "r_12: label" lines for the nearest existing rows


@dataclass
class Outcome:
    index: int
    status: str  # NEW_ROW | DUPLICATE_OF | NOT_CHARACTERISTIC | FAILED
    row: ExtensionRow | None = None
    duplicate_of: str | None = None
    note: str = ""


def build_messages(candidates: list[Candidate]) -> list[dict]:
    lines = []
    for c in candidates:
        near = "; ".join(c.nearest) if c.nearest else "-"
        lines.append(
            f"[{c.index}] label=\"{c.display_name}\" konteks=\"{c.context or '-'}\" "
            f"contoh_nilai={c.samples[:5]} terdekat=[{near}]"
        )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n".join(lines)}]


def plan(candidates: list[Candidate], llm_call: Callable[..., AcquisitionPlan] = call_with_fallback) -> AcquisitionPlan:
    result = llm_call(response_model=AcquisitionPlan, messages=build_messages(candidates))
    if not isinstance(result, AcquisitionPlan):
        raise TypeError("llm_call must return an AcquisitionPlan")
    return result


def acquire(
    candidates: list[Candidate],
    *,
    existing_row_ids: set[str],
    acquire_call: Callable[[dict[str, Any]], dict[str, Any]],
    run_id: str,
    source_sha256: str,
    llm_call: Callable[..., AcquisitionPlan] = call_with_fallback,
) -> list[Outcome]:
    """Judge, group and acquire. Never raises for judgement problems: failures become FAILED outcomes."""
    if not candidates:
        return []
    try:
        decided = {item.index: item for item in plan(candidates, llm_call).items}
    except Exception as exc:  # noqa: BLE001 - acquisition must never abort the mapping run
        return [Outcome(c.index, "FAILED", note=f"penilai akuisisi gagal: {type(exc).__name__}") for c in candidates]

    outcomes: dict[int, Outcome] = {}
    groups: dict[int, list[Candidate]] = {}
    for c in candidates:
        item = decided.get(c.index)
        if item is None:
            outcomes[c.index] = Outcome(c.index, "FAILED", note="tidak dinilai")
        elif not item.is_characteristic:
            outcomes[c.index] = Outcome(c.index, "NOT_CHARACTERISTIC", note=item.reasoning[:200])
        elif item.same_as_existing != NULL_REF and item.same_as_existing in existing_row_ids:
            outcomes[c.index] = Outcome(c.index, "DUPLICATE_OF", duplicate_of=item.same_as_existing, note=item.reasoning[:200])
        else:
            groups.setdefault(item.group, []).append(c)

    for members in groups.values():
        lead = decided[members[0].index]
        payload = {
            "label": lead.canonical_label.strip() or members[0].display_name,
            "domain": lead.domain,
            "examples": [s for m in members for s in m.samples[:2]][:5],
            "aliases": sorted({m.display_name for m in members if _norm(m.display_name) != _norm(lead.canonical_label)}),
            "source_label": members[0].display_name,
            "run_id": run_id,
            "source_sha256": source_sha256,
            "reason": f"akuisisi otomatis: {lead.reasoning[:160]}" if lead.reasoning else "akuisisi otomatis",
        }
        try:
            answer = acquire_call(payload)
        except Exception as exc:  # noqa: BLE001
            for m in members:
                outcomes[m.index] = Outcome(m.index, "FAILED", note=f"akuisisi gagal: {type(exc).__name__}")
            continue
        if answer.get("rejected"):
            for m in members:
                outcomes[m.index] = Outcome(m.index, "REJECTED_BEFORE", note="label dibuang kurator sebelumnya")
        elif answer.get("created") and answer.get("row"):
            row = ExtensionRow.from_mapping(answer["row"])
            for m in members:
                outcomes[m.index] = Outcome(m.index, "NEW_ROW", row=row)
        else:
            for m in members:
                outcomes[m.index] = Outcome(m.index, "DUPLICATE_OF", duplicate_of=answer.get("duplicate_of"))
    return [outcomes[c.index] for c in candidates]
