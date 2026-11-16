-- Recompute the lab summaries after the source tables change.
-- Run as postgres. Order matters: the histogram reads the bounds view.
-- Not needed for normal dashboard use (the MIMIC data is static).
REFRESH MATERIALIZED VIEW analytics.lab_name_map;
REFRESH MATERIALIZED VIEW analytics.lab_cell;
REFRESH MATERIALIZED VIEW analytics.lab_admission_profile;
REFRESH MATERIALIZED VIEW analytics.lab_day_counts;
REFRESH MATERIALIZED VIEW analytics.lab_value_trend;
REFRESH MATERIALIZED VIEW analytics.lab_value_bounds;
REFRESH MATERIALIZED VIEW analytics.lab_value_histogram;
ANALYZE analytics.lab_cell, analytics.lab_admission_profile, analytics.lab_day_counts,
        analytics.lab_value_trend, analytics.lab_value_bounds, analytics.lab_value_histogram;
