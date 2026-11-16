"""Hospital Overview queries.

Each function takes an Engine (so tests can pass the synthetic test database)
and returns a QueryResult: the raw aggregate DataFrame plus the exact SQL and
parameters used, which the dashboard shows in its "SQL" tabs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

from ehr_analytics.db import run_query
from ehr_analytics.domain import LOS_HISTOGRAM_CAP_DAYS
from ehr_analytics.filters import OverviewFilters, build_where
from ehr_analytics.sql_loader import build_page_query

PAGE = "overview"


@dataclass(frozen=True)
class QueryResult:
    data: pd.DataFrame
    sql: str
    params: dict[str, Any] = field(default_factory=dict)


def _run(engine: Engine, query: str, filters: OverviewFilters, **extra: Any) -> QueryResult:
    where, params = build_where(filters)
    params = {**params, **extra}
    sql = build_page_query(PAGE, query, where)
    return QueryResult(run_query(engine, sql, params), sql, params)


def fetch_kpis(engine: Engine, filters: OverviewFilters) -> QueryResult:
    return _run(engine, "kpis", filters)


def fetch_by_admission_type(engine: Engine, filters: OverviewFilters) -> QueryResult:
    return _run(engine, "by_admission_type", filters)


def fetch_discharge_destinations(engine: Engine, filters: OverviewFilters) -> QueryResult:
    return _run(engine, "discharge_destinations", filters)


def fetch_age_groups(engine: Engine, filters: OverviewFilters) -> QueryResult:
    return _run(engine, "age_groups", filters)


def fetch_los_histogram(engine: Engine, filters: OverviewFilters) -> QueryResult:
    return _run(engine, "los_histogram", filters, los_cap_days=LOS_HISTOGRAM_CAP_DAYS)


def fetch_filter_options(engine: Engine) -> dict[str, list[str]]:
    """Category labels per dimension, e.g. {"admission_type": [...], ...}."""
    result = _run(engine, "filter_options", OverviewFilters())
    options: dict[str, list[str]] = {}
    for dimension, label in result.data.itertuples(index=False):
        options.setdefault(dimension, []).append(label)
    return options
