# Design Decisions — CABAI-KMS Akuisisi

> Keputusan desain tidak berarti semua fitur sudah selesai diimplementasikan.
> Status kode per 23 September 2026 ada di [PROJECT_GUIDE.md](PROJECT_GUIDE.md).

Status legend: **[FINAL]** decided by the user, not up for debate.
**[PROPOSED]** my inference from profiling, needs a yes/no.
**[OPEN]** genuinely blocked on the user; current blockers belong in the
limitations section of `docs/PROJECT_GUIDE.md` until decided.

## (a) Canonical row count is dynamic

**[FINAL]** N = number of canonical rows, read dynamically from
`data/canonical/template_kanonik.xlsx` at runtime (today N = 60). No file
under `src/` may hardcode `60` (or any other literal row count) as a loop
bound, array size, or validation check. N is derived by counting non-empty
`Nomor`/row-1 entries in `Sheet1` at load time.

**[FINAL, confirmed 2026-07-20]** Based on profiling (`docs/PROFILING.md`
§1.1) and confirmed by the user:
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
coordinates remain empty on the legacy pipeline path. In the current Phase 6+
architecture, a verified Source IR that passes exact parity under
`source-ir-gated` supplies physical value/header coordinates to acknowledged
canonical-write provenance. Historical Phase 4 standalone availability did not
yet provide that integration.

## (a.2) Observations, hypotheses, verification, and Source IR are separate

**[FINAL, Phase 4]** `WorkbookProfile` contains deterministic observed workbook
facts only. `StructureProposal` is a probabilistic structural hypothesis and is
never trusted merely because model-reported confidence is high. Only a
`RESOLVED` proposal that passes the deterministic geometric verifier becomes a
`VerifiedStructure`; only that verified wrapper may be used to build Source IR.

`SourceIR` is a deterministic, versioned machine-readable representation built
from complete profile facts and verified coordinates. It preserves physical
header coordinates, value coordinates, merged-anchor traceability, and blank
logical positions. It performs no normalization or canonical schema mapping.
`AMBIGUOUS` and `UNSUPPORTED` are valid abstention outcomes and produce no Source
IR. `NEED_MORE_EVIDENCE` permits only bounded, validated, targeted range
inspection rather than blind retries or whole-profile serialization. Targeted
rounds accumulate prior evidence, reject repeated identical normalized ranges,
and share a 1,500-cell global materialization budget.

Phase 4B finalizes `source-ir-v1` coordinate semantics before production
integration: `SourceValueIR.coordinate` is the logical table position, while
`SourceValueIR.source_coordinate` is the physical content cell (including a
merged top-left anchor). A logical blank has no physical source coordinate.

## (a.3) Parser migration uses shadow parity before production cutover

**[FINAL, Phase 5]** Migration follows `legacy parser -> shadow parity -> gated
production migration`. The legacy parser remains authoritative while the profiler,
structure agent, verifier, and Source IR execute only as an optional default-off
shadow. A shadow failure, abstention, or disagreement cannot affect retrieval,
reranking, acceptance, normalization, vision, or canonical output.

Direct replacement would combine architectural change with correctness risk. The
versioned deterministic parity report therefore compares orientation, full logical
attribute identity, context, ordering, positional values, row-oriented anchor, and
transposed entity positions first. `MATCH` means behavioral equivalence to the legacy
parser on that workbook; it does not establish ground-truth correctness. A legacy
failure with new-path success is recorded only as potential coverage expansion.

## (a.4) Source IR production promotion requires exact parity

**[FINAL, Phase 6]** The default production backend remains `legacy`. The explicit
`source-ir-gated` backend builds one verified Source IR candidate and may use it for
downstream schema matching only when its deterministic Phase 5 report is exactly
`MATCH`. No confidence threshold can substitute for parity. Difference, abstention,
verification/model failure, and legacy-reference failure stop before indexing; there
is no silent fallback in an explicitly gated experiment.

This gate changes only the source parsing representation. Retrieval inputs,
reranking, normalization, selective acceptance, and canonical assembly remain shared,
making downstream effects scientifically attributable to the parser migration.
Legacy-fail/new-success remains potential coverage evidence and is not promoted.

