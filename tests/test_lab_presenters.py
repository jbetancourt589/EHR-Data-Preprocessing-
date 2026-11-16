"""Lab presenter rules: abnormal-rate honesty, units, suppression (no database)."""

import math

import pandas as pd
import plotly.graph_objects as go

from ehr_analytics.charts import labs as charts
from ehr_analytics.filters import LabFilters, build_lab_where
from ehr_analytics.presenters import labs as present


def row(**overrides):
    base = dict(results=27_241_023, numeric_results=26_635_403, censored_results=503, text_results=27_000, missing_results=578_117,
                flag_abnormal=27_241_023, flag_normal=0, flag_missing=0, flag_other=0,
                unique_tests=390, unique_test_units=565, admissions=491_699, admissions_with_labs=480_000)
    base.update(overrides)
    return base


# ------------------------------------------------------------------ filters
def test_lab_filters_fragments():
    f = LabFilters.from_selections(["URGENT"], ["Glucose"], (2120, 2150), (2105, 2214))
    fragments, params = build_lab_where(f)
    assert fragments["type_where"] == "admission_type = ANY(:admission_types)"
    assert "admit_year BETWEEN :year_from AND :year_to" in fragments["cohort_where"]
    assert "lab_name = ANY(:lab_names)" in fragments["where"]
    assert "lab_name" not in fragments["cohort_where"]      # cohort rows have no test column
    assert params == {"admission_types": ["URGENT"], "lab_names": ["Glucose"], "year_from": 2120, "year_to": 2150}


def test_full_year_range_is_no_filter():
    f = LabFilters.from_selections(None, None, (2105, 2214), (2105, 2214))
    assert not f.has_year_range and not f.is_active
    assert build_lab_where(f) == ({"where": "TRUE", "cohort_where": "TRUE", "type_where": "TRUE"}, {})


def test_test_selection_is_not_a_cohort_restriction():
    assert not LabFilters(lab_names=("Glucose",)).is_active


# --------------------------------------------------------- abnormal honesty
def test_abnormal_rate_not_estimable_when_no_normal_flags_exist():
    a = present.assess_abnormal_rate(row(), population=row())
    assert not a.estimable
    assert math.isnan(a.percent)
    assert "100%" in a.reason


def test_abnormal_rate_estimable_with_both_classes():
    data = row(flag_abnormal=300, flag_normal=700, flag_missing=50)
    a = present.assess_abnormal_rate(data, population=data)
    assert a.estimable
    assert a.percent == 30.0          # 300 / (300 + 700); unflagged results excluded


def test_abnormal_rate_needs_enough_flagged_results():
    data = row(flag_abnormal=10, flag_normal=5)
    a = present.assess_abnormal_rate(data, population=row(flag_normal=100))
    assert not a.estimable and "Fewer than 30" in a.reason


def test_kpis_show_not_estimable():
    view = present.present_kpis(row(), row(), exact=True)
    assert view.abnormal == "Not estimable"
    assert view.results == "27,241,023"
    assert view.unique_tests == "390"


def test_flag_classes_keep_missing_separate_and_suppress():
    flags = present.present_flag_classes(row(flag_abnormal=5000, flag_normal=3, flag_missing=400, flag_other=0))
    by = flags.set_index("key")
    assert by.loc["flag_abnormal", "results"] == 5000
    assert math.isnan(by.loc["flag_normal", "results"])   # 3: suppressed
    assert by.loc["flag_missing", "label"] == "Not flagged (unknown)"
    assert by.loc["flag_other", "results"] == 0


# ------------------------------------------------------------- time series
def test_day_counts_fill_all_buckets_and_label_edges():
    out = present.present_counts_over_time(pd.DataFrame({"bucket": [-1, 0, 30], "results": [500, 4, 20]}), "day")
    assert len(out) == 32
    assert out["label"].iloc[0] == "Before adm." and out["label"].iloc[-1] == "30+"
    assert math.isnan(out.loc[out["bucket"] == 0, "results"].item())   # 4: suppressed
    assert out.loc[out["bucket"] == 5, "results"].item() == 0


