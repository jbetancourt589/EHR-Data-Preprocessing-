-- -----------------------------------------------------------------------------
-- drug_detail.sql — aggregate statistics for ONE selected medication
-- -----------------------------------------------------------------------------
-- The drug name arrives as a bind parameter (:drug); it is never inserted into
-- the SQL text.
--
-- GROUPING SETS ((), (age_group), (admission_type)) returns, in one pass:
--   ()                the cohort total for this drug
--   (age_group)       one row per anchor-age band
--   (admission_type)  one row per admission type
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    CASE
        WHEN GROUPING(age_group) = 0      THEN 'age_group'
        WHEN GROUPING(admission_type) = 0 THEN 'admission_type'
        ELSE 'total'
    END AS dimension,
    CASE
        WHEN GROUPING(age_group) = 0      THEN age_group
        WHEN GROUPING(admission_type) = 0 THEN admission_type
        ELSE 'All'
    END AS label,
    SUM(orders)              AS orders,
    SUM(stops)               AS stops,
    SUM(admissions_any)      AS admissions_any,
    SUM(admissions_ordered)  AS admissions_ordered,
    SUM(adm_orders_1)        AS adm_orders_1,
    SUM(adm_orders_2)        AS adm_orders_2,
    SUM(adm_orders_3_5)      AS adm_orders_3_5,
    SUM(adm_orders_6_plus)   AS adm_orders_6_plus
FROM cells
WHERE drug = :drug
GROUP BY GROUPING SETS ((), (age_group), (admission_type));
