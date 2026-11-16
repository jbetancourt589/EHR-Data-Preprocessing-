"""Privacy and formatting rules of the medication presenter (no database)."""

import math

import pandas as pd
import plotly.graph_objects as go

from ehr_analytics.charts import medications as charts
from ehr_analytics.filters import MedicationFilters, build_where
from ehr_analytics.presenters import medications as present
from ehr_analytics.privacy import OTHER_LABEL


def kpi_row(**overrides):
    row = dict(admissions=491_699, admissions_with_events=417_120, admissions_with_orders=410_000,
               distinct_drug_orders=9_840_000, orders=17_193_856, stops=15_642_811,
               unique_medications=7_131, unique_medications_ordered=7_000)
    row.update(overrides)
    return row


# ---------------------------------------------------------------- filters
def test_placeholder_toggle_is_not_a_cohort_filter():
    f = MedicationFilters.from_selections(exclude_placeholders=False)
    assert not f.is_active
    assert build_where(f) == ("TRUE", {})


def test_medication_filters_build_where():
    f = MedicationFilters.from_selections(["URGENT"], ["60–69"])
    where, params = build_where(f)
    assert where == "admission_type = ANY(:admission_types) AND age_group = ANY(:age_groups)"
    assert params == {"admission_types": ["URGENT"], "age_groups": ["60–69"]}


# ------------------------------------------------------------------- KPIs
def test_kpis_exact_unfiltered():
    view = present.present_kpis(kpi_row(), exact=True)
    assert view.orders == "17,193,856"
    assert view.unique_medications == "7,131"
    assert view.distinct_meds_per_admission == "24.0"


def test_kpis_rounded_when_filtered():
    view = present.present_kpis(kpi_row(), exact=False)
    assert view.orders == "17,193,855"
    assert view.admissions_with_events == "417,120"


def test_kpis_small_cohort_hides_rates():
    view = present.present_kpis(kpi_row(admissions=20, admissions_with_events=15, admissions_with_orders=12,
                                        distinct_drug_orders=40, orders=50, stops=5), exact=False)
    assert view.stops == "<11"
    assert view.distinct_meds_per_admission == "—"   # fewer than 30 admissions with orders


# -------------------------------------------------------------- top lists
def top_raw():
    return pd.DataFrame({
        "drug": ["Insulin", "Heparin", "Bag"],
        "is_placeholder": [False, False, True],
        "orders": [700, 360, 250], "stops": [350, 7, 210],
        "admissions_any": [300, 200, 150], "admissions_ordered": [290, 195, 150],
        "rank_by_orders": [1, 2, 3], "rank_by_admissions": [1, 2, 3],
    })


def test_top_lists_round_and_suppress_small_stops():
    by_orders, by_admissions = present.present_top_medications(top_raw(), cohort_admissions=1000)
    row = by_orders.set_index("drug").loc["Heparin"]
    assert row["orders"] == 360
    assert math.isnan(row["stops"])           # 7 stops: suppressed
    assert math.isnan(row["stop_pct"])        # and so is the derived ratio
    assert by_orders.set_index("drug").loc["Insulin", "share_pct"] == 29.0
    assert list(by_admissions["drug"]) == ["Insulin", "Heparin", "Bag"]


def test_top_lists_empty_keep_all_columns():
    # Regression: when no drug meets the 11-admission minimum the page crashed
    # on a missing derived column.
    empty = top_raw().iloc[0:0]
    by_orders, by_admissions = present.present_top_medications(empty, cohort_admissions=50)
    for frame in (by_orders, by_admissions):
        assert frame.empty
        assert {"share_pct", "stop_pct", "orders_per_admission"} <= set(frame.columns)


# ------------------------------------------------------------ utilization
def test_utilization_merges_small_groups_and_computes_rates():
    raw = pd.DataFrame({
        "dimension": ["age_group"] * 3,
        "label": ["60–69", "18–29", "90+ (capped)"],
        "admissions": [1000, 500, 6],
        "admissions_with_orders": [900, 400, 5],
        "orders": [27000, 8000, 40], "stops": [25000, 7000, 30],
        "distinct_drug_orders": [22500, 6000, 20],
    })
    out = present.present_utilization(raw, "age_group")
    # Only the small group (90+, 6) is merged. Other is itself < 11, so it is
    # suppressed; the large groups are never hidden as complements.
    assert out["label"].tolist() == ["18–29", "60–69", OTHER_LABEL]
    rows = out.set_index("label")
    assert math.isnan(rows.loc[OTHER_LABEL, "admissions"])
    assert math.isnan(rows.loc[OTHER_LABEL, "distinct_per_admission"])
    assert rows.loc["60–69", "distinct_per_admission"] == 25.0
    assert rows.loc["18–29", "distinct_per_admission"] == 15.0   # 6000 / 400


def test_utilization_keeps_fixed_age_order():
    raw = pd.DataFrame({
        "dimension": ["age_group"] * 3, "label": ["60–69", "90+ (capped)", "18–29"],
        "admissions": [1000, 300, 500], "admissions_with_orders": [900, 250, 400],
        "orders": [1, 1, 1], "stops": [1, 1, 1], "distinct_drug_orders": [1, 1, 1],
    })
    assert present.present_utilization(raw, "age_group")["label"].tolist() == ["18–29", "60–69", "90+ (capped)"]


