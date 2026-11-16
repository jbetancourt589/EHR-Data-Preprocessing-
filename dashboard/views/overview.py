"""Page 1 — Hospital Overview."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.data import overview_bundle, overview_filter_options, population_kpis
from components.ui import chart_card, page_header, sql_panel, stop_with_error, theme_mode
from ehr_analytics.charts import overview as charts
from ehr_analytics.domain import AGE_GROUP_ORDER, ANCHOR_AGE_NOTE, LOS_HISTOGRAM_CAP_DAYS
from ehr_analytics.filters import OverviewFilters
from ehr_analytics.presenters import formatting as fmt
from ehr_analytics.presenters import overview as present
from ehr_analytics.privacy import (
    ROUNDING_BASE,
    SMALL_CELL_THRESHOLD,
    STATISTIC_MIN_N,
    check_cohort,
    round_count,
)

FILTER_KEYS = ("f_admission_types", "f_age_groups", "f_discharge_locations")

page_header(
    "Analytics · Page 1",
    "Hospital Overview",
    "Admissions, length of stay, and discharge outcomes across "
    "MIMIC-derived hospital admissions. All figures are computed in PostgreSQL.",
)


try:
    options = overview_filter_options()
    population = population_kpis()
except Exception as exc:  # noqa: BLE001 - shown to the user, details in console
    stop_with_error(exc)


# ------------------------------------------------------------------------ filters
def _reset_filters() -> None:
    for key in FILTER_KEYS:
        st.session_state[key] = []


age_options = [g for g in AGE_GROUP_ORDER if g in set(options.get("age_group", []))]

with st.container(border=True):
    with st.form("overview_filters", border=False, enter_to_submit=False):
        col_type, col_age, col_dest, col_buttons = st.columns(
            [3, 2.4, 3, 1.4], vertical_alignment="bottom"
        )
        col_type.multiselect(
            "Admission type",
            options.get("admission_type", []),
            key="f_admission_types",
            placeholder="All admission types",
        )
        col_age.multiselect(
            "Anchor age group",
            age_options,
            key="f_age_groups",
            placeholder="All ages",
            help=ANCHOR_AGE_NOTE,
        )
        col_dest.multiselect(
            "Discharge destination",
            options.get("discharge_location", []),
            key="f_discharge_locations",
            placeholder="All destinations",
        )
        with col_buttons:
            st.form_submit_button("Apply", type="primary", width="stretch")
            st.form_submit_button("Reset", on_click=_reset_filters, width="stretch")

filters = OverviewFilters.from_selections(
    st.session_state.get("f_admission_types"),
    st.session_state.get("f_age_groups"),
    st.session_state.get("f_discharge_locations"),
)

# ----------------------------------------------------------------------- load data
try:
    with st.spinner("Querying PostgreSQL…"):
        bundle = overview_bundle(
            filters.admission_types, filters.age_groups, filters.discharge_locations
        )
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

results = bundle["results"]
kpi_row = results["kpis"].data.iloc[0]

st.caption(
    f"**Cohort:** {filters.describe()}  ·  "
    + (
        f"Counts rounded to the nearest {ROUNDING_BASE}; groups under "
        f"{SMALL_CELL_THRESHOLD} suppressed."
        if filters.is_active
        else f"Headline totals exact; breakdown counts rounded to the nearest {ROUNDING_BASE}."
    )
)

cohort = check_cohort(int(kpi_row["admissions"]), int(population["admissions"]), filters.is_active)
if not cohort.allowed:
    st.warning(cohort.message, icon=":material/shield_person:")
    st.stop()

# -------------------------------------------------------------------------- KPIs
kpis = present.present_kpis(kpi_row, exact=not filters.is_active)

cols = st.columns(6)
cols[0].metric(
    "Patients", kpis.patients, border=True,
    help="Distinct patients (subject_id) with at least one admission in the cohort.",
)
cols[1].metric(
    "Admissions", kpis.admissions, border=True,
    help="Hospital admissions (hadm_id) matching the filters.",
)
cols[2].metric(
    "Valid stays", kpis.los_valid, border=True,
    help=f"{kpis.los_valid_pct} of admissions. Valid = both timestamps present and "
    "discharge on or after admission (zero-length stays included).",
)
cols[3].metric(
    "Excluded", kpis.excluded, border=True,
    help=f"Admissions excluded from length-of-stay statistics. Missing timestamp: {kpis.excluded_missing} · Discharge before admission: "
    f"{kpis.excluded_negative}. These records are kept in the database and in all "
    "counts; they are only left out of length-of-stay statistics.",
)
cols[4].metric(
    "Mean LOS", kpis.los_mean, border=True,
    help="Mean length of stay (LOS). Arithmetic mean over admissions with valid stay dates. "
    "Pulled upward by a long right tail; compare with the median.",
)
cols[5].metric(
    "Median LOS", kpis.los_median, border=True,
    help=f"Median length of stay: 50th percentile (PERCENTILE_CONT). {kpis.los_iqr}.",
)

st.info(
    f"**Length-of-stay denominator:** {kpis.los_valid} of {kpis.admissions} admissions "
    f"({kpis.los_valid_pct}) have valid stay dates. Excluded: {kpis.excluded_missing} with a "
    f"missing timestamp and {kpis.excluded_negative} with discharge recorded before admission. "
    "No records were modified or deleted.",
    icon=":material/rule:",
)

mode = theme_mode()

# ----------------------------------------------------------- admission type views
by_type = present.present_by_admission_type(results["by_admission_type"].data)

type_table = pd.DataFrame(
    {
        "Admission type": by_type["admission_type"],
        "Admissions": by_type["admissions"].map(fmt.count_cell),
        "Share of cohort": by_type["share_pct"].map(fmt.percent_cell),
    }
)

left, right = st.columns(2, gap="medium")
with left:
    chart_card(
        "Admissions by type",
        "How patients entered the hospital. Gray bars are missing or merged small groups.",
        charts.category_bar(by_type, "admission_type", mode=mode),
        type_table,
        results["by_admission_type"].sql,
        results["by_admission_type"].params,
        key="chart_by_type",
    )

box_table = pd.DataFrame(
    {
        "Admission type": by_type["admission_type"],
        "Valid stays": by_type["los_valid_n"].map(
            lambda n: fmt.count_cell(None if pd.isna(n) else round_count(n))
        ),
        "p10": by_type["los_p10_days"].map(fmt.days_cell),
        "p25": by_type["los_p25_days"].map(fmt.days_cell),
        "Median": by_type["los_median_days"].map(fmt.days_cell),
        "p75": by_type["los_p75_days"].map(fmt.days_cell),
        "p90": by_type["los_p90_days"].map(fmt.days_cell),
        "Mean": by_type["los_mean_days"].map(fmt.days_cell),
    }
)
with right:
    chart_card(
        "Length of stay by admission type",
        f"Box = middle 50% (p25–p75), solid line = median, dashed line = mean, "
        f"whiskers = p10 and p90 (hover labels call them fences). Days. "
        f"Groups with fewer than {STATISTIC_MIN_N} valid stays are omitted.",
        charts.los_box_by_type(by_type, mode=mode),
        box_table,
        results["by_admission_type"].sql,
        results["by_admission_type"].params,
        key="chart_los_box",
    )

# ------------------------------------------------- LOS distribution + destinations
hist = present.present_los_histogram(results["los_histogram"].data)
hist_table = pd.DataFrame(
    {
        "Length of stay (days)": hist["bin_label"],
        "Admissions": hist["admissions"].map(fmt.count_cell),
    }
)
destinations = present.present_discharge_destinations(results["discharge_destinations"].data)
dest_table = pd.DataFrame(
    {
        "Discharge destination": destinations["discharge_location"],
        "Admissions": destinations["admissions"].map(fmt.count_cell),
        "Share of cohort": destinations["share_pct"].map(fmt.percent_cell),
        "Median LOS (days)": destinations["los_median_days"].map(fmt.days_cell),
    }
)

left, right = st.columns(2, gap="medium")
with left:
    chart_card(
        "Length-of-stay distribution",
        f"Admissions with valid stay dates in 1-day bins. Stays of {LOS_HISTOGRAM_CAP_DAYS} "
        "days or longer share the final gray bar.",
        charts.los_histogram(hist, mode=mode),
        hist_table,
        results["los_histogram"].sql,
        results["los_histogram"].params,
        key="chart_los_hist",
    )
with right:
    chart_card(
        "Discharge destinations",
        "Where patients went after discharge. 'Not recorded' is common in MIMIC, "
        "especially for observation stays, and is shown rather than dropped.",
        charts.category_bar(destinations, "discharge_location", mode=mode),
        dest_table,
        results["discharge_destinations"].sql,
        results["discharge_destinations"].params,
        key="chart_destinations",
    )

# --------------------------------------------------------------------- age groups
ages = present.present_age_groups(results["age_groups"].data)
age_table = pd.DataFrame(
    {
        "Anchor age group": ages["age_group"],
        "Admissions": ages["admissions"].map(fmt.count_cell),
        "Patients": ages["patients"].map(fmt.count_cell),
        "Share of admissions": ages["share_pct"].map(fmt.percent_cell),
        "Median LOS (days)": ages["los_median_days"].map(fmt.days_cell),
    }
)
left, right = st.columns([1, 1], gap="medium")
with left:
    chart_card(
        "Admissions by anchor age group",
        "Anchor age is MIMIC's de-identified age, not necessarily age at admission; "
        "ages above 89 are capped.",
        charts.category_bar(ages, "age_group", mode=mode),
        age_table,
        results["age_groups"].sql,
        results["age_groups"].params,
        key="chart_age",
    )
with right:
    with st.container(border=True):
        st.markdown("**Reading this page**")
        st.markdown(
            f"""
