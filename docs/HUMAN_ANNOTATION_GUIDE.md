# Human schema-mapping annotation guide

> **PILOT ONLY:** The current 13-item workbook is for rehearsing the human workflow. Its labels must not automatically become final research/calibration gold. The final research campaign remains blocked pending additional real heterogeneous workbooks and a preregistered minimum sample size.

Instruction version: `human-schema-mapping-v1`

## Independent annotation rules

Annotate each source attribute independently from the other annotator. Use the
`Canonical Reference` worksheet to inspect valid canonical keys. The template is
prediction-blinded: do not consult pipeline predictions, historical review files, or
the other annotator's decisions before submitting the first pass.

Only edit these human-decision columns:

- `gold_status`
- `gold_canonical_keys`
- `ambiguous_candidate_canonical_keys`
- `annotator_id`
- `annotation_round`
- `notes`

Do not edit `mapping_item_id`, `mapping_identity_kind`, `mapping_identity_value`,
`source_file_sha256`, `source_sheet`, `source_format`, or any other provenance or
configuration column. Use one pseudonymous annotator ID throughout one workbook.
Annotator A and Annotator B must use different IDs. For this campaign, enter
annotation round `1`.

Canonical-key lists use `|` as the separator, without row IDs or display labels.
Examples: `panjang_daun` or `panjang_daun|lebar_daun`.

## Status definitions

### ONE_TO_ONE

Use when the source attribute has one clear semantic equivalent in the canonical
schema. Enter exactly one value in `gold_canonical_keys`.

Do not use when more than one canonical row is required, when two or more targets are
plausible but unresolved, or when no target exists.

### NO_MATCH

Use when the source attribute is outside the canonical schema or when the schema has
no semantically valid target. Leave both canonical-key columns blank.

Do not force a nearby or broader canonical row merely because its wording is similar.

### AMBIGUOUS

Use when the available source label, context, and values do not support one defensible
decision between multiple canonical rows. Leave `gold_canonical_keys` blank and list
the plausible keys in `ambiguous_candidate_canonical_keys`, separated by `|`.

Do not use merely because the decision took effort. If the evidence supports one
target, use `ONE_TO_ONE`; if no candidate is valid, use `NO_MATCH`.

### COMPOSITE

Use when one source attribute intentionally contains information belonging to two or
more canonical rows and all are needed to represent its meaning. Enter every required
key in `gold_canonical_keys`, separated by `|`.

Do not use for uncertainty between alternatives. Alternative plausible targets are
`AMBIGUOUS`, not `COMPOSITE`.

### EXCLUDE

Use when the item cannot be fairly evaluated because the source itself is malformed,
unreadable, duplicated without a resolvable identity, or otherwise outside the stated
annotation task. Leave canonical-key fields blank and explain the reason in `notes`.

Do not use `EXCLUDE` for a valid attribute that is merely outside the canonical schema;
that case is `NO_MATCH`.

## Uncertainty and notes

Base decisions on source meaning, structural context, and representative source
values. Record concise evidence in `notes` when uncertainty or exclusion is material.
Never use model confidence or predicted targets as evidence. Do not invent a stable
identity for an item whose identity is unavailable; report it to the campaign owner.
