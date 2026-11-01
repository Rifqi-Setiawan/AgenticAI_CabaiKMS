-- CABAI-KMS migration 0006. Persistent attribute catalog extensions (append-only).
-- Applied transactionally by migrate.py. The 59-row canonical template stays in data/canonical;
-- rows here extend it with curator-approved attributes, aliases and remembered rejections.

CREATE TABLE IF NOT EXISTS kms.attribute_catalog_ext (
  attribute_id text PRIMARY KEY,
  canonical_key text NOT NULL UNIQUE,
  label text NOT NULL,
  label_norm text NOT NULL UNIQUE,
  organ text NOT NULL,
  value_type text NOT NULL,
  unit text,
  description text,
  development_stage text,
  source_label text,
  created_from_run text NOT NULL,
  created_by text NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kms.attribute_alias_ext (
  alias_norm text PRIMARY KEY,
  alias text NOT NULL,
  attribute_id text NOT NULL,
  created_from_run text NOT NULL,
  created_by text NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kms.attribute_rejections (
  label_norm text PRIMARY KEY,
  source_label text NOT NULL,
  created_from_run text NOT NULL,
  created_by text NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS reject_change ON kms.attribute_catalog_ext;
CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.attribute_catalog_ext
  FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();
DROP TRIGGER IF EXISTS reject_truncate ON kms.attribute_catalog_ext;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.attribute_catalog_ext
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

DROP TRIGGER IF EXISTS reject_change ON kms.attribute_alias_ext;
CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.attribute_alias_ext
  FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();
DROP TRIGGER IF EXISTS reject_truncate ON kms.attribute_alias_ext;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.attribute_alias_ext
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

DROP TRIGGER IF EXISTS reject_change ON kms.attribute_rejections;
CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.attribute_rejections
  FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();
DROP TRIGGER IF EXISTS reject_truncate ON kms.attribute_rejections;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.attribute_rejections
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

REVOKE ALL ON kms.attribute_catalog_ext, kms.attribute_alias_ext, kms.attribute_rejections FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cabai_app') THEN
    GRANT SELECT, INSERT ON kms.attribute_catalog_ext, kms.attribute_alias_ext, kms.attribute_rejections TO cabai_app;
  END IF;
END $$;
