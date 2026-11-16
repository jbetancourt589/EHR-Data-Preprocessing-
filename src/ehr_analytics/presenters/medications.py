"""Medication Analytics presenter: raw summary rows -> privacy-protected views.

Privacy unit: ADMISSIONS (patients' hospital stays). Order and stop counts are
event counts, but a small event count can still describe a small number of
admissions, so they are suppressed and rounded the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from ehr_analytics.domain import AGE_GROUP_ORDER, NOT_RECORDED, ORDERS_BUCKET_LABELS
from ehr_analytics.privacy import (
    OTHER_LABEL,
    SMALL_CELL_THRESHOLD,
    format_count,
    is_small,
    protect_categories,
    protect_count_column,
    round_count,
    safe_percent,
    statistic_allowed,
)


def _rounded(n: float | None) -> float:
    """Round a count for display; NaN if it must be suppressed."""
    if n is None or pd.isna(n) or is_small(n):
        return float("nan")
    return float(round_count(n))


def _ratio(numerator: float, denominator: float) -> float:
    """A per-admission rate, shown only when the denominator is large enough."""
    if not statistic_allowed(denominator) or pd.isna(numerator):
        return float("nan")
    return float(numerator) / float(denominator)


# --------------------------------------------------------------------------- KPIs
@dataclass(frozen=True)
class MedicationKpiView:
    orders: str
    stops: str
    unique_medications: str
    admissions_with_events: str
    pct_admissions_with_orders: str
    distinct_meds_per_admission: str
    stop_to_order_pct: str
    cohort_admissions: str
    exact: bool


def present_kpis(row: Mapping[str, float], *, exact: bool) -> MedicationKpiView:
    """Headline numbers. Exact only for the unfiltered whole-database view."""
    admissions = float(row["admissions"] or 0)
    with_orders = float(row["admissions_with_orders"] or 0)
    with_orders_shown = with_orders if exact else _rounded(with_orders)
    admissions_shown = admissions if exact else _rounded(admissions)
    pct = safe_percent(with_orders_shown, admissions_shown)
    per_admission = _ratio(row["distinct_drug_orders"], with_orders)
    orders = float(row["orders"] or 0)
    stop_pct = safe_percent(float(row["stops"] or 0), orders) if statistic_allowed(orders) else float("nan")
    return MedicationKpiView(
        orders=format_count(orders, exact=exact),
        stops=format_count(row["stops"], exact=exact),
        # A count of distinct NAMES (not people): shown exactly.
        unique_medications=f"{int(row['unique_medications']):,}",
        admissions_with_events=format_count(row["admissions_with_events"], exact=exact),
        pct_admissions_with_orders="—" if pd.isna(pct) else f"{pct:.1f}%",
        distinct_meds_per_admission="—" if pd.isna(per_admission) else f"{per_admission:.1f}",
        stop_to_order_pct="—" if pd.isna(stop_pct) else f"{stop_pct:.0f}%",
        cohort_admissions=format_count(admissions, exact=exact),
        exact=exact,
    )


# ------------------------------------------------------------------ top lists
def _protect_drug_rows(df: pd.DataFrame, cohort_admissions: float) -> pd.DataFrame:
    """Round counts, suppress small stop counts, add shares and stop ratio."""
    out = df.copy()
    cohort_shown = round_count(cohort_admissions) if cohort_admissions else float("nan")
    for col in ("orders", "admissions_ordered", "admissions_any"):
        out[col] = out[col].map(_rounded)
    out["stops"] = protect_count_column(out["stops"])
    out["share_pct"] = [safe_percent(a, cohort_shown) for a in out["admissions_ordered"]]
    out["stop_pct"] = [safe_percent(s, o) for s, o in zip(out["stops"], out["orders"])]
    out["orders_per_admission"] = [
        (o / a) if (pd.notna(o) and pd.notna(a) and a > 0) else float("nan")
        for o, a in zip(out["orders"], out["admissions_ordered"])
    ]
    return out


def present_top_medications(
    df: pd.DataFrame, cohort_admissions: float, top_n: int = 20
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the ranked query result into (top by orders, top by admissions).

    Empty input (no drug meets the minimum) still gets every derived column,
    so the page can render empty tables.
    """
    protected = _protect_drug_rows(df, cohort_admissions)
    by_orders = protected[protected["rank_by_orders"] <= top_n].sort_values("rank_by_orders")
    by_admissions = protected[protected["rank_by_admissions"] <= top_n].sort_values("rank_by_admissions")
    return by_orders.reset_index(drop=True), by_admissions.reset_index(drop=True)


