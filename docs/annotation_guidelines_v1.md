# Annotation guidelines v1

Version: `annotation-guidelines-v1`  
Campaign: `schema-mapping-validation-campaign-v1`  
Round: `1`

Annotate from the source label, structural context, representative values, and the `Canonical Reference` sheet only. The model's proposed target, confidence, retrieval results, verifier result, and acceptance result are intentionally absent. Do not seek them out, infer a decision from them, or consult the other annotator before both first passes are frozen.

Only the yellow fields are editable: `gold_status`, `gold_canonical_keys`, `ambiguous_candidate_canonical_keys`, `annotator_id`, `annotation_round`, and `notes`. Use one pseudonymous annotator ID throughout the workbook, enter round `1`, never add/delete/reorder rows, and never edit identity or provenance. Canonical-key lists use `|`, for example `panjang_daun|lebar_daun`; do not enter display labels or row numbers.

## Decision categories

### ONE_TO_ONE

Definition: exactly one source attribute expresses exactly one canonical characteristic. Put exactly one key in `gold_canonical_keys`; leave ambiguous candidates blank.

Positive example: `Panjang daun (cm)` with numeric length values maps to `panjang_daun`. A spelling variant or established synonym such as `leaf length` is still one-to-one when context and values agree.

Counterexample: `Panjang dan lebar daun` requires two concepts and is `COMPOSITE`. `Ukuran daun` with no dimension context may be `AMBIGUOUS`. A merely similar phrase with incompatible meaning is not one-to-one.

Boundary rule: units and formatting do not create a different concept. Convert neither values nor units in the annotation workbook; use them only as semantic evidence. A missing value in some observations does not prevent one-to-one when the label and remaining evidence are clear.

### NO_MATCH

Definition: the attribute is valid and usable, but no canonical characteristic represents its meaning. Leave both canonical-key fields blank.

Positive example: a valid administrative field such as `Nama peneliti` when the canonical schema contains only plant characteristics.

Counterexample: do not force a broad or lexically close canonical key. Do not use `NO_MATCH` for malformed/unusable data (`EXCLUDE`) or for two plausible targets (`AMBIGUOUS`).

Boundary rule: absence of values alone is not automatically no-match. If the label clearly names a canonical characteristic, use the semantic decision and mention missingness in `notes`; if missingness removes the evidence needed to interpret a vague label, use `AMBIGUOUS` or `EXCLUDE` as described below.

### AMBIGUOUS

Definition: available evidence is insufficient to choose confidently among two or more plausible canonical targets. Leave `gold_canonical_keys` blank and list every plausible key in `ambiguous_candidate_canonical_keys`.

Positive example: `Lebar` under an unclear merged header where both fruit width and leaf width remain plausible; record `lebar_buah|lebar_daun`.

Counterexample: difficulty alone is not ambiguity. A known synonym supported by context is `ONE_TO_ONE`; a field intentionally combining concepts is `COMPOSITE`; no valid candidate is `NO_MATCH`.

Boundary rule: when uncertainty is material, state what evidence is missing in `notes`. Do not resolve uncertainty from model output. If only one candidate remains after using source context, values, units, and canonical examples, use `ONE_TO_ONE`.

### COMPOSITE

Definition: one source attribute semantically contains multiple canonical concepts and cannot be represented as a clean one-to-one mapping. Put every required key in `gold_canonical_keys`; leave ambiguous candidates blank.

Positive example: `Panjang x lebar daun` stored together represents both `panjang_daun` and `lebar_daun`.

Counterexample: alternatives such as “could be fruit width or leaf width” are `AMBIGUOUS`, not composite. Multiple units or formatting variants of one characteristic remain `ONE_TO_ONE`.

Boundary rule: use composite only when all listed concepts are actually present, not because one source label contains several words. Explain the segmentation briefly in `notes` when it is not obvious.

### EXCLUDE

Definition: the item is outside the evaluation scope or cannot be evaluated because the source is malformed, unreadable, or otherwise unusable for a documented reason. Leave both key fields blank and make `notes` non-empty.

Positive example: a parser artifact that is not a real source attribute, or an irretrievably corrupted label/value region.

Counterexample: a valid out-of-schema field is `NO_MATCH`. A duplicate-looking attribute is not automatically excluded; distinguish it using structural context. If duplicate labels cannot receive stable identity, campaign readiness must fail before annotation rather than asking humans to invent identity.

Boundary rule: missing values justify exclusion only when neither label, context, nor usable observations provide enough evidence and the item cannot fairly be categorized. Record the exact reason.

## Cross-cutting rules

- Duplicate-looking attributes: compare their structural contexts and values. Annotate each stable `mapping_item_id` independently. Never merge IDs or manufacture an ID.
- Synonyms: accept a synonym as `ONE_TO_ONE` only when its conventional meaning, context, and values identify one canonical concept.
- Units and formatting: units, punctuation, capitalization, abbreviations, decimal separators, and presentation differences are evidence, not separate characteristics. Do not normalize workbook contents.
- Missing values: judge the attribute, not each cell. Partial missingness normally does not change the semantic category; total missingness may require `AMBIGUOUS` or documented `EXCLUDE` depending on label/context evidence.
- Uncertainty: use `AMBIGUOUS` for competing valid targets and document the missing evidence. Never use confidence scores or hidden predictions.

## Human fields

- `gold_canonical_keys`: one key for `ONE_TO_ONE`, two or more keys for `COMPOSITE`, blank for the other statuses.
- `ambiguous_candidate_canonical_keys`: two or more plausible keys for `AMBIGUOUS`; blank otherwise.
- `notes`: concise evidence for difficult cases; mandatory in practice for `EXCLUDE`, recommended for ambiguity/composite boundaries, and never a place to copy model output.
