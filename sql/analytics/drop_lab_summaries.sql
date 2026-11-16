-- Drops the derived lab summaries so 004_lab_summaries.sql can recreate them.
-- Derived objects only: public tables are never touched. Run in the same
-- transaction as 004 so a failed rebuild leaves the old summaries in place.
DROP VIEW IF EXISTS analytics.lab_tests;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_value_histogram;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_value_bounds;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_value_trend;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_day_counts;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_admission_profile;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_cell;
DROP VIEW IF EXISTS analytics.lab_results_clean;
DROP MATERIALIZED VIEW IF EXISTS analytics.lab_name_map;
