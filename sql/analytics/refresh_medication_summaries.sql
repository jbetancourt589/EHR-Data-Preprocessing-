-- Recompute the medication summaries after the source tables change.
-- Run as postgres. Order matters: later views read earlier ones.
-- Not needed for normal dashboard use (the MIMIC data is static).
REFRESH MATERIALIZED VIEW analytics.med_drug_cell;
REFRESH MATERIALIZED VIEW analytics.med_admission_profile;
REFRESH MATERIALIZED VIEW analytics.med_route_summary;
REFRESH MATERIALIZED VIEW analytics.med_pair_summary;
ANALYZE analytics.med_drug_cell, analytics.med_admission_profile,
        analytics.med_route_summary, analytics.med_pair_summary;
