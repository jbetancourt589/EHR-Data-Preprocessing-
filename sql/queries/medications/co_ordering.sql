-- -----------------------------------------------------------------------------
-- co_ordering.sql — conditional co-ordering matrix for the most-ordered drugs
-- -----------------------------------------------------------------------------
-- Output: one row per (row_drug, col_drug) among the top :matrix_size drugs.
--   pct  = of admissions that ordered row_drug, the share that also ordered
--          col_drug. The matrix is NOT symmetric: most heparin admissions may
--          include insulin while few insulin admissions include a rare drug.
--
-- The pair summary stores each pair once (drug_a < drug_b); UNION ALL emits
-- it in both directions so every cell of the square matrix is available.
-- -----------------------------------------------------------------------------
WITH pair_drugs AS (
    SELECT drug_a AS drug FROM analytics.med_pair_summary
    UNION
    SELECT drug_b FROM analytics.med_pair_summary
),
top_drugs AS (
    SELECT n.drug, n.admissions_ordered
    FROM analytics.medication_names AS n
    JOIN pair_drugs AS pd ON pd.drug = n.drug
    ORDER BY n.admissions_ordered DESC, n.drug
    LIMIT :matrix_size
),
both_directions AS (
    SELECT drug_a AS row_drug, drug_b AS col_drug, pct_a_with_b AS pct, admissions_both, lift
    FROM analytics.med_pair_metrics
    UNION ALL
    SELECT drug_b, drug_a, pct_b_with_a, admissions_both, lift
    FROM analytics.med_pair_metrics
)
SELECT
    bd.row_drug,
    bd.col_drug,
    bd.pct,
    bd.admissions_both,
    bd.lift,
    tr.admissions_ordered AS row_admissions
FROM both_directions AS bd
JOIN top_drugs AS tr ON tr.drug = bd.row_drug
JOIN top_drugs AS tc ON tc.drug = bd.col_drug
ORDER BY tr.admissions_ordered DESC, bd.row_drug, bd.col_drug;
