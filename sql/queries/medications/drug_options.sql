-- -----------------------------------------------------------------------------
-- drug_options.sql — names offered in the medication explorer search box
-- -----------------------------------------------------------------------------
-- Only names recorded in at least min_admissions admissions (all data) are
-- offered, so selecting a name can never reveal a rarely used treatment.
-- Ordered by how many admissions ordered the drug, so common drugs come first.
-- -----------------------------------------------------------------------------
SELECT
    drug,
    name_key,
    is_placeholder,
    is_non_formulary,
    admissions_any,
    admissions_ordered,
    orders
FROM analytics.medication_names
WHERE admissions_any >= :min_admissions
ORDER BY admissions_ordered DESC, drug;
