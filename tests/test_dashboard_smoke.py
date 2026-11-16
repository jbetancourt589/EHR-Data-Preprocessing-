"""Headless smoke test of the Hospital Overview page on SYNTHETIC data.

Streamlit's AppTest runs the real page script in-process. The engine provider
is swapped for the synthetic test database, so no MIMIC data is touched and no
dashboard credentials are needed.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

pytestmark = pytest.mark.db

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"


@pytest.fixture()
def overview_app(test_engine, monkeypatch):
    monkeypatch.syspath_prepend(str(DASHBOARD))
    import components.data as data  # noqa: PLC0415

    monkeypatch.setattr(data, "dashboard_engine", lambda: test_engine)
    for fn in (data.overview_filter_options, data.overview_bundle):
        fn.clear()
    app = AppTest.from_file(str(DASHBOARD / "views" / "overview.py"), default_timeout=30)
    yield app
    for fn in (data.overview_filter_options, data.overview_bundle):
        fn.clear()
    sys.modules.pop("components.data", None)


def test_overview_renders_unfiltered(overview_app):
    at = overview_app.run()
    assert not at.exception, [e.value for e in at.exception]
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Admissions"] == "7"          # unfiltered totals are exact
    assert metrics["Patients"] == "4"
    assert metrics["Valid stays"] == "<11"  # 4 valid stays: suppressed
    assert metrics["Mean LOS"] == "—"  # fewer than 30 valid stays
    assert len(at.multiselect) == 3
    assert any("Admission type comparison" in s.value for s in at.subheader)


def test_small_filtered_cohort_is_blocked(overview_app):
    at = overview_app.run()
    at.multiselect(key="f_admission_types").set_value(["EW EMER."])
    at.button[0].click()  # Apply
    at.run()
    assert not at.exception
    assert at.warning, "a cohort of 4 admissions must be blocked"
    assert "fewer than 11" in at.warning[0].value
    assert not at.metric  # nothing else rendered


def test_reset_clears_filters(overview_app):
    at = overview_app.run()
    at.multiselect(key="f_age_groups").set_value(["18–29"])
    at.button[0].click()
    at.run()
    at.button[1].click()  # Reset
    at.run()
    assert at.multiselect(key="f_age_groups").value == []
    assert not at.warning
