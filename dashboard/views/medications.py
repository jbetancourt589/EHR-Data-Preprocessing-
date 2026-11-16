"""Page 2 — Medication Analytics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.data import (
    medication_bundle,
    medication_co_ordering,
    medication_drug_context,
    medication_drug_detail,
    medication_drug_options,
    medication_objects_missing,
    medication_population_admissions,
)
from components.ui import chart_card, page_header, sql_panel, stop_with_error, theme_mode
from ehr_analytics.charts import medications as charts
from ehr_analytics.domain import (
    AGE_GROUP_ORDER,
    ANCHOR_AGE_NOTE,
    MEDICATION_ORDER_NOTE,
    MEDICATION_PLACEHOLDERS,
    NOT_RECORDED,
)
from ehr_analytics.filters import MedicationFilters
from ehr_analytics.presenters import formatting as fmt
from ehr_analytics.presenters import medications as present
from ehr_analytics.privacy import (
    OTHER_LABEL,
    ROUNDING_BASE,
    SMALL_CELL_THRESHOLD,
    STATISTIC_MIN_N,
    check_cohort,
)

FILTER_KEYS = ("m_admission_types", "m_age_groups")
MUTED_LABELS = {NOT_RECORDED, OTHER_LABEL}

page_header(
    "Analytics · Page 2",
    "Medication Analytics",
    "Medication orders and stop events across 32.8 million records, aggregated in "
    "PostgreSQL. Orders are prescriptions entered, not confirmed administrations.",
)

# ------------------------------------------------------------------ readiness
try:
    missing = medication_objects_missing()
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

if missing:
    st.info(
        "**Medication summaries have not been built yet.** This page reads small "
        "precomputed summaries instead of scanning 32.8 million rows on every click. "
        "They are created by `sql/analytics/001`–`003` (run once, as postgres).\n\n"
        f"Missing: {', '.join(f'`{m}`' for m in missing)}",
        icon=":material/build:",
    )
    st.stop()


# -------------------------------------------------------------------- filters
def _reset_filters() -> None:
    for key in FILTER_KEYS:
        st.session_state[key] = []
    st.session_state["m_exclude_placeholders"] = True


try:
    unfiltered = medication_bundle((), (), True)
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

utilization_all = unfiltered["results"]["utilization"].data
type_options = sorted(utilization_all.loc[utilization_all["dimension"] == "admission_type", "label"])
age_present = set(utilization_all.loc[utilization_all["dimension"] == "age_group", "label"])
age_options = [g for g in AGE_GROUP_ORDER if g in age_present]

st.session_state.setdefault("m_exclude_placeholders", True)

with st.container(border=True):
    with st.form("medication_filters", border=False, enter_to_submit=False):
        col_type, col_age, col_toggle, col_buttons = st.columns([3, 2.4, 2.6, 1.4], vertical_alignment="bottom")
        col_type.multiselect("Admission type", type_options, key="m_admission_types",
                             placeholder="All admission types")
        col_age.multiselect("Anchor age group", age_options, key="m_age_groups",
                            placeholder="All ages", help=ANCHOR_AGE_NOTE)
        col_toggle.checkbox(
            "Exclude container placeholders",
            key="m_exclude_placeholders",
            help="Removes order-entry names that are not medications ("
            + ", ".join(f"'{p}'" for p in MEDICATION_PLACEHOLDERS[:3])
            + ", 'Click Change…'). They are flagged, never deleted. "
            "Admission-level utilization always excludes them.",
        )
        with col_buttons:
            st.form_submit_button("Apply", type="primary", width="stretch")
            st.form_submit_button("Reset", on_click=_reset_filters, width="stretch")

filters = MedicationFilters.from_selections(
    st.session_state.get("m_admission_types"),
    st.session_state.get("m_age_groups"),
    st.session_state.get("m_exclude_placeholders", True),
)

try:
    with st.spinner("Querying medication summaries…"):
        bundle = medication_bundle(filters.admission_types, filters.age_groups, filters.exclude_placeholders)
        population = medication_population_admissions()
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

results = bundle["results"]
kpi_row = results["kpis"].data.iloc[0]
cohort_admissions = float(kpi_row["admissions"] or 0)

st.caption(
    f"**Cohort:** {filters.describe()}  ·  "
    + ("Container placeholders excluded" if filters.exclude_placeholders else "Container placeholders included")
    + "  ·  "
    + (
        f"Counts rounded to the nearest {ROUNDING_BASE}; groups under {SMALL_CELL_THRESHOLD} suppressed."
        if filters.is_active
        else f"Headline totals exact; breakdown counts rounded to the nearest {ROUNDING_BASE}."
    )
)

cohort = check_cohort(int(cohort_admissions), int(population), filters.is_active)
if not cohort.allowed:
    st.warning(cohort.message, icon=":material/shield_person:")
    st.stop()

mode = theme_mode()

# ----------------------------------------------------------------------- KPIs
kpis = present.present_kpis(kpi_row, exact=not filters.is_active)
# Two rows of three: 8-digit order counts need wider cards than six-across allows.
cols = st.columns(3) + st.columns(3)
cols[0].metric("Medication orders", kpis.orders, border=True,
               help="MED_ORDER events: prescriptions entered (not confirmed administrations).")
cols[1].metric("Stop events", kpis.stops, border=True,
               help=f"MED_STOP events: orders discontinued. {kpis.stop_to_order_pct} as many stops as orders.")
cols[2].metric("Unique medications", kpis.unique_medications, border=True,
               help="Distinct medication names recorded, exactly as written. Different "
               "formulations and spellings count separately (names are never merged).")
cols[3].metric("Admissions with medications", kpis.admissions_with_events, border=True,
               help=f"Admissions with at least one medication order or stop event "
               f"(container placeholders excluded), out of {kpis.cohort_admissions} admissions.")
cols[4].metric("Admissions with ≥1 order", kpis.pct_admissions_with_orders, border=True,
               help="Share of admissions in the cohort with at least one medication order.")
cols[5].metric("Medications per admission", kpis.distinct_meds_per_admission, border=True,
               help="Average number of DISTINCT medication names ordered per admission, "
               "among admissions with at least one order.")

st.info(f"**Orders vs. stops.** {MEDICATION_ORDER_NOTE}", icon=":material/medication:")

# ------------------------------------------------------------------ top lists
by_orders, by_admissions = present.present_top_medications(results["top_medications"].data, cohort_admissions)


def _top_table(df: pd.DataFrame, rank_col: str) -> pd.DataFrame:
    return pd.DataFrame({
        "Rank": df[rank_col].astype(int),
        "Medication (as recorded)": df["drug"] + df["is_placeholder"].map({True: "  [placeholder]", False: ""}),
        "Orders": df["orders"].map(fmt.count_cell),
        "Stop events": df["stops"].map(fmt.count_cell),
        "Admissions ordering": df["admissions_ordered"].map(fmt.count_cell),
        "% of cohort admissions": df["share_pct"].map(fmt.percent_cell),
        "Orders per admission": df["orders_per_admission"].map(fmt.days_cell),
    })


top_hover = (("share_pct", "% of cohort admissions", ".1f"), ("orders_per_admission", "Orders per admission", ".1f"))
left, right = st.columns(2, gap="medium")
with left:
    chart_card(
        "Top 20 medications by orders",
        "Total MED_ORDER events. Repeated orders in one admission each count. "
        "Gray = container placeholder.",
        charts.ranked_bar(by_orders, "drug", "orders", value_title="Orders", mode=mode,
                          muted=by_orders.get("is_placeholder", []), hover_fields=top_hover),
        _top_table(by_orders, "rank_by_orders"),
        results["top_medications"].sql, results["top_medications"].params,
        key="med_top_orders",
    )
with right:
    chart_card(
        "Top 20 medications by distinct admissions",
        "Number of admissions with at least one order of the drug — how widely it is used, "
        "rather than how often it is re-ordered.",
        charts.ranked_bar(by_admissions, "drug", "admissions_ordered", value_title="Admissions ordering",
                          mode=mode, muted=by_admissions.get("is_placeholder", []), hover_fields=top_hover),
        _top_table(by_admissions, "rank_by_admissions"),
        results["top_medications"].sql, results["top_medications"].params,
        key="med_top_admissions",
    )

# -------------------------------------------------------------- orders vs stops
top15 = by_orders.head(15)
left, right = st.columns([3, 2], gap="medium")
with left:
    chart_card(
        "Orders vs. stop events — top 15 by orders",
        "Blue = orders, orange = stop events. A stop count close to the order count means "
        "most orders were explicitly discontinued during the stay.",
        charts.orders_vs_stops(top15, mode=mode),
        pd.DataFrame({
            "Medication": top15["drug"],
            "Orders": top15["orders"].map(fmt.count_cell),
            "Stop events": top15["stops"].map(fmt.count_cell),
            "Stops as % of orders": top15["stop_pct"].map(lambda v: fmt.percent_cell(v, 0)),
        }),
        results["top_medications"].sql, results["top_medications"].params,
        key="med_orders_stops",
    )
with right:
    with st.container(border=True):
        st.markdown("**What orders and stops represent**")
        st.markdown(
            f"""
