# Design Decisions — CABAI-KMS Akuisisi

> Keputusan desain tidak berarti semua fitur sudah selesai diimplementasikan.
> Status kode per 3 September 2026 ada di [PROJECT_GUIDE.md](PROJECT_GUIDE.md).

Status legend: **[FINAL]** decided by the user, not up for debate.
**[PROPOSED]** my inference from profiling, needs a yes/no.
**[OPEN]** genuinely blocked on the user — see `docs/OPEN_QUESTIONS.md` for
the numbered question this links to.

## (a) Canonical row count is dynamic

**[FINAL]** N = number of canonical rows, read dynamically from
`data/canonical/template_kanonik.xlsx` at runtime (today N = 60). No file
under `src/` may hardcode `60` (or any other literal row count) as a loop
bound, array size, or validation check. N is derived by counting non-empty
`Nomor`/row-1 entries in `Sheet1` at load time.

**[FINAL, confirmed 2026-07-20]** Based on profiling (`docs/PROFILING.md`
§1.1), confirmed by the user (`docs/OPEN_QUESTIONS.md` Q4):
- Row 56 (label `Lokasi`) is the location row.
- Rows 57–60 (labels `Gambar Daun`, `Gambar Batang`, `Gambar Buah`, `Gambar
  Bunga`) are the four image rows, one per plant part.
- Rows 1–55 are morphological characters (vegetatif/daun/bunga/buah/biji).

This mapping is recorded by **label text**, not row number, in
`src/schema/row_domains.yaml`, so it survives the user inserting new rows
later.

## (a.1) Stable canonical identity and template position are separate

**[FINAL, Phase 2]** `CanonicalRow.id` (`r_N`) is only the positional row
identifier for the currently loaded template. Existing `SchemaMapping`,
retrieval, review, and builder APIs continue to use it for compatibility,
but it is not a durable research identity.

`CanonicalRow.canonical_key` is the durable semantic identity, explicitly
committed in `src/schema/row_keys.yaml`. Keys are unique lowercase snake_case,
validated with exact template-label coverage, and remain unchanged when rows
are reordered. Missing, duplicate, or invalid key metadata is a configuration
error; runtime loading never invents fallback keys.

`schema_version` identifies the intended canonical specification.
`template_hash` independently fingerprints the exact ordered template labels,
so row reordering may change the latter without changing canonical keys.

Accepted non-empty schema-matching writes produce one structured cell
provenance record after the output builder confirms a mutation. Review,
no-write, blank, and duplicate/no-op attempts produce none. Exact source cell
coordinates remain empty until a future Source IR/structure-understanding
phase exposes them.

## (b) Domain = derived label, not a predicted field

**[FINAL]** "Domain" is a category tag attached to each canonical row
(`vegetatif`, `daun`, `bunga`, `buah`, `biji`, `lokasi`). It is used only for:
1. Extra context injected into the LLM prompt for that row.
2. Planned grouping of rows for Macro-F1 (not implemented yet; the empty
   `eval/metrics/` placeholder was removed during the September cleanup).

No agent predicts domain directly — it is always looked up from
`src/schema/row_domains.yaml` for whatever row is being processed. The set
of valid domains is **not a hardcoded enum**: it's whatever unique `domain`
values exist in that YAML file at load time.

All 60 current rows have an unambiguous domain assignment (see
`row_domains.yaml`); none needed `unassigned`.

**[FINAL, confirmed 2026-07-20]** Resolves `docs/OPEN_QUESTIONS.md` Q5:
- `buah` and `biji` are separate domains (rows 37–53 and 54–55
  respectively) — not merged into one `buah_biji` bucket as I'd first
  proposed.
- The four image rows (`Gambar Daun/Batang/Buah/Bunga`) each reuse the
  domain of the plant part they depict, rather than sharing one generic
  `path_citra` bucket: `Gambar Daun` → `daun`, `Gambar Buah` → `buah`,
  `Gambar Bunga` → `bunga`. `Gambar Batang` → `vegetatif`, since "batang"
  itself is just one vegetatif-domain row (#5) and has no dedicated domain
  of its own in the template.
- Net effect for Macro-F1: a wrong leaf photo penalizes the same `daun`
  score as a wrong leaf-text answer, instead of being tracked separately.

## (c) Google Drive = flat image list, part inferred from content

**[FINAL]** Drive folder has no subfolders; every image is a direct child.
Plant-part classification (daun/batang/buah/bunga) is decided from image
content plus filename signal, never from folder structure. The crawler is
implemented in `src/agents/drive_crawler.py`; its historical live verification
is recorded in `docs/CHECKPOINTS.md`. Vision is implemented separately.

## (d) Exactly two raw-format variants

**[FINAL]** Raw field spreadsheets come in exactly two shapes:
(i) transposed — varietas as column headers, characters as rows;
(ii) row-oriented — one row per observation, varietas named inside a
`jenis cabai`-like column. Anchor detection (locating that column, since its
position isn't fixed) is mandatory for parsing variant (ii).

**[FINAL, resolved 2026-07-20]** Profiling only turned up a variant-(ii)
example (`data/samples/data_input.xlsx`) and no variant-(i) example. Per
the user (`docs/OPEN_QUESTIONS.md` Q1), a fabricated variant-(i) fixture was
generated instead of waiting for a real one:
`data/samples/sample_transposed_sintetis.xlsx`. It is derived from the
canonical template's own row labels (read dynamically, not hand-copied) but
deliberately injects the messy notations catalogued in
`docs/PROFILING.md` §1.2/§2.3 (decimal-comma ranges, `;`-joined multi-value,
natural-language color instead of an RHS code, a stray `*` footnote marker,
a `-` for "missing", trailing whitespace, an inconsistent capitalization,
and a leading title row before the real header — to also exercise
header-row detection). It is clearly marked as synthetic in its own first
two rows and should be swapped for a real transposed-format sample if one
ever turns up; nothing should assume it's representative of real messiness
beyond exercising the parser mechanically.

**[DECIDED, partially deferred]** The one real sample available exposed two
mapping problems that sit above "which variant is this":
- Q2 (varietas names in the sample don't match any of the canonical
  template's 10 varietas headers): **deferred**, per the user — whether a
  fixed lookup/crosswalk is needed depends on what real per-varietas input
  data looks like once ingestion is actually built, and whether it ends up
  split per varietas at all. Not blocking Fase 0; revisit when the
  ingestion layer is designed.
- Q3 (the sample's location data is multiple fields; the canonical schema
  has one `Lokasi` cell per varietas): **[FINAL]** `Lokasi` stores a single
  composed human-readable string (e.g. `"<name> (<lat>, <lon>, <elev>
  mdpl)"`), per the proposal's constraint of one observation location per
  varietas. If lat/lon/elevation need to be queried structurally later, add
  a sidecar JSON (keyed by varietas or location id) alongside the canonical
  data rather than parsing it back out of the composed string. Not built
  yet — no structured coordinate data exists to seed it with, and this
  belongs to the schema/ingestion fase, not Fase 0.
