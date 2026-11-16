-- -----------------------------------------------------------------------------
-- value_classes.sql — how one test/unit's results split by value type
-- -----------------------------------------------------------------------------
-- numeric   plotted in the histogram
-- censored  inequality-qualified (e.g. "<0.01"); the number is a detection
--           limit, not a measurement, so it is counted but not plotted
-- text      non-numeric results; counted, not interpreted
-- missing   source wrote the literal text 'nan' (a missing value); counted apart
-- Uses the same admission-type filter as the histogram so the counts match it.
-- -----------------------------------------------------------------------------
SELECT
    COALESCE(SUM(numeric_results), 0)   AS numeric_results,
    COALESCE(SUM(censored_results), 0)  AS censored_results,
    COALESCE(SUM(text_results), 0)      AS text_results,
    COALESCE(SUM(missing_results), 0)   AS missing_results
FROM analytics.lab_cell
WHERE lab_name = :lab_name
  AND units = :units
  AND {{ type_where }};
