-- -----------------------------------------------------------------------------
-- by_admission_type.sql — one row per admission type
-- -----------------------------------------------------------------------------
-- Feeds three visuals: admissions-by-type bars, the LOS box plot, and the
-- admission-type comparison table. One query = one scan for all three.
--
-- Concepts: GROUP BY with several conditional aggregates; per-group
-- percentiles. PERCENTILE_CONT interpolates between neighbouring values, so a
-- median is not necessarily one patient's exact stay.
--
-- Discharge outcome counts use admissions WITH a recorded discharge location
-- as their denominator (27% of admissions have none); the missing share is
-- reported separately instead of being hidden.
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    admission_type,
    COUNT(*)                                                          AS admissions,
    COUNT(*) FILTER (WHERE los_status = 'valid')                      AS los_valid_n,

    AVG(los_days) FILTER (WHERE los_status = 'valid')                 AS los_mean_days,
    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                           AS los_p10_days,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                           AS los_p25_days,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                           AS los_median_days,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                           AS los_p75_days,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                           AS los_p90_days,

    COUNT(*) FILTER (WHERE discharge_location <> 'Not recorded')              AS discharge_recorded_n,
    COUNT(*) FILTER (WHERE discharge_location =  'HOME')                      AS discharged_home_n,
    COUNT(*) FILTER (WHERE discharge_location =  'SKILLED NURSING FACILITY')  AS discharged_snf_n,
    COUNT(*) FILTER (WHERE discharge_location =  'DIED')                      AS died_n
FROM filtered
GROUP BY admission_type
ORDER BY admissions DESC;