For promoted Source IR writes, `source_cells` means physical value cells contributing
to the acknowledged canonical mutation. `source_header_cells` separately identifies
the physical cells defining source attribute identity/context. Duplicate raw values
retain all distinct contributing cells, while repeated references to one merged anchor
are deduplicated in first-seen order. Legacy records retain empty coordinate lists.

XLSX archive timestamps and the core `modified` value are intentionally normalized
during pipeline serialization. Deterministic artifact bytes support reproducibility;
the normalized metadata must not be interpreted as the actual export time.

## (a.5) Exact cosine is the opt-in retrieval backend for Phase 7A

**[FINAL, Phase 7A]** For the current small, dynamically loaded canonical
vocabulary, exhaustive cosine is architecturally preferable to ANN: N is very
small, its matrix-vector cost is negligible, every row is evaluated, ties can be
resolved deterministically by stable `canonical_key`, and experiments are easier to
reproduce and audit without an approximation/persistence layer.

Phase 7A changes only canonical candidate search. Exact and Chroma use the same
`paraphrase-multilingual-MiniLM-L12-v2` model, canonical serialization, source query,
reranker, mapping contract, and acceptance logic. Exact mode defensively normalizes
both sides, reports cosine distance (`1 - similarity`) for compatibility, embeds the
canonical matrix once per process-local model/representation cache key, and never
accesses Chroma. ANN/exact overlap is diagnostic only: agreement is not ground truth,
and disagreement does not invalidate exhaustive search.

Migration policy: `chroma` remains the default in Phase 7A and `exact` requires
explicit opt-in. After retrieval audit and human/gold evaluation, a future phase may
promote exact to default and retire Chroma if it is no longer required. Phase 7A does
not remove Chroma or its persisted data.

## (a.6) Deterministic equivalence precedes probabilistic mapping

**[FINAL, Phase 7B]** Explicit canonical labels and curated aliases are equivalence
metadata. When a normalized source leaf name has exactly one canonical owner, it is
resolved before any embedding retrieval or LLM reranking:

`unique label/alias equivalence > embedding retrieval > LLM reranking`.

This precedence applies only to a unique owner. Two or more rows sharing a normalized
label/alias—including a label on one row colliding with another row's alias—produce
an observable `AMBIGUOUS` resolution and fall through to semantic retrieval and
reranking. Template position, domain, and vector similarity must never silently turn
ambiguous equivalence metadata into a deterministic match. Direct reranker callers
use the same fail-closed resolver.

Verified Source IR header hierarchy and detected source value type are semantic
evidence and may enrich the source query and reranker prompt. Physical cell
coordinates and `source_attribute_id` are provenance/traceability evidence; they are
not embedded merely because Source IR makes them available. Legacy profiles with no
richer evidence retain their prior query and prompt bytes. Chroma/exact preparation
is lazy, so an all-exact-name workbook initializes neither vector backend.

## (a.7) Prediction and verification are independent contracts

**[FINAL, Phase 7C1]** `SchemaMapping` is the reranker's proposal;
`MappingVerificationResult` is deterministic evidence about that proposal. LLM
self-confidence remains observable and continues to feed the legacy Phase 1 policy,
but it is not treated as an independent correctness estimate. The verifier uses no
LLM, embedding call, network, or file I/O.

Phase 7C1 records exact-name consistency, source metadata consistency, candidate
membership, target rank/distance, top-1/top-2 separation, and reliability-wrapper
signals. A globally valid canonical row is not a valid reranker decision unless it
was actually supplied in the candidate set. Deterministic hard violations immediately
force `NO_WRITE`; verifier PASS cannot promote a legacy REVIEW, and soft verifier
REVIEW remains observational. No distance or margin thresholds are introduced.

Migration strategy:

- **C1:** collect raw evidence and enforce only hard integrity invariants.
- **C2:** calibrate soft signals on explicit validation ground truth, evaluate
  precision/risk versus automation coverage, then promote only validated policy.

## (a.8) Calibration uses adjudicated stable-key gold and workbook holdout

