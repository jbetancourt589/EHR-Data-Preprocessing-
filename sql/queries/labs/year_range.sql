-- -----------------------------------------------------------------------------
-- year_range.sql — available (shifted) admission years for the range filter
-- -----------------------------------------------------------------------------
SELECT
    MIN(admit_year) AS first_year,
    MAX(admit_year) AS last_year
FROM analytics.lab_admission_profile
WHERE admit_year IS NOT NULL;
