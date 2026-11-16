-- -----------------------------------------------------------------------------
-- top_tests.sql — most frequent lab tests in the filtered cohort
-- -----------------------------------------------------------------------------
-- Two-step aggregation:
--   per_unit  one row per (test, unit). Admissions are distinct WITHIN a unit.
--   per_test  one row per test. Result counts add up across units, but
--             admissions do not (one admission can have a test in two units),
--             so MAX(admissions) is used as a conservative lower bound for the
--             privacy minimum: a test is listed only if at least min_admissions
--             admissions had it in one unit.
-- string_agg(... ORDER BY ...) FILTER (...) builds the list of units, leaving
-- out units used fewer than min_admissions times.
-- -----------------------------------------------------------------------------
WITH {{ base }},
per_unit AS (
    SELECT
        lab_name,
        units,
        SUM(results)          AS results,
        SUM(numeric_results)  AS numeric_results,
        SUM(flag_abnormal)    AS flag_abnormal,
        SUM(flag_normal)      AS flag_normal,
        SUM(admissions)       AS admissions
    FROM cells
    GROUP BY lab_name, units
),
per_test AS (
    SELECT
        lab_name,
        SUM(results)                                          AS results,
        SUM(numeric_results)                                  AS numeric_results,
        SUM(flag_abnormal)                                    AS flag_abnormal,
        SUM(flag_normal)                                      AS flag_normal,
        MAX(admissions)                                       AS admissions_lower_bound,
        string_agg(units, ', ' ORDER BY results DESC)
            FILTER (WHERE results >= :min_admissions)         AS units_list
    FROM per_unit
    GROUP BY lab_name
    HAVING MAX(admissions) >= :min_admissions
)
SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY results DESC, lab_name) AS rank
FROM per_test
ORDER BY results DESC, lab_name
LIMIT :top_n;
