"""OPT-IN smoke test of the Hospital Overview against the REAL ehr_analytics DB.

Skipped unless RUN_LIVE_DB_TESTS=1. It connects only through the read-only
ehr_dashboard role, renders the page headlessly, and checks structure and
behaviour. It asserts no patient-level data and prints nothing from the
database.

PowerShell:
    $env:RUN_LIVE_DB_TESTS = "1"; .\\.venv\\Scripts\\python.exe -m pytest -m live -v
"""

import os
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("RUN_LIVE_DB_TESTS") != "1", reason="set RUN_LIVE_DB_TESTS=1"),
]

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"


@pytest.fixture()
def app():
    from streamlit.testing.v1 import AppTest

    sys.path.insert(0, str(DASHBOARD))
    try:
        yield AppTest.from_file(str(DASHBOARD / "views" / "overview.py"), default_timeout=120)
    finally:
        sys.path.remove(str(DASHBOARD))


def assert_full_page(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert len(at.metric) == 6
    assert len(at.get("plotly_chart")) == 5
    assert len(at.dataframe) == 6  # 5 chart tables + comparison table


def test_read_only_role():
    from sqlalchemy import text

    from ehr_analytics.db import get_dashboard_engine

    with get_dashboard_engine().connect() as conn:
        assert conn.execute(text("SHOW transaction_read_only")).scalar() == "on"
        assert not conn.execute(text("SELECT has_table_privilege('clinical_notes', 'SELECT')")).scalar()
        assert not conn.execute(text("SELECT has_table_privilege('admissions', 'INSERT')")).scalar()


def test_unfiltered_filtered_and_reset(app):
    at = app.run()
    assert_full_page(at)
    unfiltered_admissions = {m.label: m.value for m in at.metric}["Admissions"]

    at.multiselect(key="f_age_groups").set_value(["60–69"])
    at.button[0].click()
    at.run()
    assert_full_page(at)
    assert {m.label: m.value for m in at.metric}["Admissions"] != unfiltered_admissions

    at.button[1].click()  # Reset
    at.run()
    assert_full_page(at)
    assert all(ms.value == [] for ms in at.multiselect)
    assert {m.label: m.value for m in at.metric}["Admissions"] == unfiltered_admissions


def test_tiny_cohort_is_blocked(app):
    at = app.run()
    at.multiselect(key="f_admission_types").set_value(["Not recorded"])
    at.multiselect(key="f_discharge_locations").set_value(["HOME"])
    at.button[0].click()
    at.run()
    assert not at.exception
    assert at.warning and not at.metric
