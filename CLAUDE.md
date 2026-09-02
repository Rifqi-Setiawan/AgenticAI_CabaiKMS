# CLAUDE.md — cabai-kms-akuisisi

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
Anything still unresolved: [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md).
Full project reference (flow, tech stack, role of every folder/file):
[`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md).

## Architecture — 5 layers

1. **Data & Schema** (`data/`, `src/schema/`) — the canonical template, gold
   labels, and `row_domains.yaml` (the row → domain lookup; domain is never
   predicted, only looked up — see `docs/DESIGN_DECISIONS.md` (b)).
2. **Ingestion** — raw-format detection and normalization into a common
   intermediate representation: variant (i) transposed vs. (ii)
   row-oriented spreadsheets (anchor-column detection required for (ii)),
   and the Drive image crawler (flat file list, part inferred from image
   content + filename, never folder structure).
3. **Agents** (`src/agents/`) — LLM-driven extraction/standardization per
   canonical row: turning a messy source value (range, decimal-comma,
   multi-value, color code, ...) into the canonical row's expected format,
   plus an image-to-plant-part classification agent.
4. **Orchestration & Reliability** (`src/orchestrator/`, `src/reliability/`)
   — a LangGraph graph coordinating agent calls across rows/domains for a
   given varietas, with retry/rate-limiting policy and (once needed)
   vector-store-backed few-shot retrieval for grounding agent prompts.
5. **Interface & Evaluation** (`src/ui/`, `eval/`) — a Streamlit review UI
   for human-in-the-loop correction, and the Macro-F1-per-domain evaluation
   harness against `data/gold/`.

`src/llm/` is a cross-cutting provider abstraction (Groq / Gemini clients)
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
validation), `langgraph` + `langchain-core` (orchestration, Fase 1+),
`chromadb` + `sentence-transformers` (few-shot retrieval, Fase 2+),
`instructor` (structured LLM output, Fase 2+), `tenacity` + `aiolimiter`
(retry/rate-limit, Fase 1+), `groq` + `google-genai` (LLM providers, Fase
3+), `google-api-python-client` (Drive crawler), `streamlit` (review UI).
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
- Files under `data/` (canonical template, samples, gold, Drive images once
  fetched) are inputs — read them, never write/overwrite them from code
  without an explicit user-approved reason.

## Working rules

- Read the actual asset (template, sample file, image) before writing any
  logic that touches it — don't assume shape from a description.
- Add/run a test for every change that touches parsing, schema mapping, or
  agent contracts.
- Big design decisions (schema semantics, agent contracts, evaluation
  metric definitions) get raised as an explicit question before being
  implemented — don't silently guess. Use `docs/OPEN_QUESTIONS.md` for
  anything that blocks progress across sessions.