- **Length of stay (LOS)** = discharge time − admission time, in days. A stay is
  *valid* when both timestamps exist and discharge is on or after admission.
- **Mean vs. median:** LOS is right-skewed (a few very long stays), so the mean
  sits above the median. The median is the better "typical stay".
- **Anchor age:** {ANCHOR_AGE_NOTE}
- **Dates are shifted** per patient in MIMIC for de-identification, so this page
  has no calendar-time filter.
- **Privacy:** counts are rounded to the nearest {ROUNDING_BASE}; groups under
  {SMALL_CELL_THRESHOLD} are suppressed or merged into *Other (small groups)*;
  statistics need ≥ {STATISTIC_MIN_N} valid stays. See *Methods & Privacy*.
- **SQL:** every card has an SQL tab with the exact query and parameters.
"""
        )

# ---------------------------------------------------------- comparison table
st.subheader("Admission type comparison", anchor=False)
st.caption(
    "Outcome percentages use admissions **with a recorded discharge destination** as the "
    "denominator; *Discharge recorded* shows how complete that field is. "
    "'Died' = discharge destination recorded as DIED (in-hospital death)."
)
comparison = pd.DataFrame(
    {
        "Admission type": by_type["admission_type"],
        "Admissions": by_type["admissions"].map(fmt.count_cell),
        "Share": by_type["share_pct"].map(fmt.percent_cell),
        "Median LOS (days)": by_type["los_median_days"].map(fmt.days_cell),
        "IQR (days)": [
            fmt.range_cell(lo, hi) for lo, hi in zip(by_type["los_p25_days"], by_type["los_p75_days"])
        ],
        "Mean LOS (days)": by_type["los_mean_days"].map(fmt.days_cell),
        "Discharge recorded": by_type["discharge_recorded_pct"].map(fmt.percent_cell),
        "Home": by_type["home_pct"].map(fmt.percent_cell),
        "Skilled nursing": by_type["snf_pct"].map(fmt.percent_cell),
        "Died": by_type["died_pct"].map(fmt.percent_cell),
    }
)
with st.container(border=True):
    tab_table, tab_sql = st.tabs(["Table", "SQL"])
    with tab_table:
        st.dataframe(comparison, hide_index=True, width="stretch")
    with tab_sql:
        sql_panel(results["by_admission_type"].sql, results["by_admission_type"].params)

# --------------------------------------------------------------------- footer
timings = bundle["timings_ms"]
st.caption(
    f"PostgreSQL time for this filter combination: {max(timings.values()):,.0f} ms "
    "(5 queries run in parallel; repeat views come from cache) · "
    + " · ".join(f"{name.replace('_', ' ')} {ms:,.0f} ms" for name, ms in timings.items())
)
