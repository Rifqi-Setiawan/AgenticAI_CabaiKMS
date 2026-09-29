-- Run as cabai_migrator (schema owner), after migration; never as the runtime role.
REVOKE ALL ON SCHEMA kms FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA kms FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA kms FROM PUBLIC;
GRANT USAGE ON SCHEMA kms TO cabai_app;
GRANT SELECT ON ALL TABLES IN SCHEMA kms TO cabai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA kms TO cabai_app;
GRANT INSERT, UPDATE ON kms.varieties,kms.characteristics,kms.acquisition_runs,
 kms.variety_character_values,kms.canonical_aliases,kms.outbox_events TO cabai_app;
GRANT INSERT ON kms.variety_aliases,kms.catalog_versions,kms.source_artifacts,
 kms.draft_revisions,kms.value_observations,kms.review_decisions,kms.gold_examples,
 kms.media_assets,kms.plant_images,kms.audit_trace TO cabai_app;
-- Intentionally absent: DELETE, TRUNCATE, CREATE, REFERENCES, schema ownership,
-- writes to schema_migrations, or UPDATE on evidence/audit tables.
