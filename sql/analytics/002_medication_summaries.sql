-- =============================================================================
-- 002_medication_summaries.sql — precomputed aggregates for Medication Analytics
-- =============================================================================
-- Why precompute?
--   medications has ~32.8M rows. "Distinct admissions per drug" requires grouping
--   ~10M (admission, drug) pairs, and co-ordering requires a self-join producing
--   tens of millions of pair-rows. Neither fits an interactive 15 s budget.
--   These materialized views do that work ONCE; dashboard queries then read a
--   few thousand to ~150k pre-aggregated rows.
--
-- What is stored: only AGGREGATE counts grouped by drug name, admission type,
-- and anchor-age band. No hadm_id, subject_id, timestamps, or doses are stored.
--
-- Additivity: every admission belongs to exactly one (admission_type, age_group)
-- cell, so "distinct admissions" can be SUMMED across cells correctly.
--
-- Run as postgres on ehr_analytics after 001. Reads public tables; never
-- modifies them. Refresh with sql/analytics/refresh_medication_summaries.sql.
-- Undo: DROP MATERIALIZED VIEW analytics.<name> [CASCADE];
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. med_drug_cell — one row per (drug, admission_type, age_group)
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.med_drug_cell AS
WITH per_admission_drug AS (
    -- Collapse events to one row per admission and drug first; this is what
    -- makes COUNT(*) below equal to "distinct admissions".
    SELECT
        m.hadm_id,
        m.drug,
        COUNT(*) FILTER (WHERE m.event_type = 'MED_ORDER') AS orders,
        COUNT(*) FILTER (WHERE m.event_type = 'MED_STOP')  AS stops
    FROM public.medications AS m
    WHERE m.drug IS NOT NULL AND btrim(m.drug) <> ''
    GROUP BY m.hadm_id, m.drug
)
SELECT
    pad.drug,
    al.admission_type,
    al.age_group,
    EXISTS (SELECT 1 FROM analytics.medication_placeholders AS ph
            WHERE ph.drug = pad.drug)                         AS is_placeholder,
    SUM(pad.orders)::bigint                                   AS orders,
    SUM(pad.stops)::bigint                                    AS stops,
    COUNT(*)::bigint                                          AS admissions_any,
    COUNT(*) FILTER (WHERE pad.orders > 0)::bigint            AS admissions_ordered,
    -- orders-per-admission distribution for this drug
    COUNT(*) FILTER (WHERE pad.orders = 1)::bigint            AS adm_orders_1,
    COUNT(*) FILTER (WHERE pad.orders = 2)::bigint            AS adm_orders_2,
    COUNT(*) FILTER (WHERE pad.orders BETWEEN 3 AND 5)::bigint AS adm_orders_3_5,
    COUNT(*) FILTER (WHERE pad.orders > 5)::bigint            AS adm_orders_6_plus
FROM per_admission_drug AS pad
JOIN analytics.admission_labels AS al ON al.hadm_id = pad.hadm_id
GROUP BY pad.drug, al.admission_type, al.age_group;

CREATE INDEX IF NOT EXISTS med_drug_cell_drug_idx ON analytics.med_drug_cell (drug);

-- -----------------------------------------------------------------------------
-- 2. med_admission_profile — admissions per cell and orders-per-admission band
--    (denominators for utilization rates and the orders-per-admission chart).
--    Placeholders are excluded here so "admissions involving medications" means
--    real medication events.
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.med_admission_profile AS
WITH per_admission AS (
    SELECT
        m.hadm_id,
        COUNT(*) FILTER (WHERE m.event_type = 'MED_ORDER') AS orders,
        COUNT(*) FILTER (WHERE m.event_type = 'MED_STOP')  AS stops,
        COUNT(DISTINCT m.drug) FILTER (WHERE m.event_type = 'MED_ORDER') AS distinct_drugs_ordered
    FROM public.medications AS m
    WHERE m.drug IS NOT NULL AND btrim(m.drug) <> ''
      AND NOT EXISTS (SELECT 1 FROM analytics.medication_placeholders AS ph WHERE ph.drug = m.drug)
    GROUP BY m.hadm_id
)
SELECT
    al.admission_type,
    al.age_group,
    CASE
        WHEN COALESCE(pa.orders, 0) = 0 THEN 0
        WHEN pa.orders < 10  THEN 1
        WHEN pa.orders < 25  THEN 2
        WHEN pa.orders < 50  THEN 3
        WHEN pa.orders < 100 THEN 4
        WHEN pa.orders < 200 THEN 5
        ELSE 6
    END                                                        AS orders_bucket,
    COUNT(*)::bigint                                           AS admissions,
    COUNT(pa.hadm_id)::bigint                                  AS admissions_with_events,
    COUNT(*) FILTER (WHERE pa.orders > 0)::bigint              AS admissions_with_orders,
    COALESCE(SUM(pa.orders), 0)::bigint                        AS orders,
    COALESCE(SUM(pa.stops), 0)::bigint                         AS stops,
    COALESCE(SUM(pa.distinct_drugs_ordered), 0)::bigint        AS distinct_drug_orders