def test_value_trend_hides_small_periods():
    raw = pd.DataFrame({"bucket": [0, 1], "n": [600, 12], "p25": [1.0, 1.0], "p50": [2.0, 2.0], "p75": [3.0, 3.0]})
    out = present.present_value_trend(raw, "day")
    assert out.loc[0, "p50"] == 2.0
    assert math.isnan(out.loc[1, "p50"])           # n = 12 < 30


# --------------------------------------------------------------- histogram
def hist_raw():
    return pd.DataFrame({"bin": [0, 1, 15, 30, 31], "results": [20, 400, 900, 7, 25],
                         "lo": [10.0] * 5, "hi": [40.0] * 5})


def test_histogram_bins_edges_and_suppression():
    out = present.present_histogram(hist_raw())
    assert len(out) == 32
    assert out["label"].iloc[0] == "< 10" and out["label"].iloc[-1] == "≥ 40"
    assert out.loc[1, "label"] == "10–11"                       # width (40-10)/30 = 1
    assert math.isnan(out.loc[out["bin"] == 30, "results"].item())  # 7: suppressed
    assert out.loc[out["bin"] == 15, "results"].item() == 900


def test_histogram_constant_valued_test():
    out = present.present_histogram(pd.DataFrame({"bin": [1], "results": [500], "lo": [5.0], "hi": [5.0]}))
    assert len(out) == 1 and out["label"].iloc[0] == "5"


def test_histogram_empty():
    assert present.present_histogram(pd.DataFrame(columns=["bin", "results", "lo", "hi"])).empty


def test_top_tests_round_and_share():
    raw = pd.DataFrame({"lab_name": ["Glucose", "MCHC"], "results": [1_743_439, 748_264],
                        "numeric_results": [1_743_000, 748_264], "flag_abnormal": [0, 0], "flag_normal": [0, 0],
                        "admissions_lower_bound": [400_000, 200_000], "units_list": ["mg/dL", "g/dL, %"],
                        "rank": [1, 2]})
    out = present.present_top_tests(raw, total_results=27_241_023).set_index("lab_name")
    assert out.loc["Glucose", "results"] == 1_743_440
    assert out.loc["MCHC", "units_list"] == "g/dL, %"
    empty = present.present_top_tests(raw.iloc[0:0], total_results=0)
    assert empty.empty and "share_pct" in empty.columns


# ------------------------------------------------------------------ charts
def test_charts_render_in_both_modes():
    hist = present.present_histogram(hist_raw())
    counts = present.present_counts_over_time(pd.DataFrame({"bucket": [0], "results": [500]}), "day")
    trend = present.present_value_trend(
        pd.DataFrame({"bucket": [0, 1], "n": [600, 600], "p25": [1.0, 1.1], "p50": [2.0, 2.1], "p75": [3.0, 3.1]}), "day")
    for mode in ("light", "dark"):
        h = charts.value_histogram(hist, units="mg/dL", mode=mode)
        assert isinstance(h, go.Figure)
        assert h.data[0].marker.color[0] == "#898781"              # below-p1 bin in gray
        assert isinstance(charts.counts_over_time(counts, x_title="Day", mode=mode), go.Figure)
        assert len(charts.median_with_iqr(trend, units="mg/dL", x_title="Day", mode=mode).data) == 3
    assert isinstance(charts.value_histogram(present.present_histogram(pd.DataFrame(columns=["bin", "results", "lo", "hi"])),
                                             units="x"), go.Figure)


def test_sparse_ticks_avoid_collision_with_wide_first_label():
    labels = ["Before adm."] + [str(d) for d in range(0, 30)] + ["30+"]
    ticks = charts.sparse_ticks(labels, 5)
    assert ticks[0] == "Before adm." and ticks[-1] == "30+"
    assert "0" not in ticks and "5" in ticks and len(ticks) < 10
    assert charts.sparse_ticks(["a", "b"], 5) == ["a", "b"]
