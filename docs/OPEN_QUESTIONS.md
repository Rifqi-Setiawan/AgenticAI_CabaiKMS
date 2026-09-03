# Open Questions — Fase 0

> Riwayat keputusan Juli 2026. Pembaruan audit 3 September 2026: kolom output
> tabular kini berasal dari varietas input, sehingga tidak wajib cocok dengan
> varietas template. Crosswalk nama masih relevan untuk vision, yang memakai
> referensi template. Penyusunan `Lokasi` komposit belum diimplementasikan.
> Lihat [PROJECT_GUIDE.md](PROJECT_GUIDE.md) untuk daftar keterbatasan terkini.

Answered by the user on 2026-07-20. Kept as a record of *why* each decision
in `docs/DESIGN_DECISIONS.md` is the way it is — see that file for the
authoritative current state.

## Q1 — RESOLVED: no variant-(i) (transposed) raw sample existed

**Decision:** fabricate a synthetic fixture now rather than wait for a real
one. Created `data/samples/sample_transposed_sintetis.xlsx`, generated from
the canonical template's own row labels (read dynamically) with deliberately
messy injected values. Marked as synthetic in its own header rows. Should be
replaced/supplemented with a real transposed-format sample if one ever
surfaces — see `docs/DESIGN_DECISIONS.md` (d).

## Q2 — DEFERRED: sample varietas names don't match canonical varietas headers

`data_input.xlsx`'s `Jenis Cabai` values (species-level, e.g. `"Cabai rawit
(Capsicum frutescens L)"`) don't match any of the 10 canonical varietas
column headers.

**Decision:** depends on what real per-varietas input data actually looks
like once ingestion is built, and whether it ends up split per varietas at
all. Not deciding a fixed lookup/crosswalk now — revisit during the
ingestion-layer design fase, with more real samples in hand.

## Q3 — RESOLVED: multi-field location data vs. single `Lokasi` cell

**Decision:** `Lokasi` holds one composed human-readable string (name +
coordinates + elevation), consistent with the proposal's "one observation
location per cabai" constraint — the simplest option that still fits within
that boundary. If lat/lon/elevation need to be queried structurally later,
add a sidecar JSON keyed by varietas/location id rather than re-parsing the
composed string. Not implemented yet (no structured coordinate data to seed
it with) — belongs to the schema/ingestion fase.

## Q4 — RESOLVED: Lokasi/citra row mapping confirmed

Confirmed: row 56 = `Lokasi`; rows 57–60 = `Gambar Daun` / `Gambar Batang` /
`Gambar Buah` / `Gambar Bunga`.

## Q5 — RESOLVED: image rows split by plant part, buah/biji split too

**Decision:** split, not unified.
- `buah` and `biji` are separate domains (previously proposed as one merged
  `buah_biji`).
- Each image row reuses the domain of the part it depicts: `Gambar Daun` →
  `daun`, `Gambar Buah` → `buah`, `Gambar Bunga` → `bunga`, `Gambar Batang`
  → `vegetatif` (batang has no dedicated domain of its own in the template).

Applied in `src/schema/row_domains.yaml`.
