-- -----------------------------------------------------------------------------
-- discharge_destinations.sql — admissions per discharge destination
-- -----------------------------------------------------------------------------
-- 'Not recorded' is kept as its own row: a missing discharge location is
-- common in MIMIC (especially for observation stays), and dropping it would
-- inflate every other destination's share.
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    discharge_location,
    COUNT(*)                                                 AS admissions,
    COUNT(*) FILTER (WHERE los_status = 'valid')             AS los_valid_n,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                  AS los_median_days
FROM filtered
GROUP BY discharge_location
ORDER BY admissions DESC;
