-- -----------------------------------------------------------------------------
-- kpis.sql — headline lab metrics and the flag / value-type breakdown (1 row)
-- -----------------------------------------------------------------------------
-- results  counts follow all filters, including the test selection.
-- cohort   admission counts follow admission type and year only: "admissions
--          with lab results" means ANY lab, so it can be summed across cells
--          (each admission belongs to exactly one type × year cell).
--
-- Flag columns count the source flag exactly as recorded:
--   flag_abnormal / flag_normal  explicit values
--   flag_missing                 blank: NOT flagged, which is not "normal"
--   flag_other                   any other recorded value
-- Whether an abnormal RATE can be estimated is decided in Python, from
-- whether explicit normal flags exist at all (see presenters/labs.py).
-- -----------------------------------------------------------------------------
WITH {{ base }},
r AS (
    SELECT
        COALESCE(SUM(results), 0)            AS results,
        COALESCE(SUM(numeric_results), 0)    AS numeric_results,
        COALESCE(SUM(censored_results), 0)   AS censored_results,
        COALESCE(SUM(text_results), 0)       AS text_results,
        COALESCE(SUM(missing_results), 0)    AS missing_results,
        COALESCE(SUM(flag_abnormal), 0)      AS flag_abnormal,
        COALESCE(SUM(flag_normal), 0)        AS flag_normal,
        COALESCE(SUM(flag_missing), 0)       AS flag_missing,
        COALESCE(SUM(results - flag_abnormal - flag_normal - flag_missing), 0) AS flag_other,
        COUNT(DISTINCT lab_name)             AS unique_tests,
        COUNT(DISTINCT (lab_name, units))    AS unique_test_units
    FROM cells
),
c AS (
    SELECT
        COALESCE(SUM(admissions), 0)            AS admissions,
        COALESCE(SUM(admissions_with_labs), 0)  AS admissions_with_labs
    FROM cohort
)
SELECT *
FROM r
CROSS JOIN c;
