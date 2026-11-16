-- =============================================================================
-- 004_lab_summaries.sql — precomputed aggregates for Lab Results Analytics
-- =============================================================================
-- Why precompute? lab_results has ~27.2M rows. Distinct admissions per test,
-- medians, and histograms each need a full pass (tens of seconds); these views
-- do that work once so dashboard queries read at most ~160k aggregate rows.
--
-- What is stored: only AGGREGATES grouped by test name, unit, admission type,
-- shifted admission year, day of stay, or histogram bin. No hadm_id,
-- subject_id, timestamps, or individual values are stored.
--
-- Definitions used throughout
--   units            recorded unit; NULL/blank -> 'Not recorded'. Every numeric
--                    statistic is grouped by (lab_name, units): values with
--                    different units are never combined.
--   numeric          result_type = 'numeric' AND operator IS NULL
--   censored         numeric with an inequality operator ('<', '>', '<=', '>=').
--                    The stored number is a detection limit, not a measurement,
--                    so censored results are counted but excluded from medians
--                    and histograms.
--   text             non-numeric results; counted, never interpreted.
--   missing          non-numeric results whose text is the literal 'nan' (the source
--                    wrote a missing value as text). Counted as missing_results,
--                    NOT as text results, and never interpreted.
--   lab_name         names that differ only by case/spacing are merged into the
--                    most frequent spelling (analytics.lab_name_map).
--   flag             the source flag, as recorded. Only explicit values are
--                    classified ('abnormal', 'normal'); blank means "not
--                    flagged", which is NOT the same as normal.
--   admit_year       calendar year of the admission. MIMIC shifts dates per
--                    patient for de-identification, so years are not real.
--   day_of_stay      whole days from admission to the result: -1 = drawn
--                    before admission (e.g. emergency department), 30 = 30+.
--
-- Run as postgres on ehr_analytics after 001–003. Reads public tables only.
-- Undo: DROP MATERIALIZED VIEW analytics.lab_* CASCADE (or drop each view).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. lab_name_map + lab_results_clean — source-quirk handling, stored once
--    lab_name_map: one row per recorded name -> canonical (most frequent) spelling.
--    lab_results_clean: zero-storage view over lab_results with the canonical name
--    and an is_missing flag. It exposes no text_value, so no free text can leak.
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_name_map AS
WITH n AS (
    SELECT lab_name, COUNT(*) AS c
    FROM public.lab_results
    WHERE lab_name IS NOT NULL AND btrim(lab_name) <> ''
    GROUP BY lab_name
)
SELECT lab_name AS raw_name,
       FIRST_VALUE(lab_name) OVER (PARTITION BY lower(btrim(lab_name)) ORDER BY c DESC, lab_name) AS lab_name
FROM n;

CREATE UNIQUE INDEX IF NOT EXISTS lab_name_map_raw_idx ON analytics.lab_name_map (raw_name);

CREATE OR REPLACE VIEW analytics.lab_results_clean AS
SELECT
    l.hadm_id,
    l.event_time,
    m.lab_name,
    l.value,
    l.units,
    l.flag,
    l.result_type,
    l.operator,
    (l.result_type IS DISTINCT FROM 'numeric' AND l.text_value ~* '^\s*nan(\s|$)') AS is_missing
FROM public.lab_results AS l
JOIN analytics.lab_name_map AS m ON m.raw_name = l.lab_name;

