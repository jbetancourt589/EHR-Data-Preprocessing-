"""Lab Results Analytics queries.

Every query reads the precomputed summaries in the `analytics` schema
(sql/analytics/004_lab_summaries.sql), never the 27.2M-row lab_results table.
`min_admissions` parameters exist so tests can inspect tiny synthetic data;
the dashboard always uses the default (SMALL_CELL_THRESHOLD = 11).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ehr_analytics.db import run_query
from ehr_analytics.domain import LAB_ANALYTICS_OBJECTS
from ehr_analytics.filters import LabFilters, build_lab_where
from ehr_analytics.privacy import SMALL_CELL_THRESHOLD
from ehr_analytics.repositories.overview import QueryResult
from ehr_analytics.sql_loader import build_page_query

PAGE = "labs"
TOP_N = 15


def _run(engine: Engine, query: str, filters: LabFilters, **extra: Any) -> QueryResult:
    """Filtered query: binds the filter values plus `extra` parameters."""
    fragments, params = build_lab_where(filters)
    where = fragments.pop("where")
    sql = build_page_query(PAGE, query, where, **fragments)
    params = {**params, **extra}
    return QueryResult(run_query(engine, sql, params), sql, params)


def _run_type_only(engine: Engine, query: str, filters: LabFilters, **extra: Any) -> QueryResult:
    """Queries on summaries without a year column: only admission type applies.

    Only the parameters the query actually uses are bound (and shown in the
    SQL tab), so an unused year range is never displayed as if it applied.
    """
    type_only = LabFilters(admission_types=filters.admission_types)
    fragments, params = build_lab_where(type_only)
    where = fragments.pop("where")
    sql = build_page_query(PAGE, query, where, **fragments)
    params = {**params, **extra}
    return QueryResult(run_query(engine, sql, params), sql, params)


def _run_unfiltered(engine: Engine, query: str, **params: Any) -> QueryResult:
    sql = build_page_query(PAGE, query, "TRUE", cohort_where="TRUE", type_where="TRUE")
    return QueryResult(run_query(engine, sql, params), sql, params)


def missing_analytics_objects(engine: Engine) -> list[str]:
    """Analytics objects the page needs that do not exist (or are not visible)."""
    with engine.connect() as conn:
        return [
            name
            for name in LAB_ANALYTICS_OBJECTS
            if conn.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar() is None
        ]


# ------------------------------------------------------------- cohort-filtered
def fetch_kpis(engine: Engine, filters: LabFilters) -> QueryResult:
    return _run(engine, "kpis", filters)


def fetch_top_tests(
    engine: Engine, filters: LabFilters, top_n: int = TOP_N, min_admissions: int = SMALL_CELL_THRESHOLD
) -> QueryResult:
    return _run(engine, "top_tests", filters, top_n=top_n, min_admissions=min_admissions)


def fetch_counts_by_year(engine: Engine, filters: LabFilters, lab_name: str, units: str) -> QueryResult:
    return _run(engine, "counts_by_year", filters, lab_name=lab_name, units=units)


def fetch_counts_by_day(engine: Engine, filters: LabFilters, lab_name: str, units: str) -> QueryResult:
    return _run_type_only(engine, "counts_by_day", filters, lab_name=lab_name, units=units)


def fetch_histogram(engine: Engine, filters: LabFilters, lab_name: str, units: str) -> QueryResult:
    return _run_type_only(engine, "histogram", filters, lab_name=lab_name, units=units)


def fetch_value_classes(engine: Engine, filters: LabFilters, lab_name: str, units: str) -> QueryResult:
    return _run_type_only(engine, "value_classes", filters, lab_name=lab_name, units=units)


# ---------------------------------------------- all admissions (not filtered)
def fetch_test_options(engine: Engine, min_admissions: int = SMALL_CELL_THRESHOLD) -> QueryResult:
    return _run_unfiltered(engine, "test_options", min_admissions=min_admissions)


def fetch_year_range(engine: Engine) -> QueryResult:
    return _run_unfiltered(engine, "year_range")


def fetch_value_trend(engine: Engine, lab_name: str, units: str, axis: str) -> QueryResult:
    if axis not in ("day", "year"):
        raise ValueError("axis must be 'day' or 'year'")
    return _run_unfiltered(engine, "value_trend", lab_name=lab_name, units=units, axis=axis)
