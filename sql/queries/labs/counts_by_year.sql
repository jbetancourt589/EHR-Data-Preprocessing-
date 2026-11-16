-- -----------------------------------------------------------------------------
-- counts_by_year.sql — results per shifted admission year for one test/unit
-- -----------------------------------------------------------------------------
-- Follows the admission-type and year-range filters. Years are de-identified
-- (shifted per patient), so this shows how results are spread across the
-- shifted timeline, not real calendar trends.
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    admit_year      AS bucket,
    SUM(results)    AS results,
    SUM(admissions) AS admissions
FROM cells
WHERE lab_name = :lab_name
  AND units = :units
  AND admit_year IS NOT NULL
GROUP BY admit_year
ORDER BY admit_year;
