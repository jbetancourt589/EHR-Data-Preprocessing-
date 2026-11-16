-- =============================================================================
-- 001_dashboard_role.sql  —  Option A: read-only role for the Streamlit dashboard
-- =============================================================================
-- Run as:        postgres (superuser), connected to database ehr_analytics
-- Effect:        Creates ONE new role and grants it SELECT on six existing tables.
--                No table, row, index, or column is created, altered, or deleted.
-- Password:      Intentionally NOT set here. Set it afterwards in psql with
--                    \password ehr_dashboard
--                so it never appears in a file, shell history, or server log.
--                Until then the role cannot log in (scram-sha-256 requires one).
-- Undo:          REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ehr_dashboard;
--                REVOKE ALL ON SCHEMA public FROM ehr_dashboard;
--                REVOKE ALL ON DATABASE ehr_analytics FROM ehr_dashboard;
--                DROP ROLE ehr_dashboard;
-- =============================================================================

BEGIN;  -- all-or-nothing: if any statement fails, nothing is kept

-- 1. The login role. Explicitly not a superuser and unable to create databases/roles.
--    NOINHERIT: it does not silently pick up privileges from any role it might later join.
--    CONNECTION LIMIT 10: Streamlit's pool needs only a few connections.
CREATE ROLE ehr_dashboard
    LOGIN
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    NOINHERIT
    CONNECTION LIMIT 10;

-- 2. Session defaults applied whenever ehr_dashboard connects.
--    These are defense-in-depth (a session could override them); the real
--    protection is that the role is only GRANTed SELECT (step 4).
ALTER ROLE ehr_dashboard SET default_transaction_read_only = on;  -- any INSERT/UPDATE/DELETE errors
ALTER ROLE ehr_dashboard SET statement_timeout = '15s';           -- cancels runaway queries
ALTER ROLE ehr_dashboard SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE ehr_dashboard SET jit = off;                           -- JIT compile cost outweighs benefit on sub-second queries

-- 3. Permission to connect to this database and see objects in the public schema.
--    (USAGE lets the role look up names; it does not grant access to any table.)
GRANT CONNECT ON DATABASE ehr_analytics TO ehr_dashboard;
GRANT USAGE   ON SCHEMA public          TO ehr_dashboard;

-- 4. Read-only access to the analytic tables.
--    clinical_notes is deliberately excluded: the dashboard never needs free text.
GRANT SELECT ON TABLE
    public.patients,
    public.admissions,
    public.lab_results,
    public.medications,
    public.transfers,
    public.microbiology
TO ehr_dashboard;

COMMIT;
