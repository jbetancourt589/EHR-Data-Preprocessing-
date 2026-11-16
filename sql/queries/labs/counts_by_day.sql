-- -----------------------------------------------------------------------------
-- counts_by_day.sql — results per day of hospital stay for one test/unit
-- -----------------------------------------------------------------------------
-- Day of stay is unaffected by MIMIC's date shifting (both timestamps of an
-- admission are shifted by the same amount), so this is the clinically
-- meaningful time axis. -1 = drawn before admission; 30 = day 30 or later.
-- Follows the admission-type filter. The day-of-stay summary has no year
-- column, so the year-range filter does not apply here.
-- -----------------------------------------------------------------------------
SELECT
    day_of_stay   AS bucket,
    SUM(results)  AS results
FROM analytics.lab_day_counts
WHERE lab_name = :lab_name
  AND units = :units
  AND {{ type_where }}
GROUP BY day_of_stay
ORDER BY day_of_stay;
