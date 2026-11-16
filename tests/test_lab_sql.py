"""Lab summaries + queries on SYNTHETIC data (tests/conftest.py LABS).

Hand-computed expectations:
  Glucose mg/dL   1,200 numeric (value 50 + 0.25 i), 600 on hadm 101 day 0
                  (even i), 600 on hadm 103 day 1 (odd i); + 1 censored '>'
                  on 102 day 0
  Glucose (no unit) 1 text result on 102          -> unit 'Not recorded'
  MCHC            2 x g/dL on 101, 1 x % on 103    -> two units, never combined
  Potassium       1 on 105, before admission (day -1), NO flag
  Sodium          1 on 107, day 30+, flag 'normal'
  Lactate         1 on 106 with blank unit         -> 'Not recorded'
  Totals: 1,209 results = 1,206 numeric + 1 censored + 1 text + 1 missing ("nan");
          flags 1,206 abnormal + 1 normal + 1 missing; 5 tests, 7 test-units;
          7 admissions, 6 with labs (104 has none). All admissions are in 2100.
"""

import pandas as pd
import pytest

from ehr_analytics.filters import LabFilters
from ehr_analytics.repositories import labs as repo

pytestmark = pytest.mark.db

ALL = LabFilters()


def test_analytics_objects_exist(test_engine):
    assert repo.missing_analytics_objects(test_engine) == []


def test_kpis(test_engine):
    row = repo.fetch_kpis(test_engine, ALL).data.iloc[0]
    assert row["results"] == 1209
    assert (row["numeric_results"], row["censored_results"], row["text_results"]) == (1206, 1, 1)
    assert row["missing_results"] == 1                        # the "nan nan" row is not a text finding
    assert (row["flag_abnormal"], row["flag_normal"], row["flag_missing"], row["flag_other"]) == (1207, 1, 1, 0)
    assert row["unique_tests"] == 5                           # "glucose" merged into "Glucose"
    assert row["unique_test_units"] == 7
    assert row["admissions"] == 7
    assert row["admissions_with_labs"] == 6


def test_test_selection_restricts_results_not_cohort(test_engine):
    row = repo.fetch_kpis(test_engine, LabFilters(lab_names=("MCHC",))).data.iloc[0]
    assert row["results"] == 3
    assert row["unique_test_units"] == 2
    assert row["admissions"] == 7            # cohort unchanged by test selection


def test_admission_type_filter(test_engine):
    row = repo.fetch_kpis(test_engine, LabFilters(admission_types=("URGENT",))).data.iloc[0]
    assert row["results"] == 3               # hadm 102: censored + text + missing Glucose
    assert row["admissions"] == 1


def test_year_range_filter(test_engine):
    outside = repo.fetch_kpis(test_engine, LabFilters(year_from=2101, year_to=2110)).data.iloc[0]
    assert outside["results"] == 0
    assert outside["admissions"] == 0
    inside = repo.fetch_kpis(test_engine, LabFilters(year_from=2100, year_to=2100)).data.iloc[0]
    assert inside["results"] == 1209


def test_year_range_bounds(test_engine):
    row = repo.fetch_year_range(test_engine).data.iloc[0]
    assert (row["first_year"], row["last_year"]) == (2100, 2100)


def test_top_tests_and_privacy_minimum(test_engine):
    top = repo.fetch_top_tests(test_engine, ALL, min_admissions=1).data.set_index("lab_name")
    assert top.loc["Glucose", "results"] == 1203
    assert top.loc["Glucose", "rank"] == 1
    assert top.loc["Glucose", "admissions_lower_bound"] == 3   # mg/dL unit: 101, 102, 103
    assert top.loc["MCHC", "units_list"] == "g/dL, %"            # ordered by results
    assert repo.fetch_top_tests(test_engine, ALL).data.empty     # nothing reaches 11 admissions