**[FINAL, Phase 7C2A]** Calibration ground truth is a human decision expressed with
stable `canonical_key`, never positional `r_N` and never the model's prediction.
Prediction artifacts and gold are joined only with deterministic `mapping_item_id`,
whose source identity excludes target, confidence, backend, and DataFrame order.

Two independent annotators are compared exactly on status and canonical-key set.
Disagreements require explicit adjudication, and the final record preserves both
independent decisions. `ONE_TO_ONE` and `NO_MATCH` are eligible for the current
single-target calibration. `AMBIGUOUS`, `COMPOSITE`, and `EXCLUDE` remain visible but
are excluded from threshold calculations.

Validation/test assignment is grouped by source workbook SHA. One workbook cannot
contribute attributes to both splits, and identical SHA across splits is invalid.
Calibration and policy-sweep functions reject test input; evaluation-only metrics may
use test only after policy freeze. Historical review workbooks remain
`legacy_unverified` until human migration confirms them under the new contract.

Phase 7C2A records raw signals and generates interpretable analysis artifacts only.
It selects no production distance, margin, rank, or confidence rule; the Phase 7C1
acceptance behavior and `DEFAULT_CONFIDENCE_THRESHOLD` remain unchanged.

**[FINAL, Phase 7C2A-H]** Evaluation identity is fail-open for production processing
and fail-closed for annotation/calibration. Unique displays use display identity to
remain stable across legacy and SourceIR experiments. Only members of a repeated
display group use stable `source_attribute_id`; unavailable coordinates produce an
observable null ID without blocking retrieval, reranking, acceptance, normalization,
or canonical output. No positional suffix is allowed.

Human CSV/XLSX round-trips are accepted only after recomputing each identity hash and
validating canonical keys against the active schema. First-pass A/B comparison requires
different pseudonymous annotator IDs, one shared round, and `human_independent` source.
Single-class perfect agreement retains raw agreement 1.0 but reports Cohen's kappa as
undefined, rather than manufacturing kappa 1.0.

Evaluation runs carry a secret-free fingerprint over source/retrieval backend, k,
schema version and template hash, verifier version, and embedding model. One calibration
dataset cannot silently combine fingerprints. These controls harden evidence only and
do not modify any production mapping policy or select a threshold.

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

**[FINAL, confirmed 2026-07-20]** The user confirmed:
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
implemented in `src/agents/drive_crawler.py`; vision is implemented separately.

## (d) Exactly two raw-format variants

