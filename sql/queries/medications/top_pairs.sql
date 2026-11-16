-- -----------------------------------------------------------------------------
-- top_pairs.sql — the most frequently co-ordered medication pairs
-- -----------------------------------------------------------------------------
-- Ranked by the number of admissions in which both drugs were ordered.
-- Lift is shown alongside: very common drugs (e.g. IV fluids) co-occur with
-- almost everything, so a high count with lift ~1 is expected, while lift
-- well above 1 points to drugs that are genuinely ordered together.
-- -----------------------------------------------------------------------------
SELECT
    drug_a,
    drug_b,
    admissions_both,
    admissions_a,
    admissions_b,
    pct_a_with_b,
    pct_b_with_a,
    lift
FROM analytics.med_pair_metrics
WHERE admissions_both >= :min_admissions
ORDER BY admissions_both DESC, drug_a, drug_b
LIMIT :pair_limit;
