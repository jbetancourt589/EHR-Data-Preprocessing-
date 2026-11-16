-- -----------------------------------------------------------------------------
-- filter_options.sql — category labels offered in the filter widgets
-- -----------------------------------------------------------------------------
-- Returns only category NAMES (no counts), unfiltered, so every option the
-- database contains is selectable.
--
-- Concept: GROUPING SETS. One GROUP BY computes several independent groupings
-- in a single pass over the data:
--     GROUPING SETS ((admission_type), (discharge_location), (age_group))
-- is equivalent to a UNION ALL of three GROUP BY queries, but scans the table
-- once. GROUPING(col) returns 0 when `col` is part of the current grouping set,
-- which tells us which dimension each output row belongs to.
--
-- Optimization note: an earlier version used UNION ALL over three SELECTs from
-- admission_base. Referencing a CTE more than once makes PostgreSQL
-- materialize it, and that version took ~3.7 s; this single pass is far faster.
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    CASE
        WHEN GROUPING(admission_type) = 0     THEN 'admission_type'
        WHEN GROUPING(discharge_location) = 0 THEN 'discharge_location'
        ELSE 'age_group'
    END AS dimension,
    CASE
        WHEN GROUPING(admission_type) = 0     THEN admission_type
        WHEN GROUPING(discharge_location) = 0 THEN discharge_location
        ELSE age_group
    END AS label
FROM admission_base
GROUP BY GROUPING SETS ((admission_type), (discharge_location), (age_group))
ORDER BY dimension, label;
