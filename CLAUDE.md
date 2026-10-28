# CLAUDE.md — cabai-kms-akuisisi

Current implementation reference (audited 2026-09-23):
[`README.md`](README.md) and [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md).
This file states project conventions, not a claim that the proposal is complete.

## What this system is

Adaptive Knowledge Acquisition berbasis Agentic AI untuk standardisasi data
multimodal pada CABAI-KMS. The goal: take messy field-collected chili
(cabai) varietas data — spreadsheets with inconsistent formats plus a flat
folder of unsorted plant-part photos on Google Drive — and standardize it
into rows of a canonical template (`data/canonical/template_kanonik.xlsx`),
using LLM agents rather than hand-written per-format parsers, with human
review in the loop.

Detailed data profiling: [`docs/PROFILING.md`](docs/PROFILING.md).
Design decisions and their rationale: [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md).
Full project reference (flow, tech stack, role of every folder/file):
[`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md).
Per-feature runtime map: [`docs/TECH_STACK_AND_FLOWS.md`](docs/TECH_STACK_AND_FLOWS.md).

## Architecture — 5 layers

1. **Data & Schema** (`data/`, `src/schema/`) — the canonical template, gold
   labels, and `row_domains.yaml` (the row → domain lookup; domain is never
   predicted, only looked up — see `docs/DESIGN_DECISIONS.md` (b)).
2. **Ingestion** — raw-format detection and normalization into a common
   intermediate representation: variant (i) transposed vs. (ii)
   row-oriented spreadsheets (anchor-column detection required for (ii)),
   and the Drive image crawler (flat file list, part inferred from image
   content + filename, never folder structure).
3. **Agents** (`src/agents/`) — exact-name matching, embedding retrieval,
   LLM reranking untuk atribut unresolved, normalisasi nilai deterministik,
   Drive crawling, dan klasifikasi citra multimodal.
4. **Orchestration & Reliability** (`src/orchestrator/`, `src/reliability/`)
   — LangGraph menjalankan pipeline nyata dengan checkpoint SQLite, routing
   Drive/vision, retry/validation wrappers, verifier deterministik, dan rate
   limiter opsional per run. Chroma retrieves canonical-row candidates, not a
   reviewed few-shot corpus.
5. **Interface & Evaluation** (`src/ui/`, `eval/`) — a Streamlit review UI
   for inspection/download. Review approve/revise/NO_MATCH dan replay output
   deterministik tersedia untuk run aktif. `eval/` menyediakan kampanye
   anotasi dan analisis kalibrasi; klaim metrik final belum tersedia.

`src/llm/` is a cross-cutting provider abstraction (9Router by default; Groq / Gemini / Ollama / OpenRouter in explicit legacy mode)
used by layers 3 and 4 — not a layer of its own.

Inter-agent contracts (Fase 1, `src/schema/contracts.py`): `SchemaMapping`
(source spreadsheet attribute → a canonical row id or `NULL`, with
confidence/reasoning; `target_domain` is a computed field derived from
`target_canonical_row` via `row_domains.yaml`, never requested from the
LLM), `VisionResult` (per-image plant-part classification), `ImageMetadata`
(Drive file metadata, no `relative_path` — Drive listing is flat). Valid
canonical row ids for `SchemaMapping.target_canonical_row` are read
dynamically from the loaded `CanonicalSchema` (`src/schema/canonical.py`),
never a hardcoded `Literal`. Shared LangGraph state shape is
`GlobalState` in `src/schema/state.py`.

## Stack

Python, `pandas` + `openpyxl` (spreadsheet I/O), `pydantic` (schema
validation), `langgraph` + `langgraph-checkpoint-sqlite` (runtime graph),
`chromadb` + `sentence-transformers` (canonical-row retrieval),
`instructor` (structured LLM output), `tenacity` + `aiolimiter`
(retry/optional rate-limit), `groq` + `openai` (provider clients),
`google-api-python-client` + `google-auth` (Drive), `streamlit` (UI).
No direct `google-genai` or `langchain-core` imports exist in project code.
See `requirements.txt` — only packages actually imported by code in `src/`
are left uncommented there; uncomment a dependency in the same commit that
introduces its first import.

## Conventions

- Never hardcode the canonical row count. Read N dynamically from
  `data/canonical/template_kanonik.xlsx` every time.
- Match canonical rows by **label text** (trimmed), not row number/index —
  row order and count can change when the user edits the template.
- Domain lookups always go through `src/schema/row_domains.yaml`; never
  hardcode a domain enum in Python — derive the valid set from that file's
  unique `domain` values.
- Canonical templates, samples, and annotated gold under `data/` are protected
  inputs; never overwrite them without an explicit user-approved reason.
  `data/.chroma/`, `data/.checkpoints/`, and `data/review/` are runtime stores;
  preserve their existing contents unless cleanup/reset is explicitly needed.
  Use fresh `--output` paths under `data/outputs/` for review harness runs.

## Working rules

- Read the actual asset (template, sample file, image) before writing any
  logic that touches it — don't assume shape from a description.
- Add/run a test for every change that touches parsing, schema mapping, or
  agent contracts.
- Big design decisions (schema semantics, agent contracts, evaluation
  metric definitions) get raised as an explicit question before being
  implemented — don't silently guess. Record final decisions in
  `docs/DESIGN_DECISIONS.md` and current blockers/limitations in
  `docs/PROJECT_GUIDE.md`.
