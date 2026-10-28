-- CABAI-KMS migration 0004. Additive image candidates queue and discarded images index.
-- Applied transactionally by migrate.py.

CREATE TABLE IF NOT EXISTS kms.image_candidates (
  candidate_id text PRIMARY KEY,
  asset_id text UNIQUE NOT NULL REFERENCES kms.media_assets(id),
  run_id text NOT NULL,
  source_filename text NOT NULL,
  original_sha256 text NOT NULL,
  organ_part text NOT NULL,
  suggested_name text,
  visual_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(5,4) NOT NULL,
  status text NOT NULL DEFAULT 'CANDIDATE',
  resolution jsonb,
  decided_by text,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT image_candidates_status_check CHECK (status IN ('CANDIDATE', 'PROMOTED', 'MERGED', 'DISCARDED'))
);

CREATE INDEX IF NOT EXISTS image_candidates_status_idx
  ON kms.image_candidates (status);

CREATE INDEX IF NOT EXISTS image_candidates_run_idx
  ON kms.image_candidates (run_id);

CREATE TABLE IF NOT EXISTS kms.discarded_images (
  original_sha256 text PRIMARY KEY,
  reason text NOT NULL,
  decided_by text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  asset_id text,
  source_filename text
);

CREATE INDEX IF NOT EXISTS discarded_images_decided_at_idx
  ON kms.discarded_images (decided_at);

REVOKE ALL ON kms.image_candidates FROM PUBLIC;
REVOKE ALL ON kms.discarded_images FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'cabai_app') THEN
    GRANT SELECT, INSERT, UPDATE ON kms.image_candidates TO cabai_app;
    GRANT SELECT, INSERT ON kms.discarded_images TO cabai_app;
  END IF;
END $$;
