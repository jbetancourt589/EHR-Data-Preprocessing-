-- -----------------------------------------------------------------------------
-- kpis.sql — headline metrics for the selected cohort (one row)
-- -----------------------------------------------------------------------------
-- Concepts: conditional aggregation with FILTER, COUNT(DISTINCT), and the
-- ordered-set aggregate PERCENTILE_CONT ... WITHIN GROUP.
--
-- FILTER (WHERE ...) restricts the rows a single aggregate sees. It lets one
-- scan produce population counts AND valid-LOS statistics side by side, which
-- is clearer than SUM(CASE WHEN ... THEN 1 ELSE 0 END).
--
-- Denominators
--   admissions       every admission matching the filters
--   los_valid_n      admissions used for LOS statistics (los_status = 'valid')
--   mean/median/IQR  computed over los_valid_n only
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    COUNT(*)                                                  AS admissions,
    COUNT(DISTINCT subject_id)                                AS patients,

    COUNT(*) FILTER (WHERE los_status = 'valid')              AS los_valid_n,
    COUNT(*) FILTER (WHERE los_status = 'missing_timestamp')  AS los_missing_n,
    COUNT(*) FILTER (WHERE los_status = 'negative_duration')  AS los_negative_n,

    AVG(los_days) FILTER (WHERE los_status = 'valid')         AS los_mean_days,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                   AS los_p25_days,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                   AS los_median_days,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                   AS los_p75_days
FROM filtered;
