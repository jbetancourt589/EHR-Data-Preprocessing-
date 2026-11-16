-- =============================================================================
-- 002_test_database.sql  —  Option C: empty database for synthetic-data tests
-- =============================================================================
-- Run as:        postgres (superuser), in autocommit mode (CREATE DATABASE cannot
--                run inside a transaction block). Any connected database works
--                except template0 itself, which nobody can connect to anyway.
-- Effect:        Creates a NEW, EMPTY database. It is copied from template0
--                (PostgreSQL's pristine built-in template), not from ehr_analytics,
--                so no MIMIC data is copied into it. ehr_analytics is not opened,
--                read, or modified by these statements.
-- Tables:        None are created here. The pytest fixtures create the schema
--                (from sql/schema.sql) and insert synthetic rows, and they refuse to
--                run unless current_database() = 'ehr_analytics_test'.
-- Undo:          DROP DATABASE ehr_analytics_test;
-- =============================================================================

-- 1. Empty database with the same encoding/locale as ehr_analytics
--    (UTF8, English_United States.1252, libc provider), so text sorting and
--    comparisons in tests behave like production.
CREATE DATABASE ehr_analytics_test
    WITH TEMPLATE   = template0
         ENCODING   = 'UTF8'
         LC_COLLATE = 'English_United States.1252'
         LC_CTYPE   = 'English_United States.1252'
         OWNER      = postgres;

-- 2. By default every role (PUBLIC) may connect to a new database.
--    Remove that so only postgres (superuser) can use the test database;
--    in particular the read-only ehr_dashboard role cannot.
REVOKE CONNECT, TEMPORARY ON DATABASE ehr_analytics_test FROM PUBLIC;
