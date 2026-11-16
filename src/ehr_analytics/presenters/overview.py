"""Hospital Overview presenter: raw query results -> privacy-protected views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from ehr_analytics.domain import AGE_GROUP_ORDER, LOS_HISTOGRAM_CAP_DAYS, NOT_RECORDED
from ehr_analytics.privacy import (
    OTHER_LABEL,
    SUPPRESSED_TEXT,
    is_small,
    protect_categories,
    protect_count_column,
    round_count,
    round_or_nan,
    safe_percent,
    statistic_allowed,
    suppression_mask,
)

LOS_STAT_COLUMNS = (
    "los_mean_days",
    "los_p10_days",
    "los_p25_days",
    "los_median_days",
    "los_p75_days",
    "los_p90_days",
)


# --------------------------------------------------------------------------- KPIs
@dataclass(frozen=True)
class KpiView:
    """Display-ready headline metrics. All values are already-formatted strings."""

    patients: str
    admissions: str
    los_valid: str
    los_valid_pct: str
    excluded: str
    excluded_missing: str
    excluded_negative: str
    los_mean: str
    los_median: str
    los_iqr: str
    exact: bool


def _fmt_days(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:.1f} days"


def present_kpis(row: Mapping[str, float], *, exact: bool) -> KpiView:
    """Format the one-row KPI result.

    `exact=True` is only used for the unfiltered, whole-database view; any
    filtered cohort is rounded (privacy rule 3).
    """

    def count(n: float) -> float:
        return float(n) if exact else float(round_count(n))

    admissions = float(row["admissions"])
    parts = [row["los_valid_n"], row["los_missing_n"], row["los_negative_n"]]
    # valid + missing + negative == admissions. With EXACT counts a hidden cell
    # could be recovered by subtraction, so complementary suppression applies.
    # Rounded counts each carry up to ±2 rounding error, so subtraction cannot
    # recover a hidden cell exactly; only primary suppression is needed (and it
    # avoids hiding the main "valid stays" figure of a large cohort).
    hidden = suppression_mask(parts) if exact else [is_small(v) for v in parts]
    valid, missing, negative = (
        None if h else count(v) for v, h in zip(parts, hidden)
    )

    def show(n: float | None) -> str:
        return SUPPRESSED_TEXT if n is None else f"{n:,.0f}"

    # The total excluded is hidden if it is itself small, or (exact mode) if
    # exactly one of its two parts is hidden: total minus the visible part
    # would reveal the other.
    excluded_raw = row["los_missing_n"] + row["los_negative_n"]
    excluded = (
        None
        if is_small(excluded_raw) or (exact and hidden[1] != hidden[2])
        else count(excluded_raw)
    )
    stats_ok = statistic_allowed(row["los_valid_n"])
    admissions_shown = count(admissions)

    return KpiView(
        patients=f"{count(row['patients']):,.0f}",
        admissions=f"{admissions_shown:,.0f}",
        los_valid=show(valid),
        los_valid_pct=(
            "—" if valid is None
            else f"{safe_percent(valid, admissions_shown):.2f}%" if exact
            # rounded counts: show an approximate share, not false precision
            else f"≈{safe_percent(valid, admissions_shown):.1f}%"
        ),
        excluded=show(excluded),
        excluded_missing=show(missing),
        excluded_negative=show(negative),
        los_mean=_fmt_days(row["los_mean_days"]) if stats_ok else "—",
        los_median=_fmt_days(row["los_median_days"]) if stats_ok else "—",
        los_iqr=(
            f"IQR {row['los_p25_days']:.1f}–{row['los_p75_days']:.1f} days" if stats_ok else ""
        ),
        exact=exact,
    )


# ------------------------------------------------------------- category breakdowns
def _blank_small_statistics(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Hide group statistics for the Other row and for groups with too few stays."""
    out = df.copy()
    blocked = out["is_other"] | ~out["los_valid_n"].apply(statistic_allowed)
    for col in columns:
        if col in out.columns:
            out[col] = out[col].astype("float64").where(~blocked)
    return out


def _order_rows(df: pd.DataFrame, label_col: str, order: Sequence[str] | None) -> pd.DataFrame:
    """Order by `order` if given, else by size; 'Not recorded' and Other go last."""
    out = df.copy()
    if order is not None:
        rank = {label: i for i, label in enumerate(order)}
        out["_rank"] = out[label_col].map(lambda x: rank.get(x, len(rank) + 1))
    else:
        out["_rank"] = 0
        out.loc[out[label_col] == NOT_RECORDED, "_rank"] = 1
    out.loc[out["is_other"], "_rank"] = len(out) + 100
    out = out.sort_values(["_rank", "admissions"], ascending=[True, False], kind="stable")
    return out.drop(columns="_rank").reset_index(drop=True)


