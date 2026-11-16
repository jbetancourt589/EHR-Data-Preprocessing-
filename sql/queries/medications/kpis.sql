-- -----------------------------------------------------------------------------
-- kpis.sql — headline medication metrics for the selected cohort (one row)
-- -----------------------------------------------------------------------------
-- Two independent CTEs aggregated separately, then combined with CROSS JOIN
-- (each returns exactly one row, so the cross join is just "put side by side").
--
-- cohort  denominators from the admission profile. Container placeholders are
--         always excluded there, so "admissions involving medications" counts
--         real medication events only.
-- meds    order/stop totals and distinct names from the drug cells; these
--         follow the "exclude placeholders" toggle.
--
-- COUNT(DISTINCT drug): a drug appears in several cells (one per admission
-- type × age band), so DISTINCT is required to count each name once.
-- -----------------------------------------------------------------------------
WITH {{ base }},
cohort AS (
    SELECT
        SUM(admissions)              AS admissions,
        SUM(admissions_with_events)  AS admissions_with_events,
        SUM(admissions_with_orders)  AS admissions_with_orders,
        SUM(distinct_drug_orders)    AS distinct_drug_orders
    FROM profile
),
meds AS (
    SELECT
        COALESCE(SUM(orders), 0)                              AS orders,
        COALESCE(SUM(stops), 0)                               AS stops,
        COUNT(DISTINCT drug)                                  AS unique_medications,
        COUNT(DISTINCT drug) FILTER (WHERE orders > 0)        AS unique_medications_ordered
    FROM cells
)
SELECT *
FROM cohort
CROSS JOIN meds;
