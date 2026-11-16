-- =============================================================================
-- 001_schema_and_views.sql — analytics schema and two zero-storage views
-- =============================================================================
-- Run as postgres on ehr_analytics. Creates NO table data and does not touch
-- the public tables: plain views store only their definition.
-- Undo: DROP SCHEMA analytics CASCADE;
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS analytics;

-- -----------------------------------------------------------------------------
-- admission_labels — one row per admission with the dashboard's derived labels.
-- Same definitions as sql/queries/overview/_base.sql (tests check they agree).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.admission_labels AS
SELECT
    a.hadm_id,
    a.subject_id,
    COALESCE(a.admission_type, 'Not recorded') COLLATE "C" AS admission_type,
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
    END COLLATE "C" AS age_group
FROM public.admissions AS a
LEFT JOIN public.patients AS p ON p.subject_id = a.subject_id;

-- -----------------------------------------------------------------------------
-- medication_placeholders — explicit list of non-drug order-entry names.
-- These are containers or order-entry prompts, not medications. They are
-- FLAGGED (never deleted); the dashboard lets the user include or exclude them.
-- Add a name here only after checking it is not a medication.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.medication_placeholders AS
SELECT drug, reason
FROM (VALUES
    ('Bag',                                          'container'),
    ('Vial',                                         'container'),
    ('Syringe',                                      'container'),
    ('Click Change <--- To Choose A Base Solution',  'order-entry prompt'),
    ('Click Change To Choose A Base Solution',       'order-entry prompt')
) AS t (drug, reason);
