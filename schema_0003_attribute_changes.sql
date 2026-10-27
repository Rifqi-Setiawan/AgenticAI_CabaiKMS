-- CABAI-KMS migration 0003. Additive attribute change history ledger.
-- Applied transactionally by migrate.py.

CREATE TABLE IF NOT EXISTS kms.document_attribute_changes (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  doc_id text NOT NULL,
  attribute_id text NOT NULL,
  old_value jsonb NOT NULL,
  new_value jsonb NOT NULL,
  run_id text NOT NULL,
  actor text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS document_attribute_changes_doc_idx
  ON kms.document_attribute_changes (doc_id);

CREATE INDEX IF NOT EXISTS document_attribute_changes_attr_idx
  ON kms.document_attribute_changes (attribute_id);

CREATE INDEX IF NOT EXISTS document_attribute_changes_run_idx
  ON kms.document_attribute_changes (run_id);

DROP TRIGGER IF EXISTS reject_change ON kms.document_attribute_changes;
CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.document_attribute_changes
  FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();

DROP TRIGGER IF EXISTS reject_truncate ON kms.document_attribute_changes;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.document_attribute_changes
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

REVOKE ALL ON kms.document_attribute_changes FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cabai_app') THEN
    GRANT SELECT, INSERT ON kms.document_attribute_changes TO cabai_app;
  END IF;
END $$;