- **Order (MED_ORDER):** a prescription entered in the record, with dose and route.
  It shows *intent to treat*, not that a dose was administered.
- **Stop (MED_STOP):** the order was discontinued. Stops carry no dose or route.
- **Pairing:** in a sample of admissions, ~89% of admission–drug combinations had
  exactly as many stops as orders. Fewer stops than orders usually means an order
  was still active at discharge.
- **Repeated orders:** re-ordering the same drug in one stay (e.g. sliding-scale
  insulin) adds orders but not admissions, which is why the two top-20 lists differ.
- **Cohort stop-to-order ratio:** {kpis.stop_to_order_pct}.
"""
        )

# ------------------------------------------------------------------ utilization
st.subheader("Medication utilization", anchor=False)
measure = st.segmented_control(
    "Measure",
    ["Medications per admission", "Orders per admission", "% of admissions with ≥1 order"],
    default="Medications per admission",
    key="m_util_measure",
    label_visibility="collapsed",
) or "Medications per admission"
measure_col, measure_fmt, measure_suffix = {
    "Medications per admission": ("distinct_per_admission", ".1f", ""),
    "Orders per admission": ("orders_per_admission", ".1f", ""),
    "% of admissions with ≥1 order": ("pct_with_orders", ".1f", "%"),
}[measure]
st.caption(
    "Per-admission averages use admissions with at least one order as the denominator and "
    f"need ≥ {STATISTIC_MIN_N} such admissions. Container placeholders are never counted here."
)


def _util_table(df: pd.DataFrame, label: str) -> pd.DataFrame:
    return pd.DataFrame({
        label: df["label"],
        "Admissions": df["admissions_shown"].map(fmt.count_cell),
        "With ≥1 order": df["pct_with_orders"].map(fmt.percent_cell),
        "Medications / admission": df["distinct_per_admission"].map(fmt.days_cell),
        "Orders / admission": df["orders_per_admission"].map(fmt.days_cell),
    })


util_age = present.present_utilization(results["utilization"].data, "age_group")
util_type = present.present_utilization(results["utilization"].data, "admission_type")
left, right = st.columns(2, gap="medium")
for column, data, title, label, key in (
    (left, util_age, "By anchor age group", "Anchor age group", "med_util_age"),
    (right, util_type, "By admission type", "Admission type", "med_util_type"),
):
    with column:
        chart_card(
            f"{measure} — {title.lower()}",
            "Gray = not recorded or merged small groups.",
            charts.ranked_bar(data, "label", measure_col, value_title=measure, mode=mode,
                              muted=data["label"].isin(MUTED_LABELS) if not data.empty else None,
                              value_format=measure_fmt, tick_suffix=measure_suffix),
            _util_table(data, label),
            results["utilization"].sql, results["utilization"].params,
            key=key,
        )

opa = present.present_orders_per_admission(results["orders_per_admission"].data)
left, right = st.columns([3, 2], gap="medium")
with left:
    chart_card(
        "Medication orders per admission",
        "Distribution of admissions by their total number of medication orders "
        "(placeholders excluded). '0' includes admissions with no medication records.",
        charts.ordinal_columns(opa, "label", "admissions", value_title="Admissions",
                               x_title="Medication orders in the admission", mode=mode),
        pd.DataFrame({
            "Orders in admission": opa["label"],
            "Admissions": opa["admissions"].map(fmt.count_cell),
            "Share": opa["share_pct"].map(fmt.percent_cell),
        }),
        results["orders_per_admission"].sql, results["orders_per_admission"].params,
        key="med_orders_per_admission",
    )
with right:
    with st.container(border=True):
        st.markdown("**How medication names are handled**")
        st.markdown(
            """
