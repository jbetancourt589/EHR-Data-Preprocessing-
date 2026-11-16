-- -----------------------------------------------------------------------------
-- orders_per_admission.sql — how many medication orders an admission receives
-- -----------------------------------------------------------------------------
-- Bands were assigned when the profile was built (0, 1–9, 10–24, 25–49,
-- 50–99, 100–199, 200+ orders per admission). Container placeholders are not
-- counted as orders.
-- -----------------------------------------------------------------------------
WITH {{ base }}
SELECT
    orders_bucket,
    SUM(admissions) AS admissions
FROM profile
GROUP BY orders_bucket
ORDER BY orders_bucket;
