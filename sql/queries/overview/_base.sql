-- -----------------------------------------------------------------------------
-- _base.sql — shared CTEs for every Hospital Overview query
-- -----------------------------------------------------------------------------
-- Every overview query begins with these two CTEs, so all metrics and charts
-- use ONE definition of age group, length-of-stay validity, and filters.
--
-- admission_base  one row per admission (grain = hadm_id), with derived labels
-- filtered        admission_base restricted by the dashboard filters
--
-- Why derive labels here instead of in Python?
--   * Filters can then compare against the same labels the user sees
--     ('Not recorded', '90+ (capped)'), so NULLs need no special-casing.
--   * PostgreSQL inlines non-recursive CTEs (v12+), so the WHERE clause in
--     `filtered` is pushed into the scan; nothing is materialized twice.
-- -----------------------------------------------------------------------------
admission_base AS (
    SELECT
        a.hadm_id,
        a.subject_id,

        -- NULL categories stay visible as an explicit label instead of vanishing
        -- from GROUP BY results or being dropped by filters.
        --
        -- COLLATE "C" (performance): GROUP BY on these labels sorts ~500k rows.
        -- The database's Windows locale collation makes text comparison slow;
        -- "C" compares raw bytes. Equality, and therefore grouping and
        -- filtering, is identical. Only sort order differs, and display order
        -- is applied in Python.
        COALESCE(a.admission_type, 'Not recorded')     COLLATE "C" AS admission_type,
        COALESCE(a.discharge_location, 'Not recorded') COLLATE "C" AS discharge_location,

        -- Anchor age (MIMIC anchor_age), not necessarily age at this admission.
        -- MIMIC caps ages above 89 at 91, so the top band is labelled as capped.
        CASE
            WHEN p.age IS NULL THEN 'Not recorded'
            WHEN p.age < 18    THEN '<18'
            WHEN p.age < 30    THEN '18–29'
            WHEN p.age < 40    THEN '30–39'
            WHEN p.age < 50    THEN '40–49'
            WHEN p.age < 60    THEN '50–59'
            WHEN p.age < 70    THEN '60–69'
            WHEN p.age < 80    THEN '70–79'
            WHEN p.age < 90    THEN '80–89'
            ELSE                    '90+ (capped)'
        END COLLATE "C" AS age_group,

        -- Length-of-stay validity. Records are never modified or deleted; invalid
        -- stays are only excluded from LOS statistics, and each one keeps a reason.
        --   valid              both timestamps present and discharge >= admission
        --                      (zero-length stays are valid)
        --   missing_timestamp  admission or discharge time is NULL
        --   negative_duration  discharge recorded before admission
        CASE
            WHEN a.admission_time IS NULL OR a.discharge_time IS NULL THEN 'missing_timestamp'
            WHEN a.discharge_time < a.admission_time                  THEN 'negative_duration'
            ELSE 'valid'
        END AS los_status,

        -- LOS in fractional days; NULL unless the stay is valid, so aggregates
        -- such as AVG() and PERCENTILE_CONT() can never include an invalid stay.
        -- EXTRACT returns NUMERIC (PostgreSQL 14+); casting to double precision
        -- keeps the arithmetic fast and returns plain floats to Python.
        CASE
            WHEN a.discharge_time >= a.admission_time
            THEN (EXTRACT(EPOCH FROM (a.discharge_time - a.admission_time)) / 86400.0)::double precision
        END AS los_days

    FROM admissions AS a
    -- LEFT JOIN: an admission is never dropped because demographics are missing.
    -- (The foreign key guarantees a patient row exists, so this costs nothing.)
    LEFT JOIN patients AS p
           ON p.subject_id = a.subject_id
),
filtered AS (
    SELECT *
    FROM admission_base
    WHERE {{ where }}
)