def test_orders_per_admission_bands_complete_and_protected():
    raw = pd.DataFrame({"orders_bucket": [0, 1, 6], "admissions": [74_000, 200_000, 4]})
    out = present.present_orders_per_admission(raw)
    assert out["label"].tolist() == ["0", "1–9", "10–24", "25–49", "50–99", "100–199", "200+"]
    assert math.isnan(out.loc[out["orders_bucket"] == 6, "admissions"].item())
    assert out.loc[out["orders_bucket"] == 2, "admissions"].item() == 0


# ---------------------------------------------------------------- explorer
def detail_rows(total_admissions=300):
    return pd.DataFrame([
        dict(dimension="total", label="All", orders=900, stops=800, admissions_any=total_admissions,
             admissions_ordered=total_admissions, adm_orders_1=150, adm_orders_2=100, adm_orders_3_5=45, adm_orders_6_plus=5),
        dict(dimension="age_group", label="60–69", orders=600, stops=500, admissions_any=200, admissions_ordered=200,
             adm_orders_1=0, adm_orders_2=0, adm_orders_3_5=0, adm_orders_6_plus=0),
        dict(dimension="age_group", label="18–29", orders=300, stops=300, admissions_any=100, admissions_ordered=100,
             adm_orders_1=0, adm_orders_2=0, adm_orders_3_5=0, adm_orders_6_plus=0),
    ])


UTIL = pd.DataFrame({
    "dimension": ["age_group", "age_group"], "label": ["60–69", "18–29"],
    "admissions": [1000, 2000], "admissions_with_orders": [900, 1500],
    "orders": [1, 1], "stops": [1, 1], "distinct_drug_orders": [1, 1],
})


def test_drug_detail_blocks_rare_drugs():
    view = present.present_drug_detail(detail_rows(total_admissions=8), UTIL, 3000)
    assert not view.allowed
    assert "fewer than 11" in view.message


def test_drug_detail_shares_and_distribution():
    view = present.present_drug_detail(detail_rows(), UTIL, 3000)
    assert view.allowed
    assert view.total["pct_of_cohort"] == 10.0
    assert view.total["orders_per_admission"] == 3.0
    by_age = view.by_age.set_index("label")
    assert by_age.loc["60–69", "pct_of_group"] == 20.0
    assert list(view.by_age["label"]) == ["18–29", "60–69"]
    assert math.isnan(view.distribution.set_index("label").loc["6+ orders", "admissions"])  # 5: suppressed


def test_routes_never_hide_dominant_route():
    # Regression (live review): IV (586k orders) was merged into Other because two
    # tiny route spellings summed to < 11.
    raw = pd.DataFrame({"route": ["IV", "FLUSH", "IV FLUSH"], "orders": [586_392, 3, 2], "admissions": [378_030, 3, 2]})
    out = present.present_routes(raw).set_index("route")
    assert out.loc["IV", "orders"] == 586_390
    assert math.isnan(out.loc[OTHER_LABEL, "orders"])   # 5 admissions: suppressed


def test_routes_merge_rare_routes():
    raw = pd.DataFrame({"route": ["IV", "PO", "NG"], "orders": [5000, 3000, 9], "admissions": [900, 600, 4]})
    out = present.present_routes(raw)
    assert OTHER_LABEL in set(out["route"])
    assert "NG" not in set(out["route"])


def test_matrix_blanks_small_cells():
    raw = pd.DataFrame({
        "row_drug": ["A", "B"], "col_drug": ["B", "A"], "pct": [0.5, 0.25],
        "admissions_both": [5, 5], "lift": [1.2, 1.2], "row_admissions": [10, 20],
    })
    matrix = present.present_co_ordering_matrix(raw)
    assert list(matrix.index) == ["B", "A"]  # ordered by admissions
    assert matrix.isna().all().all()         # 5 shared admissions: every cell hidden


# ------------------------------------------------------------------ charts
def test_charts_render_in_both_modes():
    by_orders, _ = present.present_top_medications(top_raw(), cohort_admissions=1000)
    for mode in ("light", "dark"):
        bar = charts.ranked_bar(by_orders, "drug", "orders", value_title="Orders", mode=mode,
                                muted=by_orders["is_placeholder"])
        assert isinstance(bar, go.Figure)
        assert bar.data[0].marker.color[2] == "#898781"  # placeholder in gray
        grouped = charts.orders_vs_stops(by_orders, mode=mode)
        assert [t.name for t in grouped.data] == ["Orders", "Stop events"]
        heat = charts.co_ordering_heatmap(pd.DataFrame([[None, 50.0], [25.0, None]], index=["A", "B"], columns=["A", "B"]), mode=mode)
        assert isinstance(heat, go.Figure)
    assert isinstance(charts.ranked_bar(pd.DataFrame(), "a", "b", value_title="x"), go.Figure)
