-- -----------------------------------------------------------------------------
-- drug_routes.sql — administration routes recorded on the selected drug's orders
-- -----------------------------------------------------------------------------
-- All admissions (route summary is not split by cohort filters). MED_STOP
-- events never carry a route, so only orders are counted.
-- -----------------------------------------------------------------------------
SELECT
    route,
    orders,
    admissions
FROM analytics.med_route_summary
WHERE drug = :drug
ORDER BY orders DESC, route;
