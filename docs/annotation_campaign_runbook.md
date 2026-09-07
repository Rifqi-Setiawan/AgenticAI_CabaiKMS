# Pilot and final annotation campaign runbook

Pilot version: `schema-mapping-pilot-v1`  
Final readiness version: `final-research-validation-v1`

The current one-workbook, 13-item package is explicitly a pilot for rehearsing fill, validation, agreement, adjudication, and finalization. It is not sufficient final research gold and must not automatically enter calibration. Its authoritative scope is `eval/campaigns/schema-mapping-pilot-v1/manifest.json`; both annotator workbooks derive from the same frozen master.

Final research readiness is tracked separately at `eval/campaigns/final-research-validation-v1/readiness.json`. The synthetic repository samples do not count as missing real validation workbooks.

## Final research readiness diagnostic

```powershell
.\.venv\Scripts\python.exe eval/prepare_annotation_campaign.py `
  --manifest eval/campaigns/final-research-validation-v1/manifest.json `
  --output-dir eval/campaigns/final-research-validation-v1 `
  --readiness-only
```

This command emits diagnostic readiness only. It must not emit a final master or annotation templates until the real heterogeneous dataset meets the declared gate.

## Package generation

```powershell
.\.venv\Scripts\python.exe eval/prepare_annotation_campaign.py `
  --manifest eval/campaigns/schema-mapping-pilot-v1/manifest.json `
  --output-dir eval/campaigns/schema-mapping-pilot-v1
```

The command always writes `readiness.json` from actual inputs. It emits no master or A/B templates unless readiness is true, and refuses to overwrite existing frozen artifacts.

## Independent annotation and exact validation

Give each annotator only their own round-1 workbook and `docs/annotation_guidelines_v1.md`. After both files are complete, preserve immutable copies and record their hashes. Validate the pair without calculating agreement:

```powershell
.\.venv\Scripts\python.exe eval/validate_mapping_annotations.py `
  --annotations eval/campaigns/schema-mapping-pilot-v1/round1/annotator_A_round1.xlsx `
  --compare eval/campaigns/schema-mapping-pilot-v1/round1/annotator_B_round1.xlsx `
  --pair-only
```

This enforces complete required fields, one annotator ID per artifact, different A/B IDs, identical `mapping_item_id` universes, verified immutable identity, valid canonical keys, and one matching annotation round.

## Agreement and adjudication

Only after A/B pass validation and their completed hashes are frozen, run:

```powershell
.\.venv\Scripts\python.exe eval/validate_mapping_annotations.py `
  --annotations eval/campaigns/schema-mapping-pilot-v1/round1/annotator_A_round1.xlsx `
  --compare eval/campaigns/schema-mapping-pilot-v1/round1/annotator_B_round1.xlsx `
  --disagreements-output eval/campaigns/schema-mapping-pilot-v1/adjudication/disagreements_round1.xlsx
```

The output reports number compared, raw agreement, Cohen's kappa, `kappa_defined`, `kappa_undefined_reason`, exclusions, and disagreement count. Matching is by `mapping_item_id`, never row position. No value is precomputed in this package.

The generated disagreement workbook contains immutable identity/context, both annotator IDs and decisions, and disagreement type. The adjudicator edits only `adjudicated_status`, `adjudicated_canonical_keys`, `adjudicator_id`, and `adjudication_notes`. Do not add/delete rows, automatically select A or B, or consult system predictions as truth.

## Final adjudicated gold

After every disagreement has an explicit resolution, run:

```powershell
.\.venv\Scripts\python.exe eval/finalize_mapping_annotations.py `
  --annotations-a eval/campaigns/schema-mapping-pilot-v1/round1/annotator_A_round1.xlsx `
  --annotations-b eval/campaigns/schema-mapping-pilot-v1/round1/annotator_B_round1.xlsx `
  --adjudication eval/campaigns/schema-mapping-pilot-v1/adjudication/disagreements_round1.xlsx `
  --campaign-metadata eval/campaigns/schema-mapping-pilot-v1/metadata.json `
  --output-final eval/campaigns/schema-mapping-pilot-v1/adjudication/adjudicated_validation_gold.xlsx `
  --output-history eval/campaigns/schema-mapping-pilot-v1/adjudication/adjudication_history.json
```

The final workbook includes campaign version and frozen evaluation fingerprint, preserves stable source identity, and is reloaded through the strict gold loader. The history JSON retains A, B, agreement/adjudication state, and final decision. Do not run this until humans complete adjudication; this repository intentionally contains no fabricated final gold.

Stop after campaign preparation. Threshold tuning, retrieval/reranking changes, calibration, production acceptance changes, and Phase 7C2B are out of scope.
