"""Headless tests of the Lab Results Analytics page on SYNTHETIC data."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

pytestmark = pytest.mark.db

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
CACHED = ("lab_objects_missing", "lab_year_range", "lab_test_options", "lab_bundle",
          "lab_test_bundle", "lab_value_trend", "overview_filter_options")


@pytest.fixture()
def data_module(test_engine, monkeypatch):
    monkeypatch.syspath_prepend(str(DASHBOARD))
    import components.data as data  # noqa: PLC0415

    monkeypatch.setattr(data, "dashboard_engine", lambda: test_engine)
    for name in CACHED:
        getattr(data, name).clear()
    yield data
    for name in CACHED:
        getattr(data, name).clear()
    sys.modules.pop("components.data", None)


def page() -> AppTest:
    return AppTest.from_file(str(DASHBOARD / "views" / "labs.py"), default_timeout=60)


def allow_rare_tests(data_module, monkeypatch):
    """Let synthetic tests (all < 11 admissions) into the selectors."""
    real = data_module.lab_repo.fetch_test_options
    monkeypatch.setattr(data_module.lab_repo, "fetch_test_options", lambda engine: real(engine, min_admissions=1))
    data_module.lab_test_options.clear()


def test_page_renders_kpis_and_abnormal_honesty(data_module):
    at = page().run()
    assert not at.exception, [e.value for e in at.exception]
    metrics = {m.label: m.value for m in at.metric}
    assert list(metrics) == ["Lab results", "Unique lab tests", "Abnormal (of flagged)", "Admissions with labs"]
    assert metrics["Lab results"] == "1,209"
    # Synthetic data contain one explicit 'normal' flag (unlike the real extract),
    # with 1,207 flagged results, so the rate is estimable here.
    assert metrics["Abnormal (of flagged)"].endswith("%")
    # No synthetic test reaches 11 admissions, so none may be offered.
    assert any("No lab tests meet the minimum-admissions rule" in i.value for i in at.info)


def test_explorer_renders_all_cards(data_module, monkeypatch):
    allow_rare_tests(data_module, monkeypatch)
    at = page().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.selectbox(key="l_test").value == "Glucose"      # most results first
    assert at.selectbox(key="l_unit").value == "mg/dL"
    assert len(at.get("plotly_chart")) == 5                   # top, flags, counts, median, histogram
    assert any(s.value == "Test explorer" for s in at.subheader)


def test_units_selector_and_time_axis(data_module, monkeypatch):
    allow_rare_tests(data_module, monkeypatch)
    at = page().run()
    at.selectbox(key="l_test").set_value("MCHC").run()
    assert at.selectbox(key="l_unit").options == ["g/dL", "%"]
    assert any("recorded in 2 units" in c.value for c in at.caption)
    at.segmented_control(key="l_axis").set_value("Admission year (shifted)").run()
    assert not at.exception, [e.value for e in at.exception]


def test_small_cohort_blocked(data_module):
    at = page().run()
    at.multiselect(key="l_admission_types").set_value(["URGENT"])
    at.button[0].click()
    at.run()
    assert not at.exception
    assert any("fewer than 11" in w.value for w in at.warning)
    assert not at.metric


def test_missing_summaries_show_setup_message(data_module, monkeypatch):
    monkeypatch.setattr(data_module.lab_repo, "missing_analytics_objects", lambda engine: ["analytics.lab_cell"])
    data_module.lab_objects_missing.clear()
    at = page().run()
    assert not at.exception
    assert any("have not been built yet" in i.value for i in at.info)
