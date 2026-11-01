-- CABAI-KMS migration 0007. Acquired canonical rows (dynamic schema, phase 2).
-- Rows only ever get appended; status and merge fields are the only mutable columns (guarded by trigger).

CREATE TABLE IF NOT EXISTS kms.schema_rows_ext (
  seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  canonical_key text NOT NULL UNIQUE,
  label text NOT NULL,
  label_norm text NOT NULL UNIQUE,
  domain text NOT NULL,
  examples jsonb NOT NULL DEFAULT '[]'::jsonb,
  aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'provisional' CHECK (status IN ('provisional', 'approved', 'merged', 'discarded')),
  merged_into_key text,
  source_label text,
  source_file_sha256 text,
  created_from_run text NOT NULL,
  created_by text NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_by text,
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS kms.schema_aliases_ext (
  alias_norm text PRIMARY KEY,
  alias text NOT NULL,
  target_key text NOT NULL,
  created_from_run text NOT NULL,
  created_by text NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kms.schema_row_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  canonical_key text NOT NULL,
  event text NOT NULL,
  actor text NOT NULL,
  run_id text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION kms.schema_rows_ext_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'kms.schema_rows_ext rows cannot be deleted';
  END IF;
  IF NEW.seq <> OLD.seq OR NEW.canonical_key <> OLD.canonical_key OR NEW.label <> OLD.label
     OR NEW.label_norm <> OLD.label_norm OR NEW.domain <> OLD.domain OR NEW.created_from_run <> OLD.created_from_run
     OR NEW.created_by <> OLD.created_by OR NEW.created_at <> OLD.created_at THEN
    RAISE EXCEPTION 'only status, aliases, examples and merge fields of kms.schema_rows_ext may change';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS schema_rows_ext_guard ON kms.schema_rows_ext;
CREATE TRIGGER schema_rows_ext_guard BEFORE UPDATE OR DELETE ON kms.schema_rows_ext
  FOR EACH ROW EXECUTE FUNCTION kms.schema_rows_ext_guard();
DROP TRIGGER IF EXISTS reject_truncate ON kms.schema_rows_ext;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.schema_rows_ext
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

DROP TRIGGER IF EXISTS reject_change ON kms.schema_aliases_ext;
CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.schema_aliases_ext
  FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();
DROP TRIGGER IF EXISTS reject_truncate ON kms.schema_aliases_ext;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.schema_aliases_ext
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

DROP TRIGGER IF EXISTS reject_change ON kms.schema_row_events;
CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.schema_row_events
  FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();
DROP TRIGGER IF EXISTS reject_truncate ON kms.schema_row_events;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.schema_row_events
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

REVOKE ALL ON kms.schema_rows_ext, kms.schema_aliases_ext, kms.schema_row_events FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cabai_app') THEN
    GRANT SELECT, INSERT, UPDATE ON kms.schema_rows_ext TO cabai_app;
    GRANT SELECT, INSERT ON kms.schema_aliases_ext, kms.schema_row_events TO cabai_app;
  END IF;
END $$;
