-- -----------------------------------------------------------------------------
-- _base.sql — shared CTEs for Lab Results Analytics queries
-- -----------------------------------------------------------------------------
-- Reads the precomputed summaries (sql/analytics/004_lab_summaries.sql), never
-- the 27.2M-row lab_results table.
--
-- cells   test × unit × admission type × admission year, restricted by
--         admission type, shifted admission-year range, and selected tests
-- cohort  admissions per admission type × year (no test column), restricted
--         by admission type and year range only
-- -----------------------------------------------------------------------------
cells AS (
    SELECT *
    FROM analytics.lab_cell
    WHERE {{ where }}
),
cohort AS (
    SELECT *
    FROM analytics.lab_admission_profile
    WHERE {{ cohort_where }}
)