# ---------------------------------------------------------------- utilization
UTILIZATION_ADDITIVE = ("admissions_with_orders", "orders", "stops", "distinct_drug_orders")


def present_utilization(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """One dimension ('age_group' or 'admission_type') of the utilization query.

    Small groups merge into Other; rates are computed from summed raw counts
    and shown only when at least STATISTIC_MIN_N admissions had orders.
    """
    part = df[df["dimension"] == dimension].drop(columns="dimension").reset_index(drop=True)
    if part.empty:
        return part.assign(is_other=pd.Series(dtype=bool))
    merged = protect_categories(part, "label", "admissions", additive_cols=UTILIZATION_ADDITIVE)
    merged["pct_with_orders"] = [
        safe_percent(round_count(w), round_count(a)) if statistic_allowed(a) and pd.notna(w) else float("nan")
        for w, a in zip(merged["admissions_with_orders"], merged["admissions"])
    ]
    merged["orders_per_admission"] = [
        _ratio(o, w) for o, w in zip(merged["orders"], merged["admissions_with_orders"])
    ]
    merged["distinct_per_admission"] = [
        _ratio(d, w) for d, w in zip(merged["distinct_drug_orders"], merged["admissions_with_orders"])
    ]
    merged["admissions_shown"] = merged["admissions"].map(_rounded)
    merged["admissions_with_orders_shown"] = merged["admissions_with_orders"].map(_rounded)

    if dimension == "age_group":
        rank = {label: i for i, label in enumerate(AGE_GROUP_ORDER)}
        merged["_rank"] = merged["label"].map(lambda x: rank.get(x, 98))
    else:
        merged["_rank"] = -merged["admissions"].fillna(0)
        merged.loc[merged["label"] == NOT_RECORDED, "_rank"] = 1e12
    merged.loc[merged["is_other"], "_rank"] = 1e13
    return merged.sort_values("_rank").drop(columns="_rank").reset_index(drop=True)


def present_orders_per_admission(df: pd.DataFrame) -> pd.DataFrame:
    """All seven bands in order, suppressed and rounded, with shares."""
    counts = df.set_index("orders_bucket")["admissions"] if not df.empty else pd.Series(dtype=float)
    out = pd.DataFrame({"orders_bucket": list(ORDERS_BUCKET_LABELS)})
    out["label"] = out["orders_bucket"].map(ORDERS_BUCKET_LABELS)
    raw = out["orders_bucket"].map(counts).fillna(0)
    out["admissions"] = protect_count_column(raw)
    total = round_count(raw.sum())
    out["share_pct"] = [safe_percent(a, total) for a in out["admissions"]]
    return out


# ------------------------------------------------------------------ explorer
@dataclass(frozen=True)
class DrugView:
    allowed: bool
    message: str
    total: dict
    by_age: pd.DataFrame
    by_type: pd.DataFrame
    distribution: pd.DataFrame


def _drug_breakdown(rows: pd.DataFrame, denominators: pd.DataFrame, order: list[str] | None) -> pd.DataFrame:
    """Per-group admissions ordering the drug, with % of that group's admissions."""
    if rows.empty:
        return rows.assign(is_other=pd.Series(dtype=bool), pct_of_group=pd.Series(dtype=float))
    merged = protect_categories(
        rows.drop(columns="dimension"), "label", "admissions_ordered",
        additive_cols=("orders", "stops", "admissions_any"),
    )
    group_admissions = denominators.set_index("label")["admissions"] if not denominators.empty else pd.Series()
    other_denominator = group_admissions[~group_admissions.index.isin(merged["label"])].sum()
    merged["group_admissions"] = [
        other_denominator if is_other else group_admissions.get(label, float("nan"))
        for label, is_other in zip(merged["label"], merged["is_other"])
    ]
    merged["admissions_ordered_shown"] = merged["admissions_ordered"].map(_rounded)
    merged["orders_shown"] = merged["orders"].map(_rounded)
    merged["pct_of_group"] = [
        safe_percent(a, round_count(g)) if pd.notna(g) and g > 0 else float("nan")
        for a, g in zip(merged["admissions_ordered_shown"], merged["group_admissions"])
    ]
    if order is not None:
        rank = {label: i for i, label in enumerate(order)}
        merged["_rank"] = merged["label"].map(lambda x: rank.get(x, 98))
    else:
        merged["_rank"] = -merged["admissions_ordered"].fillna(0)
    merged.loc[merged["is_other"], "_rank"] = 1e13
    return merged.sort_values("_rank").drop(columns="_rank").reset_index(drop=True)


def present_drug_detail(detail: pd.DataFrame, utilization: pd.DataFrame, cohort_admissions: float) -> DrugView:
    """Explorer statistics for one drug within the filtered cohort."""
    total_rows = detail[detail["dimension"] == "total"]
    if total_rows.empty or total_rows.iloc[0]["admissions_any"] is None or pd.isna(total_rows.iloc[0]["admissions_any"]):
        return DrugView(False, "This medication has no records in the selected cohort.", {},
                        pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    total = total_rows.iloc[0]
    if total["admissions_any"] < SMALL_CELL_THRESHOLD:
        return DrugView(
            False,
            f"This medication was recorded in fewer than {SMALL_CELL_THRESHOLD} admissions in the "
            "selected cohort, so its statistics are hidden. Broaden the filters.",
            {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        )
    admissions_ordered = _rounded(total["admissions_ordered"])
    orders = _rounded(total["orders"])
    summary = {
        "orders": orders,
        "stops": _rounded(total["stops"]),
        "admissions_ordered": admissions_ordered,
        "pct_of_cohort": safe_percent(admissions_ordered, round_count(cohort_admissions)),
        "orders_per_admission": _ratio(total["orders"], total["admissions_ordered"]),
        "stop_pct": safe_percent(total["stops"], total["orders"]) if statistic_allowed(total["orders"]) else float("nan"),
    }
    distribution = pd.DataFrame({
        "label": ["1 order", "2 orders", "3–5 orders", "6+ orders"],
        "raw": [total["adm_orders_1"], total["adm_orders_2"], total["adm_orders_3_5"], total["adm_orders_6_plus"]],
    })
    distribution["admissions"] = protect_count_column(distribution["raw"].astype(float))
    distribution["share_pct"] = [safe_percent(a, admissions_ordered) for a in distribution["admissions"]]
    distribution = distribution.drop(columns="raw")

    age_denominators = utilization[utilization["dimension"] == "age_group"]
    type_denominators = utilization[utilization["dimension"] == "admission_type"]
    return DrugView(
        True, "", summary,
        _drug_breakdown(detail[detail["dimension"] == "age_group"], age_denominators, list(AGE_GROUP_ORDER)),
        _drug_breakdown(detail[detail["dimension"] == "admission_type"], type_denominators, None),
        distribution,
    )


def present_routes(df: pd.DataFrame) -> pd.DataFrame:
    """Routes for one drug; routes used in fewer than 11 admissions merge into Other."""
    if df.empty:
        return df.assign(is_other=pd.Series(dtype=bool), share_pct=pd.Series(dtype=float))
    merged = protect_categories(df, "route", "admissions", additive_cols=("orders",))
    total_orders = round_count(df["orders"].sum())
    merged["orders"] = merged["orders"].map(_rounded)
    merged["admissions"] = merged["admissions"].map(_rounded)
    merged["share_pct"] = [safe_percent(o, total_orders) for o in merged["orders"]]
    merged["_rank"] = -merged["orders"].fillna(0)
    merged.loc[merged["is_other"], "_rank"] = 1
    return merged.sort_values("_rank").drop(columns="_rank").reset_index(drop=True)


def present_variants(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("orders", "admissions_any"):
        out[col] = out[col].map(_rounded)
    return out


def present_partners(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["admissions_both"] = out["admissions_both"].map(_rounded)
    out["partner_admissions"] = out["partner_admissions"].map(_rounded)
    out["pct_with_partner"] = out["pct_with_partner"] * 100
    return out


def present_top_pairs(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("admissions_both", "admissions_a", "admissions_b"):
        out[col] = out[col].map(_rounded)
    out["pct_a_with_b"] = out["pct_a_with_b"] * 100
    out["pct_b_with_a"] = out["pct_b_with_a"] * 100
    return out


def present_co_ordering_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot to a square % matrix; cells under 11 shared admissions are blank."""
    if df.empty:
        return pd.DataFrame()
    data = df.copy()
    data["pct"] = [
        float("nan") if is_small(n) else p * 100 for p, n in zip(data["pct"], data["admissions_both"])
    ]
    order = (
        data[["row_drug", "row_admissions"]].drop_duplicates()
        .sort_values(["row_admissions", "row_drug"], ascending=[False, True])["row_drug"].tolist()
    )
    matrix = data.pivot(index="row_drug", columns="col_drug", values="pct")
    return matrix.reindex(index=order, columns=order)


__all__ = [
    "OTHER_LABEL",
    "MedicationKpiView",
    "DrugView",
    "present_kpis",
    "present_top_medications",
    "present_utilization",
    "present_orders_per_admission",
    "present_drug_detail",
    "present_routes",
    "present_variants",
    "present_partners",
    "present_top_pairs",
    "present_co_ordering_matrix",
]
