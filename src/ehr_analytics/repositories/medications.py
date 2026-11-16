"""Medication Analytics queries.

`min_admissions` parameters exist so tests can inspect tiny synthetic data;
the dashboard always uses the default (SMALL_CELL_THRESHOLD = 11).

Every query reads the precomputed summaries in the `analytics` schema, never
the 32.8M-row medications table directly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ehr_analytics.db import run_query
from ehr_analytics.domain import MEDICATION_ANALYTICS_OBJECTS
from ehr_analytics.filters import MedicationFilters, build_where
from ehr_analytics.privacy import SMALL_CELL_THRESHOLD
from ehr_analytics.repositories.overview import QueryResult
from ehr_analytics.sql_loader import build_page_query

PAGE = "medications"
TOP_N = 20
VARIANT_LIMIT = 15
PARTNER_LIMIT = 15
PAIR_LIMIT = 25
MATRIX_SIZE = 12


def _run(engine: Engine, query: str, filters: MedicationFilters, **extra: Any) -> QueryResult:
    where, params = build_where(filters)
    params = {**params, "exclude_placeholders": filters.exclude_placeholders, **extra}
    sql = build_page_query(PAGE, query, where)
    return QueryResult(run_query(engine, sql, params), sql, params)


def _run_unfiltered(engine: Engine, query: str, **params: Any) -> QueryResult:
    """Queries over ALL admissions; only their own parameters are bound/shown."""
    sql = build_page_query(PAGE, query, "TRUE")
    return QueryResult(run_query(engine, sql, params), sql, params)


def missing_analytics_objects(engine: Engine) -> list[str]:
    """Analytics views the page needs that do not exist (or are not visible)."""
    with engine.connect() as conn:
        return [
            name
            for name in MEDICATION_ANALYTICS_OBJECTS
            if conn.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar() is None
        ]


# ------------------------------------------------------------ cohort-filtered
def fetch_kpis(engine: Engine, filters: MedicationFilters) -> QueryResult:
    return _run(engine, "kpis", filters)


def fetch_top_medications(
    engine: Engine, filters: MedicationFilters, top_n: int = TOP_N,
    min_admissions: int = SMALL_CELL_THRESHOLD,
) -> QueryResult:
    return _run(engine, "top_medications", filters, top_n=top_n, min_admissions=min_admissions)


def fetch_utilization(engine: Engine, filters: MedicationFilters) -> QueryResult:
    return _run(engine, "utilization", filters)


def fetch_orders_per_admission(engine: Engine, filters: MedicationFilters) -> QueryResult:
    return _run(engine, "orders_per_admission", filters)


def fetch_drug_detail(engine: Engine, filters: MedicationFilters, drug: str) -> QueryResult:
    return _run(engine, "drug_detail", filters, drug=drug)


# --------------------------------------------- all admissions (not filtered)
def fetch_drug_options(engine: Engine, min_admissions: int = SMALL_CELL_THRESHOLD) -> QueryResult:
    return _run_unfiltered(engine, "drug_options", min_admissions=min_admissions)


def fetch_drug_routes(engine: Engine, drug: str) -> QueryResult:
    return _run_unfiltered(engine, "drug_routes", drug=drug)


def fetch_drug_variants(engine: Engine, drug: str, min_admissions: int = SMALL_CELL_THRESHOLD) -> QueryResult:
    return _run_unfiltered(
        engine, "drug_variants", drug=drug,
        min_admissions=min_admissions, variant_limit=VARIANT_LIMIT,
    )


def fetch_drug_partners(engine: Engine, drug: str, min_admissions: int = SMALL_CELL_THRESHOLD) -> QueryResult:
    return _run_unfiltered(
        engine, "drug_partners", drug=drug,
        min_admissions=min_admissions, partner_limit=PARTNER_LIMIT,
    )


def fetch_top_pairs(engine: Engine, min_admissions: int = SMALL_CELL_THRESHOLD) -> QueryResult:
    return _run_unfiltered(
        engine, "top_pairs",
        min_admissions=min_admissions, pair_limit=PAIR_LIMIT,
    )


def fetch_co_ordering_matrix(engine: Engine) -> QueryResult:
    return _run_unfiltered(engine, "co_ordering", matrix_size=MATRIX_SIZE)
