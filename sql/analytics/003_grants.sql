-- =============================================================================
-- 003_grants.sql — read-only access for the dashboard role to analytics objects
-- =============================================================================
-- The dashboard role gets SELECT only. It cannot refresh, alter, or drop these
-- objects (only the owner, postgres, can).
GRANT USAGE  ON SCHEMA analytics TO ehr_dashboard;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO ehr_dashboard;  -- includes views and materialized views
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO ehr_dashboard;