- Names are shown **exactly as recorded**. Different formulations
  ("0.9% Sodium Chloride" vs. "Sodium Chloride 0.9%  Flush") and products
  ("Insulin" vs. "Insulin Glargine") are **never merged**.
- `*Nf*` marks a **non-formulary** item (e.g. "*Nf* Warfarin"). It is kept
  separate from the formulary drug.
- The explorer lists **related spellings** side by side (same name after
  ignoring case, punctuation and the `*Nf*` marker) so you can compare them.
- Container placeholders (Bag, Vial, Syringe, Click Change…) are flagged and
  excluded by default; untick the filter option to include them.
"""
        )

# -------------------------------------------------------------------- explorer
st.subheader("Medication explorer", anchor=False)
st.caption(
    "Type to search. Only names recorded in at least "
    f"{SMALL_CELL_THRESHOLD} admissions are listed. Cohort statistics follow the filters above; "
    "routes, related names and co-ordered drugs cover all admissions."
)
try:
    options_result = medication_drug_options()
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)
options_df = options_result.data
if filters.exclude_placeholders:
    # .loc + explicit bool: an EMPTY object-dtype mask would otherwise be read
    # by pandas as a list of column names and drop every column.
    options_df = options_df.loc[~options_df["is_placeholder"].astype(bool)]
drug_names = options_df["drug"].tolist()

if not drug_names:
    st.info("No medications meet the minimum-admissions rule.")
else:
    if st.session_state.get("m_drug") not in drug_names:
        st.session_state["m_drug"] = drug_names[0]
    drug = st.selectbox(
        "Medication",
        drug_names,
        key="m_drug",
        help="Ordered by number of admissions ordering the drug. Type to filter the list.",
    )
    try:
        detail_result = medication_drug_detail(
            drug, filters.admission_types, filters.age_groups, filters.exclude_placeholders
        )
        context = medication_drug_context(drug)["results"]
    except Exception as exc:  # noqa: BLE001
        stop_with_error(exc)

    view = present.present_drug_detail(detail_result.data, results["utilization"].data, cohort_admissions)
    if not view.allowed:
        st.warning(view.message, icon=":material/shield_person:")
    else:
        s = view.total
        m = st.columns(5)
        m[0].metric("Orders", fmt.count_cell(s["orders"]), border=True)
        m[1].metric("Stop events", fmt.count_cell(s["stops"]), border=True)
        m[2].metric("Admissions ordering", fmt.count_cell(s["admissions_ordered"]), border=True)
        m[3].metric("% of cohort admissions", fmt.percent_cell(s["pct_of_cohort"]), border=True)
        m[4].metric("Orders per admission", fmt.days_cell(s["orders_per_admission"]), border=True,
                    help="Among admissions with at least one order of this drug.")

        breakdown_hover = (("pct_of_group", "% of group's admissions", ".1f"),)

        def _breakdown_table(df: pd.DataFrame, label: str) -> pd.DataFrame:
            return pd.DataFrame({
                label: df["label"],
                "Admissions ordering": df["admissions_ordered_shown"].map(fmt.count_cell),
                "% of group's admissions": df["pct_of_group"].map(fmt.percent_cell),
                "Orders": df["orders_shown"].map(fmt.count_cell),
            })

        left, right = st.columns(2, gap="medium")
        with left:
            chart_card(
                f"{drug} — by anchor age group",
                "Share of each age group's admissions that ordered this drug.",
                charts.ranked_bar(view.by_age, "label", "pct_of_group", value_title="% of group's admissions",
                                  mode=mode, muted=view.by_age["label"].isin(MUTED_LABELS) if not view.by_age.empty else None,
                                  value_format=".1f", tick_suffix="%"),
                _breakdown_table(view.by_age, "Anchor age group"),
                detail_result.sql, detail_result.params, key="med_drug_age",
            )
        with right:
            chart_card(
                f"{drug} — by admission type",
                "Share of each admission type's admissions that ordered this drug.",
                charts.ranked_bar(view.by_type, "label", "pct_of_group", value_title="% of group's admissions",
                                  mode=mode, muted=view.by_type["label"].isin(MUTED_LABELS) if not view.by_type.empty else None,
                                  value_format=".1f", tick_suffix="%"),
                _breakdown_table(view.by_type, "Admission type"),
                detail_result.sql, detail_result.params, key="med_drug_type",
            )

        routes = present.present_routes(context["routes"].data)
        partners = present.present_partners(context["partners"].data)
        left, right = st.columns(2, gap="medium")
        with left:
            chart_card(
                f"{drug} — routes (all admissions)",
                "Route recorded on each order (stop events have no route). "
                "Routes used in fewer than 11 admissions are merged.",
                charts.ranked_bar(routes, "route", "orders", value_title="Orders", mode=mode,
                                  muted=routes["route"].isin(MUTED_LABELS) if not routes.empty else None,
                                  hover_fields=(("share_pct", "Share of orders %", ".1f"),)),
                pd.DataFrame({
                    "Route": routes.get("route", []),
                    "Orders": routes.get("orders", pd.Series(dtype=float)).map(fmt.count_cell),
                    "Admissions": routes.get("admissions", pd.Series(dtype=float)).map(fmt.count_cell),
                    "Share of orders": routes.get("share_pct", pd.Series(dtype=float)).map(fmt.percent_cell),
                }),
                context["routes"].sql, context["routes"].params, key="med_drug_routes",
            )
        with right:
            chart_card(
                f"Most often co-ordered with {drug}",
                "Of admissions that ordered this drug, the share that also ordered each partner "
                "(top 100 most widely ordered drugs; all admissions).",
                charts.ranked_bar(partners, "partner", "pct_with_partner",
                                  value_title=f"% of {drug} admissions", mode=mode,
                                  value_format=".1f", tick_suffix="%",
                                  hover_fields=(("lift", "Lift", ".2f"), ("admissions_both", "Admissions together", ",.0f"))),
                pd.DataFrame({
                    "Co-ordered medication": partners.get("partner", []),
                    "Admissions together": partners.get("admissions_both", pd.Series(dtype=float)).map(fmt.count_cell),
                    f"% of {drug} admissions": partners.get("pct_with_partner", pd.Series(dtype=float)).map(fmt.percent_cell),
                    "Lift": partners.get("lift", pd.Series(dtype=float)).map(lambda v: "n/a" if pd.isna(v) else f"{v:.2f}"),
                }),
                context["partners"].sql, context["partners"].params, key="med_drug_partners",
            )

        variants = present.present_variants(context["variants"].data)
        left, right = st.columns([3, 2], gap="medium")
        with left:
            with st.container(border=True):
                st.markdown(f"**Related names for {drug}** — shown for comparison, never merged")
                if variants.empty:
                    st.caption("No related names recorded in at least 11 admissions.")
                else:
                    st.dataframe(pd.DataFrame({
                        "Recorded name": variants["drug"],
                        "Relation": variants["match_type"].map({
                            "same_name": "Same name, different spelling/marker",
                            "contains_name": "Contains this name (different product?)",
                        }),
                        "Non-formulary": variants["is_non_formulary"].map({True: "Yes", False: ""}),
                        "Orders": variants["orders"].map(fmt.count_cell),
                        "Admissions": variants["admissions_any"].map(fmt.count_cell),
                    }), hide_index=True, width="stretch")
                with st.expander("SQL"):
                    sql_panel(context["variants"].sql, context["variants"].params)
        with right:
            chart_card(
                f"{drug} — orders per admission",
                "Among admissions that ordered this drug, how many times it was ordered.",
                charts.ordinal_columns(view.distribution, "label", "admissions", value_title="Admissions",
                                       x_title="Orders of this drug in the admission", mode=mode),
                pd.DataFrame({
                    "Orders in admission": view.distribution["label"],
                    "Admissions": view.distribution["admissions"].map(fmt.count_cell),
                    "Share": view.distribution["share_pct"].map(fmt.percent_cell),
                }),
                detail_result.sql, detail_result.params, key="med_drug_distribution",
            )

# ----------------------------------------------------------------- co-ordering
st.subheader("Medication co-ordering", anchor=False)
st.caption(
    "Which medications are ordered in the same admission (at any point during the stay, not "
    "necessarily simultaneously). Covers the 100 most widely ordered medications across all "
    "admissions; not affected by the filters. Pairs shared by fewer than 11 admissions are hidden."
)
try:
    co = medication_co_ordering()["results"]
except Exception as exc:  # noqa: BLE001
    stop_with_error(exc)

matrix = present.present_co_ordering_matrix(co["matrix"].data)
pairs = present.present_top_pairs(co["pairs"].data)
chart_card(
    "Co-ordering matrix — 12 most widely ordered medications",
    "Read across a row: of admissions that ordered the row medication, the % that also ordered "
    "the column medication. The matrix is not symmetric.",
    charts.co_ordering_heatmap(matrix, mode=mode),
    matrix.round(1).reset_index().rename(columns={"row_drug": "Row medication"}) if not matrix.empty else pd.DataFrame(),
    co["matrix"].sql, co["matrix"].params, key="med_co_matrix",
)

with st.container(border=True):
    st.markdown("**Most frequent co-ordered pairs**")
    st.caption(
        "Lift > 1 means the pair is ordered together more often than expected if the two were "
        "independent. High counts with lift near 1 are usually just two very common drugs "
        "(e.g. IV fluids); high lift points to drugs used together by design."
    )
    tab_table, tab_sql = st.tabs(["Table", "SQL"])
    with tab_table:
        st.dataframe(pd.DataFrame({
            "Medication A": pairs.get("drug_a", []),
            "Medication B": pairs.get("drug_b", []),
            "Admissions together": pairs.get("admissions_both", pd.Series(dtype=float)).map(fmt.count_cell),
            "% of A with B": pairs.get("pct_a_with_b", pd.Series(dtype=float)).map(fmt.percent_cell),
            "% of B with A": pairs.get("pct_b_with_a", pd.Series(dtype=float)).map(fmt.percent_cell),
            "Lift": pairs.get("lift", pd.Series(dtype=float)).map(lambda v: "n/a" if pd.isna(v) else f"{v:.2f}"),
        }), hide_index=True, width="stretch")
    with tab_sql:
        sql_panel(co["pairs"].sql, co["pairs"].params)

# --------------------------------------------------------------------- footer
timings = bundle["timings_ms"]
st.caption(
    f"PostgreSQL time for this filter combination: {max(timings.values()):,.0f} ms "
    "(queries run in parallel on precomputed summaries; repeat views come from cache) · "
    + " · ".join(f"{name.replace('_', ' ')} {ms:,.0f} ms" for name, ms in timings.items())
)
