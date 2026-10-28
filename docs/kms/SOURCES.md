# Source register

Accessed for design verification: **29 September 2026**. Public branch views may update independently; no single upstream commit was cloned and executed in the authoring environment. The installer records the actual VPS commit. These sources support the architecture discussion, not a claim of benchmark results or a live deployment.

## Repository evidence

- Repository and README: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS
- Project guide / supported backends: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/docs/PROJECT_GUIDE.md
- UI input and temporary file lifecycle: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/ui/app.py
- Review/results UI: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/ui/pages/3_Hasil.py
- Runtime/result contracts: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/ui/pipeline_runner.py
- Deterministic review replay: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/ui/review_replay.py
- Append-only local queue: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/agents/schema_matching/review_queue.py
- Canonical identity/hash semantics: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/schema/canonical.py
- Existing domains: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/schema/row_domains.yaml
- Provenance contract: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/schema/provenance.py
- Graph and vision rows: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/orchestrator/graph.py
- Vision providers, filename signal and image bytes: https://github.com/Rifqi-Setiawan/AgenticAI_CabaiKMS/blob/main/src/agents/vision_classification.py

## Primary technical references

- PostgreSQL INSERT/ON CONFLICT: https://www.postgresql.org/docs/current/sql-insert.html
- PostgreSQL backup/PITR: https://www.postgresql.org/docs/16/continuous-archiving.html
- SQLAlchemy PostgreSQL upsert: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert
- Psycopg 3 release and package: https://pypi.org/project/psycopg/
- pgvector exact/approximate search and index trade-offs: https://github.com/pgvector/pgvector
- Apache AGE: https://age.apache.org/
- LangGraph persistence concepts: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph PostgreSQL checkpointer: https://reference.langchain.com/python/langgraph.checkpoint.postgres
- Celery task retries/idempotency: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- Temporal activity requirements: https://docs.temporal.io/activity-definition
- Next.js LTS policy: https://nextjs.org/support-policy
- Azure temporary disks are not persistent: https://learn.microsoft.com/en-us/azure/virtual-machines/linux/disks-format-mount-temp-disks-linux
- R2 S3 setup and scoped credentials: https://developers.cloudflare.com/r2/get-started/s3/
- R2 S3 extensions/conditional operations: https://developers.cloudflare.com/r2/api/s3/extensions/
- R2 private/presigned access: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- Google Drive downloads: https://developers.google.com/workspace/drive/api/guides/manage-downloads
- Google auth library: https://pypi.org/project/google-auth/
- Pillow decoding and decompression limits: https://pillow.readthedocs.io/en/stable/reference/Image.html
- Caddy forward authentication: https://caddyserver.com/docs/caddyfile/directives/forward_auth

No external source establishes that this package is production-certified, that the supplied VPS uses a persistent NVMe disk, that the actual gateway model aliases resolve as expected, or that the user's metrics meet a particular accuracy target. Those claims require live evidence from the deployment.
