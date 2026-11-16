-- -----------------------------------------------------------------------------
-- top_medications.sql — top N medications by orders AND by distinct admissions
-- -----------------------------------------------------------------------------
-- Concepts: GROUP BY + HAVING, and window functions for ranking.
--
-- per_drug  re-aggregates the cells to one row per drug name. Distinct
--           admissions can be SUMMED across cells because every admission
--           belongs to exactly one (admission type, age band) cell.
-- HAVING    filters GROUPS (after aggregation), unlike WHERE which filters
--           rows. Names recorded in fewer than min_admissions (11) admissions
--           are never listed: a rare drug name is itself a small cell.
-- ROW_NUMBER() OVER (ORDER BY ...)
--           ranks without collapsing rows. Two independent rankings are
--           computed in one pass; the drug name breaks ties so the top N is
--           deterministic. (RANK() would let ties push the list past N.)
--
-- Each drug name is kept exactly as recorded: formulations and spellings are
-- NOT merged (e.g. "0.9% Sodium Chloride" and "Sodium Chloride 0.9%  Flush").
-- -----------------------------------------------------------------------------
WITH {{ base }},
per_drug AS (
    SELECT
        drug,
        bool_or(is_placeholder)   AS is_placeholder,
        SUM(orders)               AS orders,
        SUM(stops)                AS stops,
        SUM(admissions_any)       AS admissions_any,
        SUM(admissions_ordered)   AS admissions_ordered
    FROM cells
    GROUP BY drug
    HAVING SUM(admissions_any) >= :min_admissions
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (ORDER BY orders DESC, drug)             AS rank_by_orders,
        ROW_NUMBER() OVER (ORDER BY admissions_ordered DESC, drug) AS rank_by_admissions
    FROM per_drug
)
SELECT *
FROM ranked
WHERE rank_by_orders <= :top_n
   OR rank_by_admissions <= :top_n
ORDER BY rank_by_orders;
