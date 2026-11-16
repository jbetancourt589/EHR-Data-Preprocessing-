-- -----------------------------------------------------------------------------
-- age_groups.sql — admissions and patients per anchor-age band
-- -----------------------------------------------------------------------------
-- COUNT(*) counts admissions; COUNT(DISTINCT subject_id) counts patients.
-- They differ because one patient can be admitted many times. Anchor age is
-- fixed per patient, so each patient falls in exactly one band.
-- Band order is applied in Python from a fixed list (alphabetical order would
-- put '<18' and 'Not recorded' in the wrong places).
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    age_group,
    COUNT(*)                                                 AS admissions,
    COUNT(DISTINCT subject_id)                               AS patients,
    COUNT(*) FILTER (WHERE los_status = 'valid')             AS los_valid_n,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY los_days)
        FILTER (WHERE los_status = 'valid')                  AS los_median_days
FROM filtered
GROUP BY age_group;