-- -----------------------------------------------------------------------------
-- 1. lab_cell — test × unit × admission type × admission year
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_cell AS
WITH per_admission_test AS (
    -- One row per (admission, test, unit): makes COUNT(*) below = admissions.
    SELECT
        l.hadm_id,
        l.lab_name,
        COALESCE(NULLIF(btrim(l.units), ''), 'Not recorded') AS units,
        COUNT(*) AS results,
        COUNT(*) FILTER (WHERE l.result_type = 'numeric' AND l.operator IS NULL)     AS numeric_results,
        COUNT(*) FILTER (WHERE l.result_type = 'numeric' AND l.operator IS NOT NULL) AS censored_results,
        COUNT(*) FILTER (WHERE l.result_type IS DISTINCT FROM 'numeric' AND NOT l.is_missing) AS text_results,
        COUNT(*) FILTER (WHERE l.is_missing)                                         AS missing_results,
        COUNT(*) FILTER (WHERE lower(btrim(l.flag)) = 'abnormal')                    AS flag_abnormal,
        COUNT(*) FILTER (WHERE lower(btrim(l.flag)) = 'normal')                      AS flag_normal,
        COUNT(*) FILTER (WHERE NULLIF(btrim(l.flag), '') IS NULL)                    AS flag_missing
    FROM analytics.lab_results_clean AS l
    WHERE l.lab_name IS NOT NULL AND btrim(l.lab_name) <> ''
    GROUP BY l.hadm_id, l.lab_name, 3
)
SELECT
    pat.lab_name                                        AS lab_name,
    pat.units COLLATE "C"                               AS units,
    al.admission_type,
    EXTRACT(YEAR FROM a.admission_time)::int            AS admit_year,
    SUM(pat.results)::bigint                            AS results,
    SUM(pat.numeric_results)::bigint                    AS numeric_results,
    SUM(pat.censored_results)::bigint                   AS censored_results,
    SUM(pat.text_results)::bigint                       AS text_results,
    SUM(pat.missing_results)::bigint                    AS missing_results,
    SUM(pat.flag_abnormal)::bigint                      AS flag_abnormal,
    SUM(pat.flag_normal)::bigint                        AS flag_normal,
    SUM(pat.flag_missing)::bigint                       AS flag_missing,
    COUNT(*)::bigint                                    AS admissions
FROM per_admission_test AS pat
JOIN public.admissions AS a ON a.hadm_id = pat.hadm_id
JOIN analytics.admission_labels AS al ON al.hadm_id = pat.hadm_id
GROUP BY pat.lab_name, pat.units, al.admission_type, 4;

CREATE INDEX IF NOT EXISTS lab_cell_test_idx ON analytics.lab_cell (lab_name, units);

-- -----------------------------------------------------------------------------
-- 2. lab_admission_profile — admissions (with/without labs) per type × year
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_admission_profile AS
WITH per_admission AS (
    SELECT hadm_id, COUNT(*) AS results
    FROM public.lab_results
    GROUP BY hadm_id
)
SELECT
    al.admission_type,
    EXTRACT(YEAR FROM a.admission_time)::int  AS admit_year,
    COUNT(*)::bigint                          AS admissions,
    COUNT(pa.hadm_id)::bigint                 AS admissions_with_labs,
    COALESCE(SUM(pa.results), 0)::bigint      AS results
FROM public.admissions AS a
JOIN analytics.admission_labels AS al ON al.hadm_id = a.hadm_id
LEFT JOIN per_admission AS pa ON pa.hadm_id = a.hadm_id
GROUP BY al.admission_type, 2;

-- -----------------------------------------------------------------------------
-- 3. lab_day_counts — results per test × unit × admission type × day of stay
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_day_counts AS
SELECT
    l.lab_name,
    COALESCE(NULLIF(btrim(l.units), ''), 'Not recorded') COLLATE "C" AS units,
    al.admission_type,
    LEAST(GREATEST(
        FLOOR(EXTRACT(EPOCH FROM (l.event_time - a.admission_time)) / 86400)::int,
        -1), 30)                              AS day_of_stay,
    COUNT(*)::bigint                          AS results
FROM analytics.lab_results_clean AS l
JOIN public.admissions AS a ON a.hadm_id = l.hadm_id
JOIN analytics.admission_labels AS al ON al.hadm_id = l.hadm_id
WHERE a.admission_time IS NOT NULL
  AND l.event_time IS NOT NULL
  AND l.lab_name IS NOT NULL AND btrim(l.lab_name) <> ''
GROUP BY 1, 2, 3, 4;

CREATE INDEX IF NOT EXISTS lab_day_counts_test_idx ON analytics.lab_day_counts (lab_name, units);

