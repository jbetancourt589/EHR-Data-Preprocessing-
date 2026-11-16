-- -----------------------------------------------------------------------------
-- _base.sql — shared CTEs for every Medication Analytics query
-- -----------------------------------------------------------------------------
-- These read the precomputed summaries in the analytics schema
-- (sql/analytics/002_medication_summaries.sql), never the 32.8M-row
-- medications table, so every dashboard query touches at most ~150k rows.
--
-- cells    drug × admission type × age band, restricted by the filters and,
--          optionally, with container placeholders (Bag, Vial, ...) removed
-- profile  admissions per cell and orders-per-admission band (denominators)
--
-- The same {{ where }} expression applies to both because both carry the
-- admission_type and age_group columns.
-- -----------------------------------------------------------------------------
cells AS (
    SELECT *
    FROM analytics.med_drug_cell
    WHERE {{ where }}
      AND (NOT :exclude_placeholders OR NOT is_placeholder)
),
profile AS (
    SELECT *
    FROM analytics.med_admission_profile
    WHERE {{ where }}
)
