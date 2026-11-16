import re

import pytest

from ehr_analytics.domain import AGE_GROUP_ORDER, NOT_RECORDED
from ehr_analytics.filters import OverviewFilters, build_where
from ehr_analytics.sql_loader import QUERY_DIR, SqlTemplateError, build_page_query, read_sql, render

OVERVIEW_QUERIES = [p.stem for p in (QUERY_DIR / "overview").glob("*.sql") if not p.stem.startswith("_")]

# SQLAlchemy text() treats ":name" as a bind parameter even inside comments.
BIND = re.compile(r"(?<![:\w]):(\w+)")


def test_all_overview_queries_render():
    assert {"kpis", "by_admission_type", "los_histogram", "discharge_destinations", "age_groups"} <= set(
        OVERVIEW_QUERIES
    )
    for name in OVERVIEW_QUERIES:
        sql = build_page_query("overview", name, "TRUE")
        assert "{{" not in sql
        assert "admission_base AS" in sql


@pytest.mark.parametrize("name", OVERVIEW_QUERIES)
def test_only_expected_bind_parameters(name):
    filters = OverviewFilters.from_selections(["A"], ["18–29"], ["HOME"])
    where, params = build_where(filters)
    sql = build_page_query("overview", name, where)
    allowed = set(params) | {"los_cap_days"}
    assert set(BIND.findall(sql)) <= allowed


def test_render_rejects_unknown_placeholder():
    with pytest.raises(SqlTemplateError):
        render("SELECT {{ nope }}")


def test_read_sql_rejects_path_traversal():
    with pytest.raises(SqlTemplateError):
        read_sql("../admin/001_dashboard_role")


def test_python_labels_match_sql_labels():
    base = read_sql("overview/_base")
    for label in AGE_GROUP_ORDER:
        assert f"'{label}'" in base
    assert f"'{NOT_RECORDED}'" in base


def test_queries_are_read_only():
    for path in (QUERY_DIR).rglob("*.sql"):
        code = "\n".join(line.split("--")[0] for line in path.read_text(encoding="utf-8").splitlines())
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT)\b", code, re.I), path


# ------------------------------------------------------------- medications
MEDICATION_QUERIES = [p.stem for p in (QUERY_DIR / "medications").glob("*.sql") if not p.stem.startswith("_")]
MEDICATION_PARAMS = {
    "admission_types", "age_groups", "exclude_placeholders", "min_admissions", "top_n", "drug",
    "variant_limit", "partner_limit", "pair_limit", "matrix_size",
}
ANALYTICS_DIR = QUERY_DIR.parent / "analytics"


@pytest.mark.parametrize("name", MEDICATION_QUERIES)
def test_medication_queries_use_only_known_params(name):
    sql = build_page_query("medications", name, "admission_type = ANY(:admission_types)")
    assert "{{" not in sql
    assert set(BIND.findall(sql)) <= MEDICATION_PARAMS


def test_medication_queries_never_read_raw_medications_table():
    for path in (QUERY_DIR / "medications").glob("*.sql"):
        code = "\n".join(line.split("--")[0] for line in path.read_text(encoding="utf-8").splitlines())
        assert not re.search(r"\b(public\.)?medications\b", code), path.name


def test_analytics_labels_match_python():
    from ehr_analytics.domain import MEDICATION_PLACEHOLDERS

    ddl = (ANALYTICS_DIR / "001_schema_and_views.sql").read_text(encoding="utf-8")
    for label in AGE_GROUP_ORDER:
        assert f"'{label}'" in ddl
    for name in MEDICATION_PLACEHOLDERS:
        assert f"('{name}'," in ddl


def test_orders_bucket_labels_match_ddl():
    from ehr_analytics.domain import ORDERS_BUCKET_LABELS

    ddl = (ANALYTICS_DIR / "002_medication_summaries.sql").read_text(encoding="utf-8")
    assert "ELSE 6" in ddl and len(ORDERS_BUCKET_LABELS) == 7


# -------------------------------------------------------------------- labs
LAB_QUERIES = [p.stem for p in (QUERY_DIR / "labs").glob("*.sql") if not p.stem.startswith("_")]
LAB_PARAMS = {"admission_types", "lab_names", "year_from", "year_to", "min_admissions", "top_n",
              "lab_name", "units", "axis"}


@pytest.mark.parametrize("name", LAB_QUERIES)
def test_lab_queries_use_only_known_params(name):
    sql = build_page_query("labs", name, "lab_name = ANY(:lab_names)",
                           cohort_where="admit_year BETWEEN :year_from AND :year_to",
                           type_where="admission_type = ANY(:admission_types)")
    assert "{{" not in sql
    assert set(BIND.findall(sql)) <= LAB_PARAMS


def test_lab_queries_never_read_raw_lab_table():
    for path in (QUERY_DIR / "labs").glob("*.sql"):
        code = "\n".join(line.split("--")[0] for line in path.read_text(encoding="utf-8").splitlines())
        assert not re.search(r"\b(public\.)?lab_results\b", code), path.name


def test_lab_histogram_constants_match_ddl():
    from ehr_analytics.domain import LAB_HISTOGRAM_BINS, LAB_HISTOGRAM_MIN_RESULTS

    ddl = (ANALYTICS_DIR / "004_lab_summaries.sql").read_text(encoding="utf-8")
    assert f"width_bucket(l.value, b.lo, b.hi, {LAB_HISTOGRAM_BINS})" in ddl
    assert f"HAVING COUNT(*) >= {LAB_HISTOGRAM_MIN_RESULTS}" in ddl