def present_distribution(
    df: pd.DataFrame,
    label_col: str,
    *,
    order: Sequence[str] | None = None,
    extra_count_cols: Sequence[str] = (),
) -> pd.DataFrame:
    """Protect a one-dimension breakdown (admissions per category).

    Returns columns: label_col, admissions (rounded), share_pct, los_valid_n,
    los_median_days (NaN where not allowed), is_other, plus extra_count_cols
    (e.g. patients), each protected independently.
    """
    if df.empty:
        return df.assign(is_other=pd.Series(dtype=bool), share_pct=pd.Series(dtype=float))
    merged = protect_categories(
        df, label_col, "admissions", additive_cols=["los_valid_n", *extra_count_cols]
    )
    merged = _blank_small_statistics(merged, LOS_STAT_COLUMNS)
    total_shown = round_count(df["admissions"].sum())
    merged["admissions"] = merged["admissions"].map(round_or_nan)
    merged["share_pct"] = merged["admissions"].map(lambda n: safe_percent(n, total_shown))
    for col in extra_count_cols:
        merged[col] = protect_count_column(merged[col])
    return _order_rows(merged, label_col, order)


def present_age_groups(df: pd.DataFrame) -> pd.DataFrame:
    return present_distribution(df, "age_group", order=AGE_GROUP_ORDER, extra_count_cols=["patients"])


def present_discharge_destinations(df: pd.DataFrame) -> pd.DataFrame:
    return present_distribution(df, "discharge_location")


OUTCOME_COLUMNS = ("discharged_home_n", "discharged_snf_n", "died_n")


def present_by_admission_type(df: pd.DataFrame) -> pd.DataFrame:
    """Protect the admission-type comparison (bars, box plot, and table)."""
    if df.empty:
        return df.assign(is_other=pd.Series(dtype=bool), share_pct=pd.Series(dtype=float))
    count_cols = ["los_valid_n", "discharge_recorded_n", *OUTCOME_COLUMNS]
    merged = protect_categories(df, "admission_type", "admissions", additive_cols=count_cols)
    merged = _blank_small_statistics(merged, LOS_STAT_COLUMNS)
    total_shown = round_count(df["admissions"].sum())

    merged["admissions"] = merged["admissions"].map(round_or_nan)
    merged["share_pct"] = merged["admissions"].map(lambda n: safe_percent(n, total_shown))
    # Each outcome column has a knowable total (it appears in the discharge
    # chart), so each column gets its own complementary suppression.
    for col in ("discharge_recorded_n", *OUTCOME_COLUMNS):
        merged[col] = protect_count_column(merged[col])

    merged["discharge_recorded_pct"] = [
        safe_percent(r, a) for r, a in zip(merged["discharge_recorded_n"], merged["admissions"])
    ]
    for col, pct_col in (
        ("discharged_home_n", "home_pct"),
        ("discharged_snf_n", "snf_pct"),
        ("died_n", "died_pct"),
    ):
        merged[pct_col] = [
            safe_percent(n, d) for n, d in zip(merged[col], merged["discharge_recorded_n"])
        ]
    return _order_rows(merged, "admission_type", None)


# ---------------------------------------------------------------------- histogram
def present_los_histogram(df: pd.DataFrame, cap: int = LOS_HISTOGRAM_CAP_DAYS) -> pd.DataFrame:
    """Fill empty bins, then suppress and round bin counts.

    Returns columns: bin_start_day, bin_label, admissions (NaN if suppressed),
    suppressed.
    """
    counts = (
        df.set_index("bin_start_day")["admissions"] if not df.empty else pd.Series(dtype="int64")
    )
    bins = pd.DataFrame({"bin_start_day": range(0, cap + 1)})
    bins["raw"] = bins["bin_start_day"].map(counts).fillna(0).astype("int64")
    if bins["raw"].sum() == 0:
        return bins.iloc[0:0].assign(bin_label=[], admissions=[], suppressed=[]).drop(columns="raw")
    # Bin counts are always rounded, so primary suppression is sufficient.
    mask = [is_small(v) for v in bins["raw"]]
    bins["suppressed"] = mask
    bins["admissions"] = [
        float("nan") if m else float(round_count(v)) for v, m in zip(bins["raw"], mask)
    ]
    bins["bin_label"] = [f"{d}+" if d == cap else f"{d}–{d + 1}" for d in bins["bin_start_day"]]
    return bins.drop(columns="raw")[["bin_start_day", "bin_label", "admissions", "suppressed"]]


__all__ = [
    "KpiView",
    "OTHER_LABEL",
    "present_kpis",
    "present_by_admission_type",
    "present_age_groups",
    "present_discharge_destinations",
    "present_distribution",
    "present_los_histogram",
]
