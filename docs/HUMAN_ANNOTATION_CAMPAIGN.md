# Validation human-annotation campaign

Campaign version: `schema-mapping-human-campaign-v1`

## Frozen validation scope

The round-1 validation manifest is
`data/evaluation/validation_manifest.json`. It contains the repository's only
non-synthetic sample workbook:

- `data/samples/data_input.xlsx`
- SHA-256 `71e86f98a416d2f269b873c3a2c96bc729837fac0b104a79089e9d70fd093056`
- sheet `Resume Data`
- format `row-oriented`
- 13 annotatable source attributes
- 0 unavailable stable identities

The two filenames containing `sintetis` are not part of this field-data validation
campaign. No test split is created by this campaign.

Frozen evaluation settings are `legacy` source backend, `exact` retrieval backend,
`k=8`, canonical schema `cabai-kms-canonical-v1`, Mapping Verifier
`mapping-verification-v1`, and embedding model
`paraphrase-multilingual-MiniLM-L12-v2`. The expected evaluation configuration
fingerprint is
`9bbc2b52332d585895eac0800e1fa1ebdbbc475fac4c30a7e2ee2c5d534fb0fb`.

## Create independent templates

Run the frozen pipeline once and create two identical, prediction-blinded templates:

```powershell
.\.venv\Scripts\python.exe eval/prepare_annotation_campaign.py `
  --manifest data/evaluation/validation_manifest.json `
  --input-dir data/samples `
  --output-dir data/evaluation/campaign_round_1 `
  --annotation-round 1 `
  --source-backend legacy `
  --retrieval-backend exact `
  -k 8
```

The command refuses to overwrite campaign files. It validates workbook hashes,
configuration fingerprint, stable identities, and duplicate item IDs. It writes
`annotations_A.xlsx`, `annotations_B.xlsx`, and `campaign_metadata.json`. Both
workbooks contain an `Annotations` sheet followed by a read-only reference view of the
canonical keys. Human fields start blank. Follow `docs/HUMAN_ANNOTATION_GUIDE.md`.

Give each annotator only their own copy. They must not exchange files before both
first-pass files are returned.

## Validate and compare completed first passes

```powershell
.\.venv\Scripts\python.exe eval/validate_mapping_annotations.py `
  --annotations data/evaluation/campaign_round_1/annotations_A.xlsx

.\.venv\Scripts\python.exe eval/validate_mapping_annotations.py `
  --annotations data/evaluation/campaign_round_1/annotations_B.xlsx

.\.venv\Scripts\python.exe eval/validate_mapping_annotations.py `
  --annotations data/evaluation/campaign_round_1/annotations_A.xlsx `
  --compare data/evaluation/campaign_round_1/annotations_B.xlsx `
  --disagreements-output data/evaluation/campaign_round_1/adjudication.xlsx
```

The comparison reports raw agreement, Cohen's kappa, number compared, number excluded
from kappa, and disagreement count. Matching is by `mapping_item_id`, never row order.
No agreement value should be reported until both human files are complete.

## Adjudicate disagreements

The generated adjudication workbook contains immutable identity and source context,
both annotator IDs, statuses and canonical-key decisions, plus the disagreement type.
The adjudicator edits only:

- `adjudicated_status`
- `adjudicated_canonical_keys`
- `adjudicator_id`
- `adjudication_notes`

No row may be added, removed, or automatically resolved. The adjudicator uses the same
status definitions and canonical-key encoding as the independent annotators.

## Create final validation gold

After every disagreement is adjudicated, run:

```powershell
.\.venv\Scripts\python.exe eval/finalize_mapping_annotations.py `
  --annotations-a data/evaluation/campaign_round_1/annotations_A.xlsx `
  --annotations-b data/evaluation/campaign_round_1/annotations_B.xlsx `
  --adjudication data/evaluation/campaign_round_1/adjudication.xlsx `
  --output-final data/evaluation/campaign_round_1/adjudicated_validation_gold.xlsx `
  --output-history data/evaluation/campaign_round_1/adjudication_history.json
```

The command validates the adjudication item set and immutable fields, merges agreements
and explicit resolutions with `merge_adjudicated_gold()`, writes the full A/B and
adjudication history to JSON, and reloads the flat final workbook through the strict
gold loader before completing. It refuses to overwrite existing outputs.

Do not run calibration analysis or Phase 7C2B as part of this workflow.
