"""Cached data loaders for the dashboard.

Only small aggregate results are cached. The underlying MIMIC data is static,
so a long TTL is safe; restart the app (or clear the cache from the menu) after
any database change.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import streamlit as st
from sqlalchemy.engine import Engine

from ehr_analytics.db import get_dashboard_engine
from ehr_analytics.filters import LabFilters, MedicationFilters, OverviewFilters
from ehr_analytics.repositories import labs as lab_repo
from ehr_analytics.repositories import medications as medication_repo
from ehr_analytics.repositories import overview as overview_repo

CACHE_TTL = timedelta(hours=12)


@st.cache_resource(show_spinner=False)
def dashboard_engine() -> Engine:
    """One read-only connection pool per Streamlit server process."""
    return get_dashboard_engine()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def overview_filter_options() -> dict[str, list[str]]:
    return overview_repo.fetch_filter_options(dashboard_engine())


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def overview_bundle(
    admission_types: tuple[str, ...],
    age_groups: tuple[str, ...],
    discharge_locations: tuple[str, ...],
) -> dict:
    """Run every Hospital Overview query for one filter combination.

    Arguments are plain tuples so Streamlit can hash them as the cache key.
    Returns {"results": {name: QueryResult}, "timings_ms": {name: float}}.
    """
    filters = OverviewFilters(admission_types, age_groups, discharge_locations)
    engine = dashboard_engine()
    fetchers = {
        "kpis": overview_repo.fetch_kpis,
        "by_admission_type": overview_repo.fetch_by_admission_type,
        "los_histogram": overview_repo.fetch_los_histogram,
        "discharge_destinations": overview_repo.fetch_discharge_destinations,
        "age_groups": overview_repo.fetch_age_groups,
    }

    def timed(fetch):
        started = time.perf_counter()
        result = fetch(engine, filters)
        return result, (time.perf_counter() - started) * 1000

    # The five queries are independent, so they run concurrently on separate
    # pooled connections (pool_size 3 + max_overflow 2 = 5). PostgreSQL executes
    # them on different CPU cores; page time ≈ the slowest query, not the sum.
    with ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
        futures = {name: pool.submit(timed, fetch) for name, fetch in fetchers.items()}
        outcomes = {name: future.result() for name, future in futures.items()}
    return {
        "results": {name: result for name, (result, _) in outcomes.items()},
        "timings_ms": {name: ms for name, (_, ms) in outcomes.items()},
    }


def _run_parallel(tasks: dict) -> dict:
    """Run independent zero-argument callables concurrently; return results and ms."""

    def timed(fn):
        started = time.perf_counter()
        result = fn()
        return result, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        futures = {name: pool.submit(timed, fn) for name, fn in tasks.items()}
        outcomes = {name: future.result() for name, future in futures.items()}
    return {
        "results": {name: r for name, (r, _) in outcomes.items()},
        "timings_ms": {name: ms for name, (_, ms) in outcomes.items()},
    }


# ------------------------------------------------------------------ medications
@st.cache_data(ttl=timedelta(seconds=60), show_spinner=False)
def medication_objects_missing() -> list[str]:
    """Short TTL so the page notices soon after the summaries are built."""
    return medication_repo.missing_analytics_objects(dashboard_engine())


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def medication_bundle(
    admission_types: tuple[str, ...], age_groups: tuple[str, ...], exclude_placeholders: bool
) -> dict:
    filters = MedicationFilters(admission_types, age_groups, exclude_placeholders)
    engine = dashboard_engine()
    return _run_parallel({
        "kpis": lambda: medication_repo.fetch_kpis(engine, filters),
        "top_medications": lambda: medication_repo.fetch_top_medications(engine, filters),
        "utilization": lambda: medication_repo.fetch_utilization(engine, filters),
        "orders_per_admission": lambda: medication_repo.fetch_orders_per_admission(engine, filters),
    })


def medication_population_admissions() -> float:
    """Unfiltered admissions total (reuses the cached unfiltered bundle)."""
    row = medication_bundle((), (), True)["results"]["kpis"].data.iloc[0]
    return float(row["admissions"])


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def medication_drug_options():
    return medication_repo.fetch_drug_options(dashboard_engine())


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def medication_drug_detail(
    drug: str, admission_types: tuple[str, ...], age_groups: tuple[str, ...], exclude_placeholders: bool
):
    filters = MedicationFilters(admission_types, age_groups, exclude_placeholders)
    return medication_repo.fetch_drug_detail(dashboard_engine(), filters, drug)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def medication_drug_context(drug: str) -> dict:
    """Routes, related names, and co-ordered partners (all admissions)."""
    engine = dashboard_engine()
    return _run_parallel({
        "routes": lambda: medication_repo.fetch_drug_routes(engine, drug),
        "variants": lambda: medication_repo.fetch_drug_variants(engine, drug),
        "partners": lambda: medication_repo.fetch_drug_partners(engine, drug),
    })


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def medication_co_ordering() -> dict:
    engine = dashboard_engine()
    return _run_parallel({
        "matrix": lambda: medication_repo.fetch_co_ordering_matrix(engine),
        "pairs": lambda: medication_repo.fetch_top_pairs(engine),
    })


# ------------------------------------------------------------------------- labs
@st.cache_data(ttl=timedelta(seconds=60), show_spinner=False)
def lab_objects_missing() -> list[str]:
    return lab_repo.missing_analytics_objects(dashboard_engine())


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def lab_year_range() -> tuple[int, int] | None:
    row = lab_repo.fetch_year_range(dashboard_engine()).data.iloc[0]
    if row["first_year"] is None or row["first_year"] != row["first_year"]:
        return None
    return int(row["first_year"]), int(row["last_year"])


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def lab_test_options():
    return lab_repo.fetch_test_options(dashboard_engine())


def _lab_filters(admission_types, lab_names, year_from, year_to) -> LabFilters:
    return LabFilters(admission_types, lab_names, year_from, year_to)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def lab_bundle(admission_types: tuple[str, ...], lab_names: tuple[str, ...],
               year_from: int | None, year_to: int | None) -> dict:
    filters = _lab_filters(admission_types, lab_names, year_from, year_to)
    engine = dashboard_engine()
    return _run_parallel({
        "kpis": lambda: lab_repo.fetch_kpis(engine, filters),
        "top_tests": lambda: lab_repo.fetch_top_tests(engine, filters),
    })


def lab_population() -> dict:
    """Unfiltered KPI row (reuses the cached unfiltered bundle)."""
    row = lab_bundle((), (), None, None)["results"]["kpis"].data.iloc[0]
    return {k: (None if v is None else float(v)) for k, v in row.items()}


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def lab_test_bundle(lab_name: str, units: str, admission_types: tuple[str, ...],
                    year_from: int | None, year_to: int | None) -> dict:
    """Per-test queries. The test is chosen explicitly, so the multi-test filter is not applied."""
    filters = _lab_filters(admission_types, (), year_from, year_to)
    engine = dashboard_engine()
    return _run_parallel({
        "counts_by_year": lambda: lab_repo.fetch_counts_by_year(engine, filters, lab_name, units),
        "counts_by_day": lambda: lab_repo.fetch_counts_by_day(engine, filters, lab_name, units),
        "histogram": lambda: lab_repo.fetch_histogram(engine, filters, lab_name, units),
        "value_classes": lambda: lab_repo.fetch_value_classes(engine, filters, lab_name, units),
    })


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def lab_value_trend(lab_name: str, units: str, axis: str):
    return lab_repo.fetch_value_trend(dashboard_engine(), lab_name, units, axis)


def population_kpis() -> dict:
    """Unfiltered totals for the filter-differencing check.

    Reuses the cached unfiltered bundle instead of running the KPI query again.
    """
    row = overview_bundle((), (), ())["results"]["kpis"].data.iloc[0]
    return {k: (None if v is None else float(v)) for k, v in row.items()}
