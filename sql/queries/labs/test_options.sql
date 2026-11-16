-- -----------------------------------------------------------------------------
-- test_options.sql — tests and units offered in the selectors (all admissions)
-- -----------------------------------------------------------------------------
-- One row per (test, unit) with enough admissions to be shown. The page
-- groups these into a test list and a unit list per test.
-- -----------------------------------------------------------------------------
SELECT
    lab_name,
    units,
    results,
    numeric_results,
    censored_results,
    text_results,
    missing_results,
    admissions
FROM analytics.lab_tests
WHERE admissions >= :min_admissions
ORDER BY lab_name, results DESC, units;
