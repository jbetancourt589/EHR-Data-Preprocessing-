-- -----------------------------------------------------------------------------
-- los_histogram.sql — length-of-stay distribution in 1-day bins
-- -----------------------------------------------------------------------------
-- The binning happens in PostgreSQL, so only ~31 rows reach Python instead of
-- hundreds of thousands of individual stays.
--
--   FLOOR(los_days)      0 = [0, 1) days, 1 = [1, 2) days, ...
--   LEAST(..., cap)      every stay of `cap` days or longer lands in one
--                        overflow bin ("30+"). This keeps the long right tail
--                        (max > 300 days) from flattening the chart, and avoids
--                        showing extreme stays that could describe one patient.
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    LEAST(FLOOR(los_days)::int, :los_cap_days)  AS bin_start_day,
    COUNT(*)                                    AS admissions
FROM filtered
WHERE los_status = 'valid'
GROUP BY 1
ORDER BY 1;
