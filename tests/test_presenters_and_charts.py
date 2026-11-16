import math

import pandas as pd
import plotly.graph_objects as go

from ehr_analytics.charts import overview as charts
from ehr_analytics.presenters import formatting as fmt
from ehr_analytics.presenters import overview as present
from ehr_analytics.privacy import OTHER_LABEL


def kpi_row(**overrides):
    row = dict(
        admissions=491_699, patients=201_117, los_valid_n=491_410, los_missing_n=132,
        los_negative_n=157, los_mean_days=4.8, los_p25_days=1.1, los_median_days=2.8,
        los_p75_days=5.6,
    )
    row.update(overrides)
    return row


def test_kpis_exact_for_unfiltered_view():
    view = present.present_kpis(kpi_row(), exact=True)
    assert view.admissions == "491,699"
    assert view.los_valid == "491,410"
    assert view.excluded == "289"
    assert view.los_median == "2.8 days"


def test_kpis_rounded_for_filtered_view():
    view = present.present_kpis(kpi_row(), exact=False)
    assert view.admissions == "491,700"
    assert view.excluded_missing == "130"


def test_kpis_exact_mode_uses_complementary_suppression():
    # Exact counts: missing=3 is small, so negative (40) is hidden as its
    # complement; the total of both (43, two hidden cells) is safe to show.
    view = present.present_kpis(kpi_row(los_valid_n=1000, los_missing_n=3, los_negative_n=40,
                                        admissions=1043), exact=True)
    assert view.excluded_missing == "<11"
    assert view.excluded_negative == "<11"
    assert view.excluded == "43"
    assert view.los_valid == "1,000"


def test_kpis_rounded_mode_never_hides_large_valid_count():
    # Regression (found in live testing): a filtered cohort of ~4,000 with 2
    # missing timestamps and 0 negative stays showed "Valid stays: <11" because
    # the only non-zero complement was the large valid count.
    view = present.present_kpis(kpi_row(admissions=4015, patients=3490, los_valid_n=4013,
                                        los_missing_n=2, los_negative_n=0), exact=False)
    assert view.los_valid == "4,015"
    assert view.excluded_missing == "<11"
    assert view.excluded_negative == "0"
    assert view.excluded == "<11"


def test_kpis_hide_statistics_for_small_cohorts():
    view = present.present_kpis(kpi_row(admissions=20, patients=15, los_valid_n=20, los_missing_n=0,
                                        los_negative_n=0), exact=False)
    assert view.los_mean == "—"
    assert view.los_median == "—"


def by_type_raw():
    return pd.DataFrame({
        "admission_type": ["EW EMER.", "URGENT", "Not recorded", "ELECTIVE"],
        "admissions": [1000, 400, 6, 300],
        "los_valid_n": [990, 400, 0, 25],
        "los_mean_days": [5.0, 4.0, None, 2.0],
        "los_p10_days": [0.5, 0.4, None, 0.2],
        "los_p25_days": [1.0, 1.0, None, 0.5],
        "los_median_days": [3.0, 2.5, None, 1.0],
        "los_p75_days": [6.0, 5.0, None, 2.0],
        "los_p90_days": [12.0, 9.0, None, 4.0],
        "discharge_recorded_n": [800, 300, 0, 200],
        "discharged_home_n": [400, 150, 0, 150],
        "discharged_snf_n": [100, 40, 0, 4],
        "died_n": [30, 12, 0, 2],
    })


def test_by_type_merges_small_and_blanks_statistics():
    out = present.present_by_admission_type(by_type_raw())
    # Only the small group (Not recorded, 6) is merged; large groups are never
    # hidden as complements because breakdown counts are rounded.
    assert list(out["admission_type"]) == ["EW EMER.", "URGENT", "ELECTIVE", OTHER_LABEL]
    other = out.iloc[-1]
    assert other["is_other"]
    assert math.isnan(other["admissions"])       # Other is itself < 11: suppressed
    assert math.isnan(other["los_median_days"])


def test_by_type_hides_statistics_below_minimum():
    raw = by_type_raw()
    raw.loc[3, "admissions"] = 3000  # make ELECTIVE large; it still has only 25 valid stays
    raw.loc[2, "admissions"] = 60
    out = present.present_by_admission_type(raw).set_index("admission_type")
    assert math.isnan(out.loc["ELECTIVE", "los_median_days"])
    assert out.loc["EW EMER.", "los_median_days"] == 3.0


def test_by_type_outcome_columns_protected():
    raw = by_type_raw()
    raw.loc[2, "admissions"] = 60  # nothing merged
    out = present.present_by_admission_type(raw).set_index("admission_type")
    assert math.isnan(out.loc["ELECTIVE", "died_pct"])  # died_n=2 suppressed
    assert out.loc["EW EMER.", "home_pct"] == 50.0


def test_age_groups_follow_fixed_order():
    raw = pd.DataFrame({
        "age_group": ["90+ (capped)", "18–29", "Not recorded", "60–69"],
        "admissions": [200, 300, 50, 400], "patients": [100, 150, 40, 200],
        "los_valid_n": [200, 300, 50, 400], "los_median_days": [3.0, 2.0, 2.0, 3.5],
    })
    out = present.present_age_groups(raw)
    assert list(out["age_group"]) == ["18–29", "60–69", "90+ (capped)", "Not recorded"]


def test_histogram_fills_and_suppresses_bins():
    raw = pd.DataFrame({"bin_start_day": [0, 1, 2, 30], "admissions": [500, 300, 4, 60]})
    out = present.present_los_histogram(raw, cap=30)
    assert len(out) == 31
    assert out.loc[out["bin_start_day"] == 2, "suppressed"].item()
    assert out["bin_label"].iloc[-1] == "30+"
    assert out.loc[out["bin_start_day"] == 3, "admissions"].item() == 0


def test_histogram_empty():
    out = present.present_los_histogram(pd.DataFrame({"bin_start_day": [], "admissions": []}))
    assert out.empty


def test_formatting_cells():
    assert fmt.count_cell(float("nan")) == fmt.SUPPRESSED
    assert fmt.days_cell(None) == fmt.NOT_AVAILABLE
    assert fmt.percent_cell(12.345) == "12.3%"
    assert fmt.range_cell(1.0, 5.56) == "1.0–5.6"
    assert fmt.range_cell(None, 2.0) == fmt.NOT_AVAILABLE


def test_charts_handle_empty_and_real_data():
    for mode in ("light", "dark"):
        empty = pd.DataFrame(columns=["admission_type", "admissions", "share_pct"])
        assert isinstance(charts.category_bar(empty, "admission_type", mode=mode), go.Figure)
        out = present.present_by_admission_type(by_type_raw())
        fig = charts.category_bar(out, "admission_type", mode=mode)
        assert len(fig.data[0].y) == out["admissions"].notna().sum()  # suppressed rows not drawn
        box = charts.los_box_by_type(out, mode=mode)
        assert all(label != OTHER_LABEL for label in box.data[0].y)


def test_gray_reserved_for_missing_and_other():
    raw = by_type_raw()
    extra = raw.iloc[[2]].assign(admission_type="DIRECT EMER.", admissions=8)
    out = present.present_by_admission_type(pd.concat([raw, extra], ignore_index=True))  # Other = 6 + 8 = 14
    fig = charts.category_bar(out, "admission_type", mode="light")
    colors = dict(zip(fig.data[0].y, fig.data[0].marker.color))
    assert colors[OTHER_LABEL] == "#898781"
    assert colors["EW EMER."] == "#2a78d6"