-- -----------------------------------------------------------------------------
-- 4. lab_value_trend — quartiles of numeric (uncensored) values over time
--    GROUPING SETS computes both time axes in one pass. Quartiles are not
--    additive, so this view is for all admissions (not split by filters).
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_value_trend AS
WITH v AS (
    SELECT
        l.lab_name,
        COALESCE(NULLIF(btrim(l.units), ''), 'Not recorded') COLLATE "C" AS units,
        l.value,
        LEAST(GREATEST(
            FLOOR(EXTRACT(EPOCH FROM (l.event_time - a.admission_time)) / 86400)::int,
            -1), 30)                               AS day_of_stay,
        EXTRACT(YEAR FROM a.admission_time)::int   AS admit_year
    FROM analytics.lab_results_clean AS l
    JOIN public.admissions AS a ON a.hadm_id = l.hadm_id
    WHERE l.result_type = 'numeric' AND l.operator IS NULL AND l.value IS NOT NULL
      AND a.admission_time IS NOT NULL AND l.event_time IS NOT NULL
),
q AS (
    SELECT
        lab_name,
        units,
        CASE WHEN GROUPING(day_of_stay) = 0 THEN 'day' ELSE 'year' END AS axis,
        CASE WHEN GROUPING(day_of_stay) = 0 THEN day_of_stay ELSE admit_year END AS bucket,
        COUNT(*)::bigint AS n,
        percentile_cont(ARRAY[0.25, 0.5, 0.75]) WITHIN GROUP (ORDER BY value) AS quartiles
    FROM v
    GROUP BY GROUPING SETS ((lab_name, units, day_of_stay), (lab_name, units, admit_year))
)
SELECT
    lab_name, units, axis, bucket, n,
    quartiles[1] AS p25,
    quartiles[2] AS p50,
    quartiles[3] AS p75
FROM q;

CREATE INDEX IF NOT EXISTS lab_value_trend_test_idx ON analytics.lab_value_trend (lab_name, units);

-- -----------------------------------------------------------------------------
-- 5. lab_value_bounds — histogram range per (test, unit): the 1st and 99th
--    percentiles, so a few extreme values cannot stretch the axis (and are
--    never shown individually). Only for (test, unit) with >= 1,000 numeric
--    results, so the bounds are not driven by a handful of patients.
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_value_bounds AS
SELECT
    l.lab_name,
    COALESCE(NULLIF(btrim(l.units), ''), 'Not recorded') COLLATE "C" AS units,
    COUNT(*)::bigint                                         AS n,
    percentile_cont(0.01) WITHIN GROUP (ORDER BY l.value)    AS lo,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY l.value)    AS hi
FROM analytics.lab_results_clean AS l
WHERE l.result_type = 'numeric' AND l.operator IS NULL AND l.value IS NOT NULL
GROUP BY 1, 2
HAVING COUNT(*) >= 1000;

-- -----------------------------------------------------------------------------
-- 6. lab_value_histogram — 30 equal-width bins between the bounds, plus
--    bin 0 (below the 1st percentile) and bin 31 (at/above the 99th).
--    width_bucket(value, lo, hi, 30) returns exactly that numbering.
--    If lo = hi (a constant-valued test) everything goes into bin 1.
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.lab_value_histogram AS
SELECT
    b.lab_name,
    b.units,
    al.admission_type,
    CASE WHEN b.hi > b.lo THEN width_bucket(l.value, b.lo, b.hi, 30) ELSE 1 END AS bin,
    COUNT(*)::bigint AS results
FROM analytics.lab_results_clean AS l
JOIN analytics.lab_value_bounds AS b
  ON b.lab_name = l.lab_name
 AND b.units = COALESCE(NULLIF(btrim(l.units), ''), 'Not recorded')
JOIN analytics.admission_labels AS al ON al.hadm_id = l.hadm_id
WHERE l.result_type = 'numeric' AND l.operator IS NULL AND l.value IS NOT NULL
GROUP BY 1, 2, 3, 4;

CREATE INDEX IF NOT EXISTS lab_value_histogram_test_idx ON analytics.lab_value_histogram (lab_name, units);

-- -----------------------------------------------------------------------------
-- 7. lab_tests — zero-storage view: totals per (test, unit), all admissions
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.lab_tests AS
SELECT
    lab_name,
    units,
    SUM(results)::bigint          AS results,
    SUM(numeric_results)::bigint  AS numeric_results,
    SUM(censored_results)::bigint AS censored_results,
    SUM(text_results)::bigint     AS text_results,
    SUM(missing_results)::bigint  AS missing_results,
    SUM(admissions)::bigint       AS admissions
FROM analytics.lab_cell
GROUP BY lab_name, units;

-- Read-only access for the dashboard role (also covered by default privileges
-- from 003_grants.sql; repeated here so this file is self-contained).
GRANT USAGE  ON SCHEMA analytics TO ehr_dashboard;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO ehr_dashboard;
