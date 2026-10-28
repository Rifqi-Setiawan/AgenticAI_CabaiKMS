# Implementation status and limits

## Implemented in this package

PostgreSQL DDL and checksummed transactional migration; SQLAlchemy 2 repositories; idempotent stage/commit; optimistic revisions and explicit rebase; append-only observations, review decisions, draft revisions and audit; source registry; full original-output snapshot for review recovery; original/current value separation; protection against automatic demotion of human-reviewed projection; scoped gold and curator-promoted/revocable aliases; signed at-least-once transactional outbox delivery; bounded authenticated API; local/S3 CAS; original evidence and scrubbed WebP/thumbnail; same-inference-bytes hashing; additive upstream integration installer; Streamlit commit/inspection/recovery functions; operational scripts and tests.

The integration installer modifies only the named upstream integration points. Core provider/model matching/normalization settings are not replaced. KMS_ENABLED defaults false.

## Implemented but not live-verified here

All SQL transaction behavior, triggers, grants, PostgreSQL migration and live concurrency; Drive service-account downloads; S3/R2 bucket permissions and live conditional PUT; full Streamlit UI execution against the actual upstream checkout; full LangGraph invocation, review replay and actual provider responses; Caddy/systemd/Ubuntu installation; Azure disk persistence; disaster recovery. See the validation report for executed test evidence.

The real PostgreSQL tests are included and intentionally skipped without a disposable server. S3 tests use SDK stubs. Installer tests use minimal representative source fixtures; they do not imply a successful patch against every upstream commit.

## Designed, not silently activated

Durable multi-file ingestion job scheduler; full FastAPI ownership of the ingestion engine; Celery/Temporal deployment; PostgreSQL LangGraph checkpoint migration; pgvector retrieval replacement and embedding regeneration; automatic insertion of learned aliases/few-shots into existing matcher prompts; learned confidence calibration; specimen/accession/measurement-event normalized domain model; OIDC and individual non-repudiation; row-level tenant isolation; Next.js portal; signed dataset releases; automatic media garbage collection or cross-backend migration; PITR/HA backup infrastructure.

These are roadmap items, not empty placeholder implementations in the code. The delivered outbox is a notification worker, not a background ingestion worker. Current initial ingestion still runs in Streamlit until the worker phase is implemented and validated.

## Security model

Single trusted research workspace. Reader can inspect the entire workspace; reviewer can stage/commit runs; curator can rebase/promote aliases. Token possession defines the API principal. Text typed in the old reviewer form is retained as reported identity, not authenticated proof of that person. No secret tokens are embedded in URLs.

Database users with app credentials are trusted application infrastructure, not end-user SQL accounts. Root, schema owner and cloud account administrators remain privileged. Append-only SQL triggers do not constitute external WORM or cryptographic proof against those administrators. Release/backup control is part of the production trust boundary.

Catalog registration is performed through the trusted acquisition adapter and checked for version consistency at commit. A future multi-user SaaS deployment needs a curator-owned catalog control plane and signed/approved catalog identities in addition to tenant access control.

## Compatibility caveats

Catalog units/types default to conservative text until explicit overrides are curated. Legacy runs that lost the source workbook cannot recover it from a hash; source-less commit is rejected by default. Legacy accepted vision rows without asset IDs require reprocessing with the storage hook; the adapter will not manufacture an identity from a filename or silently download a potentially changed Drive version.

Switching storage backends after registration requires a data migration. Original assets remain private and may still contain EXIF. Only served derivatives are metadata-stripped. WebP input changes can alter vision results and must be evaluated.

The package provides direct dependency pins and records the local tested environment, not a platform-independent fully hash-locked transitive dependency graph. Resolve and lock with the existing project before activation.