FROM analytics.admission_labels AS al
LEFT JOIN per_admission AS pa ON pa.hadm_id = al.hadm_id
GROUP BY 1, 2, 3;

-- -----------------------------------------------------------------------------
-- 3. med_route_summary — orders by drug and route (formulation context).
--    MED_STOP rows never carry a route, so only orders are used.
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.med_route_summary AS
SELECT
    m.drug,
    COALESCE(NULLIF(btrim(m.route), ''), 'Not recorded') COLLATE "C" AS route,
    COUNT(*)::bigint                 AS orders,
    COUNT(DISTINCT m.hadm_id)::bigint AS admissions
FROM public.medications AS m
WHERE m.event_type = 'MED_ORDER'
  AND m.drug IS NOT NULL AND btrim(m.drug) <> ''
GROUP BY 1, 2;

CREATE INDEX IF NOT EXISTS med_route_summary_drug_idx ON analytics.med_route_summary (drug);

-- -----------------------------------------------------------------------------
-- 4. med_pair_summary — co-ordering among the 100 most widely ordered drugs.
--    A pair counts once per admission in which BOTH drugs were ordered at
--    least once (not necessarily at the same time). Restricting to the top 100
--    keeps the self-join tractable (~4,950 pairs).
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.med_pair_summary AS
WITH top_drugs AS (
    SELECT drug
    FROM analytics.med_drug_cell
    WHERE NOT is_placeholder
    GROUP BY drug
    ORDER BY SUM(admissions_ordered) DESC, drug
    LIMIT 100
),
ordered AS (
    -- one row per (admission, top drug) with at least one order
    SELECT DISTINCT m.hadm_id, m.drug
    FROM public.medications AS m
    JOIN top_drugs AS t ON t.drug = m.drug
    WHERE m.event_type = 'MED_ORDER'
)
SELECT
    a.drug           AS drug_a,
    b.drug           AS drug_b,
    COUNT(*)::bigint AS admissions_both
FROM ordered AS a
JOIN ordered AS b
  ON b.hadm_id = a.hadm_id
 AND a.drug < b.drug          -- each unordered pair once, no self-pairs
GROUP BY a.drug, b.drug;

CREATE INDEX IF NOT EXISTS med_pair_summary_a_idx ON analytics.med_pair_summary (drug_a);
CREATE INDEX IF NOT EXISTS med_pair_summary_b_idx ON analytics.med_pair_summary (drug_b);

-- -----------------------------------------------------------------------------
-- 5. Zero-storage helper views over the summaries
-- -----------------------------------------------------------------------------

-- medication_names — one row per recorded name with an explicit matching key.
-- name_key lower-cases the name, drops a leading "*Nf*" (non-formulary) marker,
-- and collapses punctuation/whitespace. It is used ONLY to show related
-- spellings side by side; counts are never merged across names.
CREATE OR REPLACE VIEW analytics.medication_names AS
SELECT
    c.drug,
    btrim(regexp_replace(
        lower(regexp_replace(c.drug, '^\*nf\*\s*', '', 'i')),
        '[^a-z0-9%.]+', ' ', 'g'))                 AS name_key,
    (c.drug ~* '^\*nf\*')                          AS is_non_formulary,
    bool_or(c.is_placeholder)                      AS is_placeholder,
    SUM(c.orders)::bigint                          AS orders,
    SUM(c.stops)::bigint                           AS stops,
    SUM(c.admissions_any)::bigint                  AS admissions_any,
    SUM(c.admissions_ordered)::bigint              AS admissions_ordered
FROM analytics.med_drug_cell AS c
GROUP BY c.drug;

-- med_pair_metrics — co-ordering strength for each pair.
--   pct_a_with_b  share of admissions ordering A that also ordered B
--   lift          P(A and B) / (P(A) * P(B)); > 1 means the pair co-occurs
--                 more often than independence would predict.
--   Probabilities use admissions with at least one (non-placeholder) order.
CREATE OR REPLACE VIEW analytics.med_pair_metrics AS
WITH drug_admissions AS (
    SELECT drug, SUM(admissions_ordered)::float8 AS n
    FROM analytics.med_drug_cell
    GROUP BY drug
),
total AS (
    SELECT SUM(admissions_with_orders)::float8 AS n
    FROM analytics.med_admission_profile
)
SELECT
    p.drug_a,
    p.drug_b,
    p.admissions_both,
    da.n::bigint                                     AS admissions_a,
    db.n::bigint                                     AS admissions_b,
    p.admissions_both / da.n                         AS pct_a_with_b,
    p.admissions_both / db.n                         AS pct_b_with_a,
    (p.admissions_both / total.n) / ((da.n / total.n) * (db.n / total.n)) AS lift
FROM analytics.med_pair_summary AS p
JOIN drug_admissions AS da ON da.drug = p.drug_a
JOIN drug_admissions AS db ON db.drug = p.drug_b
CROSS JOIN total;
