-- CABAI-KMS migration 0005. Additive least-privilege permissions for cabai_app.
-- Applied transactionally by migrate.py.

DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cabai_app') THEN
    GRANT DELETE ON kms.knowledge_documents TO cabai_app;
    GRANT UPDATE ON kms.discarded_images TO cabai_app;
  END IF;
END $$;