**[FINAL]** Raw field spreadsheets come in exactly two shapes:
(i) transposed — varietas as column headers, characters as rows;
(ii) row-oriented — one row per observation, varietas named inside a
`jenis cabai`-like column. Anchor detection (locating that column, since its
position isn't fixed) is mandatory for parsing variant (ii).

**[FINAL, resolved 2026-07-20]** Profiling only turned up a variant-(ii)
example (`data/samples/data_input.xlsx`) and no variant-(i) example. With
the user's approval, a fabricated variant-(i) fixture was
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

## (e) Perlindungan Nilai Atribut Hasil Kurasi Manusia (Decision D2)

**[FINAL, 2026-10-27]** Berdasarkan keputusan formal Rifqi (D2):
- Atribut yang tersimpan di dokumen aktif dengan status `resolution = "HUMAN_REVIEW"` merupakan nilai yang telah divalidasi oleh kurator manusia dan berstatus dilindungi (`EXISTING_HUMAN_PROTECTED`).
- Nilai otomatis baru (`AUTO_ACCEPT`) tidak diperbolehkan menimpa nilai terlindungi tersebut secara otomatis.
- Penimpaan hanya boleh terjadi lewat peninjauan manusia oleh peran `curator` disertai alasan wajib (`reason`).
- Keputusan ini resmi menggantikan kriteria PRD A10 / "Decision #2" (yang sebelumnya mengizinkan AUTO_ACCEPT menimpa HUMAN_REVIEW). Catatan historis A10 ditandai: *DIGANTIKAN oleh D2 (27 Okt 2026)*.

## (f) D7: Kontrak Unwrap dan Jembatan UI-API Resolusi Review

**[FINAL, 2026-10-28]** Kontrak payload endpoint `POST /runs/v2/{run_id}/reviews/{item_id}/resolve`:
- Endpoint menerima payload datar maupun payload bersarang dengan tepat satu kunci `{"decision": {...}}` (seperti yang dikirim oleh antarmuka Streamlit dan modul review foto).
- Fungsi internal API `_unwrap_decision` membuka payload bersarang tersebut dan menyalurkannya sebagai dictionary datar ke `DocumentRepository.resolve_review`. Payload ambigu atau kosong ditolak dengan HTTP 422.
- Resolusi review wajib memuat aksi (`action`) atau status (`status`), mencegah resolusi no-op atau error parsing terselubung.

## (g) D8: UI Interaktif Penyelesaian Review Anti Salah Satuan

**[FINAL, 2026-10-28]** Perilaku antarmuka Streamlit untuk antrean review penimpaan dan ketidakcocokan satuan:
- Seluruh teks alasan bawaan yang di-hardcode dihapuskan.
- Kurator wajib menginput alasan peninjauan (minimal 10 karakter) sebelum aksi penimpaan (`APPLY_INCOMING`) atau koreksi (`REVISE`) dapat dieksekusi.
- Pada item `UNIT_MISMATCH`, tombol aksi "Terapkan Baru" ditiadakan guna mencegah penyimpanan nilai tanpa penyesuaian satuan (anti-bug 85 kg menjadi 85 cm).
- Aksi koreksi (`REVISE`) mewajibkan kurator memasukkan dan mengonfirmasi secara sadar nilai dan satuan terkoreksi yang kompatibel dengan tipe dan satuan ekspektasi atribut.

## (h) D9: Readiness Probe Terotentikasi & Verifikasi Checksum Skema

**[FINAL, 2026-10-28]** Standar endpoint kesiapan operasional (`/readyz`):
- Endpoint `/readyz` dilindungi oleh autentikasi bearer (`Depends(authenticate)`), sementara `/livez` dan `/healthz` tetap terbuka untuk pemeriksaan liveness kontainer.
- Kesiapan database diverifikasi secara deterministik terhadap keberadaan tabel wajib dan integritas tabel `kms.schema_migrations`.
- Checksum setiap berkas migrasi disk diverifikasi terhadap rekaman sha256 di database; inkonsistensi versi atau checksum mengembalikan status 503 dengan daftar migrasi yang bermasalah.
- Respons 503 disanitasi penuh sehingga tidak membocorkan traceback mentah, DSN, nama host, atau informasi rahasia server ke klien.

## (i) D10 (D-IMG-1): Antrean Kandidat untuk Citra Varietas Baru

**[FINAL, 2026-10-28]** Pengelolaan citra varietas baru tanpa pembuangan otomatis:
- Citra Google Drive yang diidentifikasi sebagai varietas baru (*OTHER*) oleh model visi tidak dibuang otomatis dan tidak langsung membentuk dokumen pengetahuan.
- Citra masuk ke antrean terstruktur `kms.image_candidates` dengan status `CANDIDATE`.
- Peneliti kurator menentukan nasib setiap kandidat: `PROMOTE` (varietas baru), `MERGE` (tautkan ke varietas terdaftar), atau `DISCARD` (tandai ditolak dan rekam sha256 ke `kms.discarded_images`).

## (j) D11 (D-IMG-2): Aksi PROMOTE dengan Penanda Habitat Belum Diketahui

**[FINAL, 2026-10-28]** Pengangkatan kandidat tanpa lokasi administratif awal:
- Aksi `PROMOTE` diizinkan tanpa menyertakan `habitat_id` definitif.
- Dokumen dibuat menggunakan habitat sentinel `habitat_unknown` dan diberi flag `habitat_unknown: true`.
- Dokumen tersebut otomatis terdeteksi dan disajikan pada antarmuka "Dokumen Perlu Habitat", serta dapat dipindahkan ke habitat definitif via endpoint `POST /documents/{key}/habitat` (`SET_HABITAT`).

## (k) D12 (D-IMG-3): Antrean Kandidat Persisten Tanpa Kedaluwarsa

**[FINAL, 2026-10-28]** Masa aktif entri antrean kandidat:
- Entri pada `kms.image_candidates` bersifat persisten tanpa batas waktu (tidak kedaluwarsa atau terhapus otomatis oleh sistem).
- Setiap kandidat bertahan di antrean hingga kurator memberikan keputusan eksplisit.

## (l) D13 (D-IMG-4): Review Granular Non-Kluster & Aturan Sinyal Fusi

**[FINAL, 2026-10-28]** Standar evaluasi citra dan hierarki sinyal:
- Peninjauan citra kandidat dilakukan secara granular satu per satu tanpa pengelompokan (*clustering*) otomatis.
- Fusi sinyal memadukan nama file, registri varietas (spreadsheet + DB), dan model visi.
- Aturan baku: **Sinyal citra visual menang atas nama file** (*visual wins over filename*). Konflik antara nama file dan bukti visual dialihkan ke peninjauan kurator (`REVIEW_MISMATCH`) dan tidak pernah ditulis otomatis.

## (m) D14: Katalog Atribut Persisten dan Aksi Kurator pada NEW_ATTRIBUTE

- **Masalah:** atribut yang tidak ada di katalog hanya membuat item review `NEW_ATTRIBUTE`; tombol "Setujui" mengubah status item tanpa mendaftarkan atribut atau menulis nilainya, sehingga atribut hilang setelah review.
- **Keputusan:** tiga aksi khusus kurator (`REGISTER_NEW`, `MAP_TO_EXISTING`, `REJECT`, alasan minimal 10 karakter) berlaku untuk semua sel berlabel sama dalam satu draf; katalog ditulis atomik bersama commit dokumen; planner memuat katalog persisten (`GET /attributes/catalog`).
  Bila satu dokumen punya beberapa baris dengan nilai berbeda untuk atribut baru, tidak ada nilai ditulis (mengikuti aturan konflik planner).

## (n) D15: Draf KMS Berasal dari Workbook Run, Bukan Berkas Contoh

- **Masalah:** `get_or_create_draft` jatuh ke `data/samples/data_input.xlsx` atau draf placeholder dan menyimpannya lintas run karena berkas unggahan hanya berupa berkas sementara yang dihapus.
- **Keputusan:** byte workbook disimpan di sesi, draf di-cache per run dan sumber, dan tata letak yang tidak didukung (bukan "Resume Data") atau sumber yang hilang dilaporkan, bukan diganti. Penulisan dokumen varietas-lokasi dibatasi pada tata letak survei lapangan.

## (o) D16: Ekspor CSV Lengkap dan Daftar Varietas Run untuk Foto

- Tombol unduh biasa "Unduh pemetaan lengkap (CSV)" dan "Unduh hasil multimodal lengkap (CSV)" pada halaman Hasil menggantikan ketergantungan pada ikon toolbar tabel (`showSaveFilePicker` tidak menghasilkan unduhan di browser tanpa kepala).
- `extract_run_scope_varieties` mencari header `"karakter"` (bukan hanya `"karakteristik"`) sehingga daftar varietas spreadsheet sampai ke klasifikasi foto; sebelumnya daftar selalu kosong dan semua foto menjadi kandidat varietas baru.

## (p) D17: Skema Kanonik Dinamis (opsional)

- **Keputusan:** baris kanonik tambahan hasil akuisisi ditambahkan setelah baris template dengan id `r_{60 + seq}` (stabil terhadap penggabungan dan pembuangan), disimpan di `kms.schema_rows_ext`, dan dimuat ke `CanonicalSchema` per run bila `KMS_DYNAMIC_SCHEMA` hidup. `schema_version` memuat hash ekstensi (`...+ext.<hash12>`), koleksi Chroma terpisah per skema, dan keluaran Excel menambah baris di bawah template.
  Dengan saklar mati, `schema_version`, fingerprint, pemetaan, dan Excel identik dengan sebelumnya (diuji regresi). Penggabungan menjadikan label dan alias baris yang kalah alias baris tujuan (template atau akuisisi) tanpa mengubah id.
- **Batasan:** domain baris akuisisi dibatasi pada biji, buah, bunga, daun, dan vegetatif (lapisan KMS lama menolak domain lain); atribut lingkungan masuk ke vegetatif. Review `NULL_TARGET` dari pemeta tetap tersisa di antrean untuk atribut yang diakuisisi.

## (q) D18: Kegagalan model visi tidak boleh diganti jawaban tiruan (mock)

- **Masalah:** `default_lvm_call()` sebelumnya diam-diam memanggil `deterministic_mock_lvm()` bila kunci provider tidak ada atau panggilan 9Router gagal (mis. `InstructorRetryException`). Mock tidak melihat gambar: ia menjawab KNOWN dari nama berkas (confidence 0,90), OTHER 0,70, atau UNCERTAIN 0,40, dan selalu bagian `DAUN` (kata "daun" selalu ada di prompt). Keluarannya tidak dapat dibedakan dari jawaban model dan lolos fusi sebagai AUTO_LINK. Pada run evaluasi UI 1 Nov 2026, 19 dari 160 foto Commons ternyata jawaban mock (8 di antaranya tertaut ke baris Gambar Daun yang salah; 7 dari 11 tautan salah pada nama berkas menyesatkan berasal dari mock).
- **Keputusan:** mock hanya dipakai bila diminta eksplisit (`CABAI_KMS_VISION_PROVIDER=mock`) atau di dalam pytest (isolasi kuota A28). Tanpa kunci provider, `default_lvm_call()` melempar `VisionProviderUnavailable`; galat provider/kontrak diteruskan ke pemanggil. `vision_hook` mencatat foto sebagai `FAILED` ("Vision provider/contract failed"), dan jalur non-KMS melalui `safe_classify_image()` mencatat kegagalan di trace; tidak ada tautan atau kandidat yang dibuat dari foto gagal.
- **Konsekuensi:** run yang terkena gangguan provider kini menampilkan foto `FAILED` alih-alih hasil palsu; jumlah foto gagal harus dilaporkan dalam evaluasi. Tes: `tests/vision/test_vision_no_silent_mock.py`.
- **Jejak sebelum perbaikan:** jawaban mock dapat dikenali dari `visual_evidence` yang diawali "Ciri morfologi visual ... cocok dengan deskripsi", "Morfologi ... tidak cocok dengan varietas run aktif", atau "Bukan organ tanaman cabai atau citra tidak meyakinkan".

## (r) D19: Data evaluasi cabai dibatasi pada level varietas/kultivar

- **Masalah:** sebagian data evaluasi tidak menunjuk varietas. Contohnya: kolom Jenis Cabai R01 hanya berisi spesies ("Cabai rawit (*C. frutescens*)"); daftar varietas foto Commons memuat nama jenis umum (Cabai Rawit, Cabai Korea) dan nama tipe buah atau *cultivar group* (Jalapeño, Habanero, Cayenne, Serrano, Paprika/bell, Scotch Bonnet, Banana Pepper); genotipe Zenodo sebagian besar bernama tipe/landrace Brasil; foto berlabel UNCERTAIN dan foto iNaturalist hanya sampai spesies.
- **Keputusan (peneliti, 4-5 Nov 2026):** hanya data yang namanya sampai level varietas atau kultivar yang dipakai: varietas terdaftar Kementan (Kepmentan/tanda daftar), varietas lokal terdaftar (Katokkon, Kopay), atau kultivar bernama (mis. 'Red Savina', 'Cheongyang', 'Hungarian Wax', Tabasco). "Varietas" di sini berarti varietas budidaya, bukan rank botani *var.* Data yang gagal dipindah ke `_dikeluarkan_bukan_varietas/` (tidak dihapus permanen) dengan `data_evaluasi/skrip/keluarkan_non_varietas.py` (`--tahap1` spesies/jenis umum, `--tahap2` nama tipe). Lima foto Commons dinaikkan labelnya ke nama kultivar (2 Cheongyang, 2 Red Savina, 1 De Cayenne) dan menjadi OTHER karena tidak ada di daftar varietas terdaftar.
- **Konsekuensi:** foto Commons tersisa 43 dari 160; daftar varietas run foto 8 nama tinggal Hungarian Wax; G01/G02 tinggal Hungarian Wax (+ Poblano); N08 tinggal 4 genotipe; R01 keluar seluruhnya. Skor foto dan atribut di draf paper masih dihitung dari data sebelum pembersihan, sehingga gold perlu disaring, daftar varietas terdaftar ditetapkan ulang, dan run foto diulang. ID butir gold untuk workbook yang isinya berubah (S01, S03, N08) tidak lagi cocok dengan berkasnya.
- **Belum diputuskan:** Gendot dan Domba (nama lokal untuk tipe, tanpa bukti pendaftaran), baris GRIN "Tipo Poblano" (tanpa nama kultivar), dan Bhut Jolokia (landrace tanpa pendaftaran formal). Rincian, bukti, dan sumber: `data_evaluasi/KLASIFIKASI_LEVEL_VARIETAS.md`.

## (s) D20: Kode mengikuti identitas level varietas/kultivar

- **Masalah:** setelah D19, beberapa bagian kode masih mengasumsikan identitas level spesies/jenis. (1) `VarietyRegistry` membuang token angka, sehingga nama berkas `turima_2_05.jpg` cocok persis dengan "Turima 1" dan "Turima 2" (urutan alfabet memilih Turima 1). (2) `VisionSession` memberi model hanya deskripsi morfologi dari kolom template, dicocokkan dengan substring; varietas run di luar template (mis. varietas PVT) hanya terkirim sebagai nama, dan jalur non-KMS bahkan menawarkan varietas template, bukan varietas run. (3) Petunjuk nama berkas tanpa registry memakai daftar kata jenis yang di-hardcode ("rawit", "besar", "habanero"...). (4) Form review foto menawarkan "Cabai rawit"/"cabai besar" sebagai pilihan bawaan dan mengizinkan dokumen baru level `species`/`source_category`.
- **Keputusan (peneliti, 5 Nov 2026):** (1) nama varietas yang memuat angka dicocokkan dengan token berurutan (angka varietas harus mengikuti namanya; nomor urut foto tidak dibaca sebagai nomor varietas), tanpa fuzzy. (2) Deskripsi varietas untuk model vision dibaca dari sheet kanonik run aktif (nilai run menang atas template), kecocokan nama template persis setelah normalisasi; kedua jalur (KMS dan non-KMS) memakai varietas run. (3) Daftar kata jenis dihapus; tanpa registry dipakai registry dari varietas run. (4) Dokumen varietas baru (CREATE_NEW_DOCUMENT foto dan PROMOTE kandidat) wajib bernama dan hanya `cultivar` (`require_variety_level_identity`), diperiksa di UI dan di server; kontrak `PlantIdentity` tetap menerima level lama agar dokumen tersimpan sebelum D19 masih terbaca.
- **Jalur penulisan dokumen KMS (`PlantCatalog.resolve`, keputusan peneliti 5 Nov 2026):** sebelumnya nama yang memuat "rawit" atau "merah"/"besar" dilebur ke identitas jenis "Cabai rawit"/"Cabai besar" (varietas berbeda bisa tergabung dalam satu dokumen), sedangkan nama varietas di luar katalog ditolak. Sekarang: (a) label yang hanya berisi kata spesies/jenis ("Cabai rawit (Capsicum frutescens L)", "cabai besar", "Capsicum annuum L.") **ditolak** menjadi item review `PLANT_IDENTITY_UNRESOLVED` tanpa dokumen; (b) kultivar katalog yang disebut dikembalikan apa adanya; (c) nama varietas lain dari kolom varietas spreadsheet **langsung menjadi identitas kultivar** sendiri (`plant_<slug nama>`). Konsekuensi: R01 (`data/samples/data_input.xlsx`) tidak lagi membentuk dokumen KMS; tes jalur penulisan KMS memakai fixture sintetis `tests/fixtures/resume_data_varietas.xlsx` (tata letak sama, nama varietas). Dokumen level jenis yang sudah tersimpan tetap terbaca. Penulisan dokumen tetap terbatas pada tata letak survei lapangan "Resume Data" (keputusan sebelumnya, tidak diubah di sini).
- Tes: `tests/vision/test_variety_registry.py`, `tests/test_vision_classification.py`, `tests/ui/test_photo_review_ui.py`, `tests/storage/test_round4_storage.py`, `tests/storage/test_identity_resolution.py`, `tests/storage/test_document_planner.py`.