def test_units_are_never_combined(test_engine):
    options = repo.fetch_test_options(test_engine, min_admissions=1).data
    mchc = options[options["lab_name"] == "MCHC"].set_index("units")
    assert mchc.loc["g/dL", "results"] == 2 and mchc.loc["%", "results"] == 1
    assert "Not recorded" in set(options.loc[options["lab_name"] == "Lactate", "units"])
    assert "Not recorded" in set(options.loc[options["lab_name"] == "Glucose", "units"])


def test_counts_by_day_include_before_admission_and_overflow(test_engine):
    glucose = repo.fetch_counts_by_day(test_engine, ALL, "Glucose", "mg/dL").data.set_index("bucket")
    assert glucose.loc[0, "results"] == 601      # 600 numeric + 1 censored
    assert glucose.loc[1, "results"] == 600
    potassium = repo.fetch_counts_by_day(test_engine, ALL, "Potassium", "mEq/L").data
    assert potassium["bucket"].tolist() == [-1]
    sodium = repo.fetch_counts_by_day(test_engine, ALL, "Sodium", "mEq/L").data
    assert sodium["bucket"].tolist() == [30]


def test_counts_by_day_ignore_year_filter_by_design(test_engine):
    result = repo.fetch_counts_by_day(test_engine, LabFilters(year_from=2101, year_to=2110), "Glucose", "mg/dL")
    assert "year_from" not in result.params      # not bound, so never displayed as applied
    assert result.data["results"].sum() == 1201


def test_counts_by_year(test_engine):
    data = repo.fetch_counts_by_year(test_engine, ALL, "Glucose", "mg/dL").data
    assert data["bucket"].tolist() == [2100]
    assert data["results"].iloc[0] == 1201


def test_value_trend_excludes_censored_and_uses_quartiles(test_engine):
    day = repo.fetch_value_trend(test_engine, "Glucose", "mg/dL", "day").data.set_index("bucket")
    assert day.loc[0, "n"] == 600                # censored '>' result excluded
    assert day.loc[0, "p50"] == pytest.approx(199.75)
    assert day.loc[1, "p50"] == pytest.approx(200.0)
    year = repo.fetch_value_trend(test_engine, "Glucose", "mg/dL", "year").data
    assert year["n"].tolist() == [1200]


def test_value_trend_rejects_bad_axis(test_engine):
    with pytest.raises(ValueError):
        repo.fetch_value_trend(test_engine, "Glucose", "mg/dL", "month; DROP TABLE x")


def test_histogram_bins(test_engine):
    hist = repo.fetch_histogram(test_engine, ALL, "Glucose", "mg/dL").data
    assert hist["results"].sum() == 1200         # numeric, uncensored only
    assert set(hist["bin"]) <= set(range(0, 32))
    assert hist["lo"].iloc[0] < hist["hi"].iloc[0]
    assert hist.loc[hist["bin"] == 0, "results"].sum() > 0   # below the 1st percentile
    # Tests with < 1,000 numeric results have no histogram.
    assert repo.fetch_histogram(test_engine, ALL, "MCHC", "g/dL").data.empty


def test_value_classes(test_engine):
    row = repo.fetch_value_classes(test_engine, ALL, "Glucose", "mg/dL").data.iloc[0]
    assert (row["numeric_results"], row["censored_results"], row["text_results"]) == (1200, 1, 0)
    text_row = repo.fetch_value_classes(test_engine, ALL, "Glucose", "Not recorded").data.iloc[0]
    assert text_row["text_results"] == 1 and text_row["missing_results"] == 1


def test_names_are_bind_parameters(test_engine):
    evil = "x'; DROP TABLE lab_results; --"
    assert repo.fetch_counts_by_day(test_engine, ALL, evil, "mg/dL").data.empty
    assert repo.fetch_kpis(test_engine, ALL).data.iloc[0]["results"] == 1209


def test_empty_selection_returns_zeros_not_errors(test_engine):
    row = repo.fetch_kpis(test_engine, LabFilters(lab_names=("No such test",))).data.iloc[0]
    assert row["results"] == 0 and row["unique_tests"] == 0
    assert pd.notna(row["admissions"])
