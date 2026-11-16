"""Page 3 — Lab Results Analytics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.data import (
    lab_bundle,
    lab_objects_missing,
    lab_population,
    lab_test_bundle,
    lab_test_options,
    lab_value_trend,
    lab_year_range,
    overview_filter_options,
)
from components.ui import chart_card, page_header, sql_panel, stop_with_error, theme_mode
from ehr_analytics.charts import labs as charts
from ehr_analytics.charts.medications import ranked_bar
from ehr_analytics.domain import LAB_DATE_NOTE, LAB_FLAG_NOTE, LAB_HISTOGRAM_MIN_RESULTS, LAB_QUIRKS_NOTE
from ehr_analytics.filters import LabFilters
from ehr_analytics.presenters import formatting as fmt
from ehr_analytics.presenters import labs as present
from ehr_analytics.privacy import ROUNDING_BASE, SMALL_CELL_THRESHOLD, STATISTIC_MIN_N, check_cohort

page_header(
    "Analytics · Page 3",
    "Lab Results Analytics",
    "27.2 million laboratory results, aggregated in PostgreSQL. Values are always "
    "summarized per test AND unit — results in different units are never combined.",
)

# ------------------------------------------------------------------ readiness
try:
    missing = lab_objects_missing()
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

if missing:
    st.info(
        "**Lab summaries have not been built yet.** This page reads small precomputed "
        "summaries instead of scanning 27.2 million rows on every click. They are created "
        "by `sql/analytics/004_lab_summaries.sql` (run once, as postgres).\n\n"
        f"Missing: {', '.join(f'`{m}`' for m in missing)}",
        icon=":material/build:",
    )
    st.stop()

try:
    years = lab_year_range()
    options = lab_test_options().data
    type_options = overview_filter_options().get("admission_type", [])
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

test_names = (
    options.groupby("lab_name")["results"].sum().sort_values(ascending=False).index.tolist()
    if not options.empty else []
)


# -------------------------------------------------------------------- filters
def _reset_filters() -> None:
    st.session_state["l_admission_types"] = []
    st.session_state["l_lab_names"] = []
    if years:
        st.session_state["l_years"] = years


if years:
    st.session_state.setdefault("l_years", years)

with st.container(border=True):
    with st.form("lab_filters", border=False, enter_to_submit=False):
        col_type, col_years, col_tests, col_buttons = st.columns([2.6, 2.6, 3, 1.4], vertical_alignment="bottom")
        col_type.multiselect("Admission type", type_options, key="l_admission_types",
                             placeholder="All admission types")
        if years and years[0] < years[1]:
            col_years.slider("Admission year (shifted)", min_value=years[0], max_value=years[1],
                             key="l_years", help=LAB_DATE_NOTE)
        else:
            col_years.caption("Admission year: single year available")
        col_tests.multiselect("Lab tests", test_names, key="l_lab_names", placeholder="All tests",
                              help="Restricts the KPIs, top tests and flag breakdown to these tests.")
        with col_buttons:
            st.form_submit_button("Apply", type="primary", width="stretch")
            st.form_submit_button("Reset", on_click=_reset_filters, width="stretch")

filters = LabFilters.from_selections(
    st.session_state.get("l_admission_types"),
    st.session_state.get("l_lab_names"),
    tuple(st.session_state["l_years"]) if years and "l_years" in st.session_state else None,
    years,
)

try:
    with st.spinner("Querying lab summaries…"):
        bundle = lab_bundle(filters.admission_types, filters.lab_names, filters.year_from, filters.year_to)
        population = lab_population()
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

results = bundle["results"]
kpi_row = results["kpis"].data.iloc[0]

st.caption(
    f"**Selection:** {filters.describe()}  ·  "
    + (
        f"Counts rounded to the nearest {ROUNDING_BASE}; groups under {SMALL_CELL_THRESHOLD} suppressed."
        if filters.is_active or filters.lab_names
        else f"Headline totals exact; breakdown counts rounded to the nearest {ROUNDING_BASE}."
    )
)

with st.expander("Known data quirks in this extract", icon=":material/info:"):
    st.markdown(LAB_QUIRKS_NOTE)

cohort = check_cohort(int(kpi_row["admissions"]), int(population["admissions"]), filters.is_active)
if not cohort.allowed:
    st.warning(cohort.message, icon=":material/shield_person:")
    st.stop()

mode = theme_mode()
exact = not (filters.is_active or filters.lab_names)

# ----------------------------------------------------------------------- KPIs
kpis = present.present_kpis(kpi_row, population, exact=exact)
cols = st.columns(4)
cols[0].metric("Lab results", kpis.results, border=True,
               help="All lab results matching the filters: numeric, censored and text.")
cols[1].metric("Unique lab tests", kpis.unique_tests, border=True,
               help=f"Distinct test names ({kpis.unique_test_units} test–unit combinations; "
               "a test reported in two units counts once here).")
cols[2].metric("Abnormal (of flagged)", kpis.abnormal, border=True, help=kpis.abnormal_help)
cols[3].metric("Admissions with labs", kpis.admissions_with_labs, border=True,
               help=f"Admissions with at least one lab result of any test, out of "
               f"{kpis.cohort_admissions} admissions matching admission type and year.")

assessment = present.assess_abnormal_rate(kpi_row, population)
if not assessment.estimable:
    st.warning(f"**Abnormal rate not estimable.** {assessment.reason} All counts on this page "
               "therefore describe abnormal-flagged results.", icon=":material/info:")

# ------------------------------------------------------- top tests + flags
top = present.present_top_tests(results["top_tests"].data, float(kpi_row["results"] or 0))
flags = present.present_flag_classes(kpi_row)
classes = present.present_value_classes(kpi_row)

left, right = st.columns([3, 2], gap="medium")
with left:
    chart_card(
        "Most common lab tests",
        f"Top {len(top)} tests by number of results. Tests seen in fewer than {SMALL_CELL_THRESHOLD} "
        "admissions are never listed.",
        ranked_bar(top, "lab_name", "results", value_title="Results", mode=mode,
                   hover_fields=(("share_pct", "Share of results %", ".1f"),)),
        pd.DataFrame({
            "Rank": top["rank"].astype(int) if not top.empty else [],
            "Lab test": top["lab_name"],
            "Results": top["results"].map(fmt.count_cell),
            "Share of results": top["share_pct"].map(fmt.percent_cell),
            "Units recorded": top["units_list"],
            "Numeric share": top["numeric_pct"].map(fmt.percent_cell),
        }),
        results["top_tests"].sql, results["top_tests"].params, key="lab_top_tests",
    )
with right:
    chart_card(
        "Abnormality flags",
        "Source flag exactly as recorded. 'Not flagged' is unknown, not normal; no reference "
        "ranges are inferred.",
        ranked_bar(flags, "label", "results", value_title="Results", mode=mode,
                   muted=flags["key"].isin(["flag_missing", "flag_other"]),
                   hover_fields=(("share_pct", "Share %", ".1f"),)),
        pd.concat([
            pd.DataFrame({"Group": "Flag", "Class": flags["label"],
                          "Results": flags["results"].map(fmt.count_cell),
                          "Share": flags["share_pct"].map(fmt.percent_cell)}),
            pd.DataFrame({"Group": "Value type", "Class": classes["label"],
                          "Results": classes["results"].map(fmt.count_cell),
                          "Share": classes["share_pct"].map(fmt.percent_cell)}),
        ], ignore_index=True),
        results["kpis"].sql, results["kpis"].params, key="lab_flags",
    )
    with st.expander("How flags and value types are handled"):
        st.markdown(
            f"{LAB_FLAG_NOTE}\n\n"
            "- **Censored** results carry an inequality such as `<0.01` or `>500`. The number is a "
            "detection limit, not a measurement, so they are counted but excluded from medians and "
            "histograms.\n"
            "- **Text** results (e.g. 'HEMOLYZED') are counted but not interpreted.\n"
            "- **Missing** results are the literal text 'nan' in the source file (a missing value). "
            "They are counted separately and are not findings."
        )

# -------------------------------------------------------------- test explorer
st.subheader("Test explorer", anchor=False)
st.caption(
    "Pick one test and unit. Over-time counts and the histogram follow the admission-type filter "
    "(and the year filter where noted); medians are precomputed for all admissions."
)

explorer_names = list(filters.lab_names) or test_names
if not explorer_names:
    st.info("No lab tests meet the minimum-admissions rule.")
    st.stop()

if st.session_state.get("l_test") not in explorer_names:
    st.session_state["l_test"] = explorer_names[0]
col_test, col_unit, col_axis = st.columns([3, 2, 2.4], vertical_alignment="bottom")
lab_name = col_test.selectbox("Lab test", explorer_names, key="l_test",
                              help="Ordered by number of results. Type to search.")
unit_rows = options[options["lab_name"] == lab_name].sort_values("results", ascending=False)
unit_choices = unit_rows["units"].tolist()
if not unit_choices:
    st.info("This test has no unit recorded in enough admissions to analyze.")
    st.stop()
if st.session_state.get("l_unit") not in unit_choices:
    st.session_state["l_unit"] = unit_choices[0]
units = col_unit.selectbox(
    "Unit", unit_choices, key="l_unit",
    help="Each unit is analyzed separately; values in different units are never combined.",
)
axis_label = col_axis.segmented_control(
    "Time axis", ["Day of stay", "Admission year (shifted)"], default="Day of stay", key="l_axis",
) or "Day of stay"
axis = "day" if axis_label == "Day of stay" else "year"
if len(unit_choices) > 1:
    st.caption(f"**{lab_name}** is recorded in {len(unit_choices)} units: " + ", ".join(unit_choices)
               + ". Choose one; they are not combined.")

try:
    test_bundle = lab_test_bundle(lab_name, units, filters.admission_types, filters.year_from, filters.year_to)
    trend_result = lab_value_trend(lab_name, units, axis)
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)
tr = test_bundle["results"]

counts_result = tr["counts_by_day"] if axis == "day" else tr["counts_by_year"]
counts = present.present_counts_over_time(counts_result.data, axis)
trend = present.present_value_trend(trend_result.data, axis)
x_title = "Day of stay (Before adm. = drawn before admission)" if axis == "day" else "Admission year (shifted)"
tick_every = 5 if axis == "day" else 10
applied = "admission type" if axis == "day" else "admission type, year range"

left, right = st.columns(2, gap="medium")
with left:
    chart_card(
        f"{lab_name} ({units}) — results over time",
        f"Number of results per {'day of stay' if axis == 'day' else 'shifted admission year'}. "
        f"Filters applied: {applied}.",
        charts.counts_over_time(counts, x_title=x_title, mode=mode, tick_every=tick_every),
        pd.DataFrame({"Time": counts["label"], "Results": counts["results"].map(fmt.count_cell)}),
        counts_result.sql, counts_result.params, key="lab_counts_time",
    )
with right:
    chart_card(
        f"{lab_name} ({units}) — median value over time",
        f"Line = median, band = interquartile range (p25–p75). Numeric, uncensored results only; "
        f"periods with fewer than {STATISTIC_MIN_N} results are hidden. All admissions (filters not applied).",
        charts.median_with_iqr(trend, units=units, x_title=x_title, mode=mode, tick_every=tick_every),
        pd.DataFrame({
            "Time": trend.get("label", []),
            "Results": trend.get("n_shown", pd.Series(dtype=float)).map(fmt.count_cell),
            "p25": trend.get("p25", pd.Series(dtype=float)).map(lambda v: "n/a" if pd.isna(v) else f"{v:.4g}"),
            "Median": trend.get("p50", pd.Series(dtype=float)).map(lambda v: "n/a" if pd.isna(v) else f"{v:.4g}"),
            "p75": trend.get("p75", pd.Series(dtype=float)).map(lambda v: "n/a" if pd.isna(v) else f"{v:.4g}"),
        }),
        trend_result.sql, trend_result.params, key="lab_value_trend",
    )

histogram = present.present_histogram(tr["histogram"].data)
value_types = present.present_value_classes(tr["value_classes"].data.iloc[0])
vt = dict(zip(value_types["key"], value_types["results"]))
left, right = st.columns([3, 2], gap="medium")
with left:
    chart_card(
        f"{lab_name} ({units}) — value distribution",
        "30 equal-width bins between the 1st and 99th percentiles; values outside fall in the gray "
        "end bins (no individual extreme value is shown). Filters applied: admission type.",
        charts.value_histogram(histogram, units=units, mode=mode),
        pd.DataFrame({
            f"Value ({units})": histogram["label"],
            "Results": histogram["results"].map(fmt.count_cell),
            "Share": histogram["share_pct"].map(fmt.percent_cell),
        }),
        tr["histogram"].sql, tr["histogram"].params, key="lab_histogram",
    )
with right:
    with st.container(border=True):
        st.markdown(f"**What is (and isn't) plotted for {lab_name} ({units})**")
        st.dataframe(pd.DataFrame({
            "Value type": value_types["label"],
            "Results": value_types["results"].map(fmt.count_cell),
            "In histogram & medians": ["Yes", "No — detection limit, not a measurement", "No — not numeric",
                                      "No — missing value ('nan' in source)"],
        }), hide_index=True, width="stretch")
        if histogram.empty:
            st.caption(
                f"No histogram: a test–unit needs at least {LAB_HISTOGRAM_MIN_RESULTS:,} numeric results "
                "for stable percentile-based bins."
            )
        with st.expander("SQL"):
            sql_panel(tr["value_classes"].sql, tr["value_classes"].params)

with st.expander("About dates in this dataset"):
    st.markdown(LAB_DATE_NOTE)

# --------------------------------------------------------------------- footer
timings = {**bundle["timings_ms"], **test_bundle["timings_ms"]}
st.caption(
    f"PostgreSQL time: {max(timings.values()):,.0f} ms for the slowest query "
    "(queries run in parallel on precomputed summaries; repeat views come from cache) · "
    + " · ".join(f"{name.replace('_', ' ')} {ms:,.0f} ms" for name, ms in timings.items())
)
