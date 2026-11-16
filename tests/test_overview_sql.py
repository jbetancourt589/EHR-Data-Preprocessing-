"""SQL correctness for the Hospital Overview, against synthetic rows only.

Expected values are worked out by hand from conftest.ADMISSIONS:
    valid stays: 101 (2.5 d), 102 (0 d), 103 (10 d), 106 (45 d)
    missing:     104, 107        negative: 105
"""

import pytest
from sqlalchemy import text

from ehr_analytics.filters import OverviewFilters
from ehr_analytics.repositories import overview as repo

pytestmark = pytest.mark.db

ALL = OverviewFilters()


def as_dict(result, key, value):
    return dict(zip(result.data[key], result.data[value]))


def test_kpis_unfiltered(test_engine):
    row = repo.fetch_kpis(test_engine, ALL).data.iloc[0]
    assert row["admissions"] == 7
    assert row["patients"] == 4
    assert row["los_valid_n"] == 4          # zero-length stay counts as valid
    assert row["los_missing_n"] == 2
    assert row["los_negative_n"] == 1
    assert row["los_mean_days"] == pytest.approx((2.5 + 0 + 10 + 45) / 4)
    assert row["los_median_days"] == pytest.approx(6.25)  # interpolated between 2.5 and 10


def test_los_values_are_floats_not_decimals(test_engine):
    row = repo.fetch_kpis(test_engine, ALL).data.iloc[0]
    assert isinstance(row["los_mean_days"], float)


def test_by_admission_type(test_engine):
    result = repo.fetch_by_admission_type(test_engine, ALL)
    counts = as_dict(result, "admission_type", "admissions")
    assert counts == {"EW EMER.": 4, "URGENT": 1, "ELECTIVE": 1, "Not recorded": 1}
    emer = result.data.set_index("admission_type").loc["EW EMER."]
    assert emer["los_valid_n"] == 3
    assert emer["discharge_recorded_n"] == 3
    assert emer["died_n"] == 1
    assert emer["los_median_days"] == pytest.approx(10.0)


def test_discharge_destinations_keep_not_recorded(test_engine):
    counts = as_dict(repo.fetch_discharge_destinations(test_engine, ALL), "discharge_location", "admissions")
    assert counts == {"Not recorded": 3, "HOME": 2, "DIED": 1, "SKILLED NURSING FACILITY": 1}


def test_age_groups(test_engine):
    result = repo.fetch_age_groups(test_engine, ALL)
    admissions = as_dict(result, "age_group", "admissions")
    patients = as_dict(result, "age_group", "patients")
    assert admissions == {"18–29": 2, "60–69": 2, "90+ (capped)": 2, "Not recorded": 1}
    assert patients["18–29"] == 1


def test_histogram_bins_and_overflow(test_engine):
    result = repo.fetch_los_histogram(test_engine, ALL)
    assert as_dict(result, "bin_start_day", "admissions") == {0: 1, 2: 1, 10: 1, 30: 1}


def test_filter_admission_type(test_engine):
    row = repo.fetch_kpis(test_engine, OverviewFilters.from_selections(["EW EMER."])).data.iloc[0]
    assert row["admissions"] == 4
    assert row["los_missing_n"] == 1


def test_filter_on_not_recorded_label(test_engine):
    filters = OverviewFilters.from_selections(discharge_locations=["Not recorded"])
    assert repo.fetch_kpis(test_engine, filters).data.iloc[0]["admissions"] == 3


def test_filters_combine_with_and(test_engine):
    filters = OverviewFilters.from_selections(["EW EMER."], ["90+ (capped)"])
    row = repo.fetch_kpis(test_engine, filters).data.iloc[0]
    assert row["admissions"] == 1
    assert row["los_valid_n"] == 0
    assert row["los_mean_days"] is None  # no valid stays -> NULL, not 0


def test_filter_values_are_bound_not_executed(test_engine):
    evil = "x'; DROP TABLE admissions; --"
    row = repo.fetch_kpis(test_engine, OverviewFilters.from_selections([evil])).data.iloc[0]
    assert row["admissions"] == 0
    with test_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM admissions")).scalar() == 7


def test_filter_options(test_engine):
    options = repo.fetch_filter_options(test_engine)
    assert "Not recorded" in options["admission_type"]
    assert set(options["age_group"]) == {"18–29", "60–69", "90+ (capped)", "Not recorded"}


def test_queries_return_sql_and_params(test_engine):
    filters = OverviewFilters.from_selections(age_groups=["60–69"])
    result = repo.fetch_age_groups(test_engine, filters)
    assert "age_group = ANY(:age_groups)" in result.sql
    assert result.params == {"age_groups": ["60–69"]}
