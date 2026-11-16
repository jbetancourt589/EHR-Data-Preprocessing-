-- -----------------------------------------------------------------------------
-- drug_variants.sql — other recorded names related to the selected drug
-- -----------------------------------------------------------------------------
-- Name strategy: names are NEVER merged. This query only shows related names
-- next to each other so the user can decide whether they belong together.
--
--   same_name     identical after lower-casing, removing a leading "*Nf*"
--                 (non-formulary) marker and collapsing punctuation, e.g.
--                 "Oxycodone--Acetaminophen" vs "Oxycodone-Acetaminophen"
--   contains_name another name that contains this name as a phrase, e.g.
--                 "Insulin" -> "Insulin Glargine" (a different product)
--
-- LIKE treats % and _ as wildcards, and drug names can contain "%" (e.g.
-- "0.9%"), so those characters are escaped before building the pattern.
-- -----------------------------------------------------------------------------
WITH selected AS (
    SELECT
        name_key,
        replace(replace(replace(name_key, '\', '\\'), '%', '\%'), '_', '\_') AS key_pattern
    FROM analytics.medication_names
    WHERE drug = :drug
)
SELECT
    n.drug,
    CASE WHEN n.name_key = s.name_key THEN 'same_name' ELSE 'contains_name' END AS match_type,
    n.is_non_formulary,
    n.orders,
    n.admissions_any
FROM analytics.medication_names AS n
CROSS JOIN selected AS s
WHERE n.drug <> :drug
  AND n.admissions_any >= :min_admissions
  AND (
        n.name_key = s.name_key
     OR (' ' || n.name_key || ' ') LIKE ('% ' || s.key_pattern || ' %')
  )
ORDER BY (n.name_key = s.name_key) DESC, n.admissions_any DESC, n.drug
LIMIT :variant_limit;
