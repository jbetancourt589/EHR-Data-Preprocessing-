-- -----------------------------------------------------------------------------
-- histogram.sql — distribution of numeric values for one test and unit
-- -----------------------------------------------------------------------------
-- Bins were fixed per (test, unit) when the summary was built: 30 equal-width
-- bins between the 1st and 99th percentiles, plus bin 0 (below) and bin 31
-- (at or above). Because every admission type uses the same bin edges, bin
-- counts can be summed across the selected admission types.
-- Follows the admission-type filter only (the histogram has no year column).
-- -----------------------------------------------------------------------------
SELECT
    h.bin,
    SUM(h.results) AS results,
    b.lo,
    b.hi
FROM analytics.lab_value_histogram AS h
JOIN analytics.lab_value_bounds AS b
  ON b.lab_name = h.lab_name
 AND b.units = h.units
WHERE h.lab_name = :lab_name
  AND h.units = :units
  AND {{ type_where }}
GROUP BY h.bin, b.lo, b.hi
ORDER BY h.bin;
