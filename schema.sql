-- CABAI-KMS migration 0001. PostgreSQL >= 15. Applied transactionally by migrate.py.
-- The runtime role is NOT the owner of these objects.
CREATE SCHEMA IF NOT EXISTS kms;

CREATE TABLE kms.varieties (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 canonical_name text NOT NULL UNIQUE CHECK (length(btrim(canonical_name)) BETWEEN 1 AND 256),
 origin_region text,
 acquisition_date date,
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE kms.variety_aliases (
 variety_id uuid NOT NULL REFERENCES kms.varieties(id),
 alias text NOT NULL CHECK (length(btrim(alias)) > 0),
 PRIMARY KEY (variety_id, alias)
);
CREATE INDEX variety_alias_lookup ON kms.variety_aliases (lower(alias));
CREATE VIEW kms.varieties_with_aliases AS
 SELECT v.*, COALESCE((SELECT jsonb_agg(a.alias ORDER BY a.alias)
 FROM kms.variety_aliases a WHERE a.variety_id=v.id), '[]'::jsonb) AS local_aliases
 FROM kms.varieties v;

CREATE TABLE kms.characteristics (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 canonical_key text NOT NULL UNIQUE CHECK (canonical_key ~ '^[a-z][a-z0-9_]{0,159}$'),
 label_id text NOT NULL CHECK (length(btrim(label_id)) > 0),
 organ_domain text CHECK (organ_domain IN ('habitus','daun','batang','bunga','buah','biji')),
 source_domain text NOT NULL,
 data_type text NOT NULL CHECK (data_type IN ('text','number','boolean','image','location')),
 standard_unit text,
 description text NOT NULL DEFAULT ''
);
CREATE TABLE kms.catalog_versions (
 schema_version text NOT NULL,
 template_hash text NOT NULL CHECK (template_hash ~ '^[a-f0-9]{64}$'),
 catalog_hash text NOT NULL CHECK (catalog_hash ~ '^[a-f0-9]{64}$'),
 definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'array'),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(schema_version, template_hash)
);
CREATE TABLE kms.source_artifacts (
 sha256 text PRIMARY KEY CHECK (sha256 ~ '^[a-f0-9]{64}$'),
 storage_uri text NOT NULL,
 file_size bigint NOT NULL CHECK (file_size > 0),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE kms.acquisition_runs (
 run_id text PRIMARY KEY CHECK (run_id ~ '^[A-Za-z0-9_-]{1,160}$'),
 source_filename text NOT NULL,
 file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[a-f0-9]{64}$'),
 source_uri text,
 schema_version text NOT NULL,
 template_hash text NOT NULL CHECK (template_hash ~ '^[a-f0-9]{64}$'),
 config_fingerprint text NOT NULL,
 total_attributes integer NOT NULL CHECK (total_attributes >= 0),
 auto_accepted_count integer NOT NULL CHECK (auto_accepted_count >= 0),
 reviewed_count integer NOT NULL CHECK (reviewed_count >= 0),
 execution_duration_ms bigint CHECK (execution_duration_ms >= 0),
 executed_at timestamptz,
 ingested_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'STAGED' CHECK (status IN ('STAGED','COMMITTED')),
 revision integer NOT NULL CHECK (revision >= 1),
 payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
 draft_payload jsonb NOT NULL CHECK (jsonb_typeof(draft_payload) = 'object'),
 base_versions jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(base_versions) = 'object'),
 receipt jsonb,
 committed_at timestamptz,
 CHECK (auto_accepted_count + reviewed_count <= total_attributes),
 CHECK ((status='COMMITTED') = (committed_at IS NOT NULL AND receipt IS NOT NULL))
);
CREATE INDEX acquisition_file_hash ON kms.acquisition_runs(file_sha256);
CREATE INDEX acquisition_recent ON kms.acquisition_runs(ingested_at DESC);
CREATE TABLE kms.draft_revisions (
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 revision integer NOT NULL,
 payload_sha256 text NOT NULL,
 payload jsonb NOT NULL,
 base_versions jsonb NOT NULL,
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(run_id, revision)
);
CREATE TABLE kms.value_observations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 variety_id uuid NOT NULL REFERENCES kms.varieties(id),
 characteristic_id uuid NOT NULL REFERENCES kms.characteristics(id),
 observation_sha256 text NOT NULL CHECK (observation_sha256 ~ '^[a-f0-9]{64}$'),
 evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id, variety_id, characteristic_id, observation_sha256)
);
CREATE INDEX observation_history ON kms.value_observations(variety_id, characteristic_id, created_at DESC);
CREATE TABLE kms.variety_character_values (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 variety_id uuid NOT NULL REFERENCES kms.varieties(id),
 characteristic_id uuid NOT NULL REFERENCES kms.characteristics(id),
 normalized_value jsonb NOT NULL CHECK (normalized_value <> 'null'::jsonb),
 raw_source_value jsonb NOT NULL,
 value_type text NOT NULL CHECK (value_type IN ('text','number','range','boolean','list')),
 is_multi_value boolean NOT NULL,
 confidence_score double precision NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
 status text NOT NULL CHECK (status IN ('AUTO_ACCEPT','HUMAN_REVIEW')),
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 version integer NOT NULL DEFAULT 1 CHECK(version >= 1),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(variety_id, characteristic_id),
 CHECK (is_multi_value = (value_type='list')),
 CHECK ((value_type='text' AND jsonb_typeof(normalized_value)='string') OR
        (value_type='number' AND jsonb_typeof(normalized_value)='number') OR
        (value_type='boolean' AND jsonb_typeof(normalized_value)='boolean') OR
        (value_type='list' AND jsonb_typeof(normalized_value)='array') OR
        (value_type='range' AND jsonb_typeof(normalized_value)='object'))
);
CREATE INDEX characteristic_value_lookup ON kms.variety_character_values(characteristic_id, status);
-- Optional targeted expression indexes belong in measured follow-up migrations.
CREATE TABLE kms.review_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 item_id text NOT NULL,
 decision text NOT NULL CHECK (decision IN ('approved','revised','no_match')),
 characteristic_id uuid REFERENCES kms.characteristics(id),
 actor text NOT NULL,
 evidence jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id, item_id),
 CHECK ((decision='no_match') = (characteristic_id IS NULL))
);
CREATE TABLE kms.gold_examples (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 item_id text NOT NULL,
 source_scope text NOT NULL,
 schema_version text NOT NULL,
 template_hash text NOT NULL,
 source_label_normalized text NOT NULL,
 context_hash text NOT NULL,
 characteristic_id uuid REFERENCES kms.characteristics(id),
 decision text NOT NULL CHECK (decision IN ('approved','revised','no_match')),
 example jsonb NOT NULL,
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,item_id),
 CHECK ((decision='no_match') = (characteristic_id IS NULL))
);
CREATE INDEX gold_scope_lookup ON kms.gold_examples(source_scope,schema_version,template_hash,source_label_normalized,context_hash);
CREATE TABLE kms.canonical_aliases (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_scope text NOT NULL,
 schema_version text NOT NULL,
 template_hash text NOT NULL,
 source_label_normalized text NOT NULL,
 context_hash text NOT NULL,
 characteristic_id uuid NOT NULL REFERENCES kms.characteristics(id),
 gold_id uuid NOT NULL REFERENCES kms.gold_examples(id),
 evaluation_reference text NOT NULL,
 reason text NOT NULL,
 promoted_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 revoked_at timestamptz,
 revoked_by text,
 revoke_reason text
);
CREATE UNIQUE INDEX active_alias_unique ON kms.canonical_aliases
(source_scope, schema_version, template_hash, source_label_normalized, context_hash) WHERE revoked_at IS NULL;
CREATE TABLE kms.media_assets (
 id text PRIMARY KEY CHECK (id ~ '^[a-f0-9]{64}$'),
 original_sha256 text NOT NULL CHECK (original_sha256 ~ '^[a-f0-9]{64}$'),
 transform_profile text NOT NULL,
 original_uri text NOT NULL,
 storage_uri text NOT NULL,
 thumbnail_uri text NOT NULL,
 image_sha256 text NOT NULL CHECK (image_sha256 ~ '^[a-f0-9]{64}$'),
 thumbnail_sha256 text NOT NULL CHECK (thumbnail_sha256 ~ '^[a-f0-9]{64}$'),
 mime_type text NOT NULL CHECK (mime_type='image/webp'),
 file_size bigint NOT NULL CHECK (file_size>0),
 original_size bigint NOT NULL CHECK (original_size>0),
 thumbnail_size bigint NOT NULL CHECK (thumbnail_size>0),
 width integer NOT NULL CHECK(width>0),
 height integer NOT NULL CHECK(height>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(original_sha256,transform_profile)
);
CREATE TABLE kms.plant_images (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 variety_id uuid NOT NULL REFERENCES kms.varieties(id),
 organ_part text NOT NULL CHECK(organ_part IN ('habitus','daun','batang','bunga','buah','biji')),
 asset_id text NOT NULL REFERENCES kms.media_assets(id),
 vision_confidence double precision NOT NULL CHECK(vision_confidence BETWEEN 0 AND 1),
 vision_evidence jsonb NOT NULL CHECK(jsonb_typeof(vision_evidence)='object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,variety_id,organ_part,asset_id)
);
CREATE INDEX plant_image_lookup ON kms.plant_images(variety_id,organ_part);
CREATE VIEW kms.plant_images_with_media AS SELECT i.*, m.storage_uri,m.thumbnail_uri,m.mime_type,m.file_size,
 m.original_sha256,m.transform_profile FROM kms.plant_images i JOIN kms.media_assets m ON m.id=i.asset_id;

CREATE TABLE kms.audit_trace (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id text,
 actor text NOT NULL,
 event_type text NOT NULL,
 entity_type text NOT NULL,
 old_data jsonb,
 new_data jsonb,
 transaction_id bigint NOT NULL DEFAULT txid_current(),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_run_order ON kms.audit_trace(run_id,id);
CREATE TABLE kms.outbox_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 run_id text NOT NULL REFERENCES kms.acquisition_runs(run_id),
 event_type text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 available_at timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0,
 lease_token uuid,
 leased_until timestamptz,
 delivered_at timestamptz,
 dead_letter_at timestamptz,
 last_error_code text,
 UNIQUE(run_id,event_type)
);
CREATE INDEX outbox_ready ON kms.outbox_events(available_at)
 WHERE delivered_at IS NULL AND dead_letter_at IS NULL;

CREATE FUNCTION kms.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Append-only table %.%: % is prohibited', TG_TABLE_SCHEMA,TG_TABLE_NAME,TG_OP; END $$;
CREATE FUNCTION kms.audit_mutation() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
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
 INSERT INTO kms.audit_trace(run_id,actor,event_type,entity_type,old_data,new_data)
 VALUES(nullif(current_setting('kms.run_id',true),''),a,TG_OP,TG_TABLE_NAME,before_row,after_row);
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION kms.lock_committed_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status='COMMITTED' THEN RAISE EXCEPTION 'Committed run is immutable; create an amendment run'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_committed_run BEFORE UPDATE ON kms.acquisition_runs FOR EACH ROW EXECUTE FUNCTION kms.lock_committed_run();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['audit_trace','draft_revisions','value_observations','review_decisions','gold_examples','catalog_versions','source_artifacts','media_assets','plant_images'] LOOP
  EXECUTE format('CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.%I FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation()',t);
  EXECUTE format('CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.%I FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['varieties','variety_aliases','characteristics','acquisition_runs','variety_character_values','review_decisions','canonical_aliases','media_assets','plant_images','source_artifacts'] LOOP
  EXECUTE format('CREATE TRIGGER trace_change AFTER INSERT OR UPDATE OR DELETE ON kms.%I FOR EACH ROW EXECUTE FUNCTION kms.audit_mutation()',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA kms FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA kms FROM PUBLIC;
REVOKE ALL ON SCHEMA kms FROM PUBLIC;
