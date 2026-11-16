-- -----------------------------------------------------------------------------
-- value_trend.sql — median and interquartile range of numeric values over time
-- -----------------------------------------------------------------------------
-- One test AND one unit at a time: values in different units are never
-- combined. Censored (<, >) and text results are excluded. Quartiles are not
-- additive, so they were computed for all admissions when the summary was
-- built and are not affected by the dashboard filters.
-- :axis is 'day' (day of stay) or 'year' (shifted admission year).
-- -----------------------------------------------------------------------------
SELECT
    bucket,
    n,
    p25,
    p50,
    p75
FROM analytics.lab_value_trend
WHERE lab_name = :lab_name
  AND units = :units
  AND axis = :axis
ORDER BY bucket;
