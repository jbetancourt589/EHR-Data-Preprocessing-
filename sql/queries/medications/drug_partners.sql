-- -----------------------------------------------------------------------------
-- drug_partners.sql — medications most often ordered in the same admission
-- -----------------------------------------------------------------------------
-- Pairs are stored once with drug_a < drug_b. The selected drug can be on
-- either side, so CASE expressions "rotate" each row so the selected drug is
-- always the reference and `partner` is the other drug.
--
--   pct_with_partner  of admissions that ordered the selected drug, the share
--                     that also ordered the partner (conditional probability)
--   lift              > 1: ordered together more often than if independent
--
-- Covers the 100 most widely ordered drugs, across all admissions.
-- -----------------------------------------------------------------------------
SELECT
    CASE WHEN drug_a = :drug THEN drug_b ELSE drug_a END                AS partner,
    admissions_both,
    CASE WHEN drug_a = :drug THEN pct_a_with_b ELSE pct_b_with_a END    AS pct_with_partner,
    CASE WHEN drug_a = :drug THEN admissions_b ELSE admissions_a END    AS partner_admissions,
    lift
FROM analytics.med_pair_metrics
WHERE (drug_a = :drug OR drug_b = :drug)
  AND admissions_both >= :min_admissions
ORDER BY admissions_both DESC, partner
LIMIT :partner_limit;
