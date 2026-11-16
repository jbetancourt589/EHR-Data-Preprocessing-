"""Headless tests of the Medication Analytics page on SYNTHETIC data."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

pytestmark = pytest.mark.db

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
CACHED = (
    "medication_objects_missing", "medication_bundle", "medication_drug_options",
    "medication_drug_detail", "medication_drug_context", "medication_co_ordering",
)


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
    return AppTest.from_file(str(DASHBOARD / "views" / "medications.py"), default_timeout=60)


def test_page_renders_all_sections(data_module):
    at = page().run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [m.label for m in at.metric]
    assert labels[:6] == [
        "Medication orders", "Stop events", "Unique medications",
        "Admissions with medications", "Admissions with ≥1 order", "Medications per admission",
    ]
    metrics = dict(zip(labels, (m.value for m in at.metric)))
    assert metrics["Medication orders"] == "18"          # unfiltered: exact
    assert metrics["Stop events"] == "<11"               # 6 stops: suppressed
    assert metrics["Medications per admission"] == "—"   # < 30 admissions with orders
    subheaders = [s.value for s in at.subheader]
    assert subheaders == ["Medication utilization", "Medication explorer", "Medication co-ordering"]
    # Synthetic drugs are all in < 11 admissions: none may be listed.
    assert any("No medications meet the minimum-admissions rule" in i.value for i in at.info)


def test_explorer_blocks_rare_drug(data_module, monkeypatch):
    # Let the option list include the (rare) synthetic drugs; the presenter
    # must still refuse to show their statistics.
    from ehr_analytics.repositories import medications as repo

    real = repo.fetch_drug_options
    monkeypatch.setattr(data_module.medication_repo, "fetch_drug_options",
                        lambda engine: real(engine, min_admissions=1))
    data_module.medication_drug_options.clear()
    at = page().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.selectbox(key="m_drug").value is not None
    assert any("fewer than 11 admissions" in w.value for w in at.warning)


def test_small_cohort_is_blocked(data_module):
    at = page().run()
    at.multiselect(key="m_admission_types").set_value(["URGENT"])
    at.button[0].click()
    at.run()
    assert not at.exception
    assert any("fewer than 11" in w.value for w in at.warning)
    assert not at.metric


def test_missing_summaries_show_setup_message(data_module, monkeypatch):
    monkeypatch.setattr(data_module.medication_repo, "missing_analytics_objects",
                        lambda engine: ["analytics.med_drug_cell"])
    data_module.medication_objects_missing.clear()
    at = page().run()
    assert not at.exception
    assert any("have not been built yet" in i.value for i in at.info)
    assert not at.metric
