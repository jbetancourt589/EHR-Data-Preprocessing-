-- -----------------------------------------------------------------------------
-- utilization.sql — medication use by anchor-age band AND by admission type
-- -----------------------------------------------------------------------------
-- GROUPING SETS ((age_group), (admission_type)) produces both breakdowns in
-- one pass over the profile; GROUPING(col) = 0 identifies which set a row
-- belongs to.
--
-- Rates are computed in Python from these additive counts:
--   % with orders          admissions_with_orders / admissions
--   orders per admission   orders / admissions_with_orders
--   distinct meds / adm.   distinct_drug_orders / admissions_with_orders
-- (Averaging ratios across cells would weight small cells incorrectly;
--  summing numerators and denominators first is the correct way.)
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    CASE WHEN GROUPING(age_group) = 0 THEN 'age_group' ELSE 'admission_type' END AS dimension,
    CASE WHEN GROUPING(age_group) = 0 THEN age_group   ELSE admission_type   END AS label,
    SUM(admissions)              AS admissions,
    SUM(admissions_with_orders)  AS admissions_with_orders,
    SUM(orders)                  AS orders,
    SUM(stops)                   AS stops,
    SUM(distinct_drug_orders)    AS distinct_drug_orders
FROM profile
GROUP BY GROUPING SETS ((age_group), (admission_type));
