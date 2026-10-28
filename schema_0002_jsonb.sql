-- CABAI-KMS migration 0002. Additive JSONB document storage.
-- Applied transactionally by migrate.py.

CREATE TABLE IF NOT EXISTS kms.knowledge_documents (
  id text PRIMARY KEY,
  variety_id text NOT NULL,
  habitat_id text NOT NULL,
  document jsonb NOT NULL CHECK (jsonb_typeof(document) = 'object'),
  version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_knowledge_documents_variety_habitat UNIQUE (variety_id, habitat_id)
);

CREATE INDEX IF NOT EXISTS knowledge_documents_variety_habitat_idx
  ON kms.knowledge_documents (variety_id, habitat_id);

CREATE INDEX IF NOT EXISTS knowledge_documents_variety_lookup
  ON kms.knowledge_documents ((document->'variety'->>'id'));

CREATE INDEX IF NOT EXISTS knowledge_documents_habitat_lookup
  ON kms.knowledge_documents ((document->'habitat'->>'id'));

CREATE INDEX IF NOT EXISTS knowledge_documents_gin
  ON kms.knowledge_documents USING gin (document);

-- Update audit trigger to redact document payload from old_data and new_data
CREATE OR REPLACE FUNCTION kms.audit_mutation() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
 SET search_path = pg_catalog, kms AS $$
DECLARE a text; before_row jsonb; after_row jsonb;
BEGIN
 a := nullif(current_setting('kms.actor',true),'');
 IF a IS NULL THEN RAISE EXCEPTION 'Authenticated kms.actor is required'; END IF;
 IF TG_OP <> 'INSERT' THEN before_row := to_jsonb(OLD); END IF;
 IF TG_OP <> 'DELETE' THEN after_row := to_jsonb(NEW); END IF;
 IF TG_TABLE_NAME='acquisition_runs' THEN
  before_row := before_row - 'draft_payload' - 'base_versions';
  after_row := after_row - 'draft_payload' - 'base_versions';
 END IF;
 IF TG_TABLE_NAME='knowledge_documents' THEN
  before_row := before_row - 'document';
  after_row := after_row - 'document';
 END IF;
 INSERT INTO kms.audit_trace(run_id,actor,event_type,entity_type,old_data,new_data)
 VALUES(nullif(current_setting('kms.run_id',true),''),a,TG_OP,TG_TABLE_NAME,before_row,after_row);
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trace_change ON kms.knowledge_documents;
CREATE TRIGGER trace_change AFTER INSERT OR UPDATE OR DELETE ON kms.knowledge_documents
  FOR EACH ROW EXECUTE FUNCTION kms.audit_mutation();

DROP TRIGGER IF EXISTS reject_truncate ON kms.knowledge_documents;
CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.knowledge_documents
  FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();

REVOKE ALL ON kms.knowledge_documents FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cabai_app') THEN
    GRANT SELECT, INSERT, UPDATE ON kms.knowledge_documents TO cabai_app;
  END IF;
END $$;
