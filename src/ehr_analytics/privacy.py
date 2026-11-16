"""Disclosure-control rules for aggregate results shown in the dashboard.

PROVISIONAL SAFEGUARDS — these reduce, but do not formally eliminate,
re-identification risk, and they are not proof of MIMIC / PhysioNet compliance.
Verify the applicable disclosure requirements before any public release.

Rules
-----
1. Primary suppression. A count of 1–10 (n < SMALL_CELL_THRESHOLD) is never
   displayed; it is shown as "<11". Zero is shown (it describes nobody).
2. Complementary (secondary) suppression. Where EXACT counts are shown (the
   unfiltered headline KPIs), if a hidden cell could be recovered by
   subtraction from a known total, the next-smallest cell is hidden too.
   Breakdowns merge their small cells into one "Other (small groups)" row,
   shown as suppressed if it is itself under 11. Rounded counts (rule 3) carry
   ±2 error per cell, so subtraction cannot recover a hidden cell exactly;
   large categories are therefore never hidden to protect a small one.
3. Rounding. Every count derived from a breakdown or a filtered cohort is
   rounded to the nearest ROUNDING_BASE (5). Percentages are computed from the
   rounded counts, so they cannot be used to recover exact counts. Rounding is
   deterministic: repeating a query returns the identical value, so averaging
   repeated results reveals nothing new (random rounding would).
   Exact counts are shown only for the whole-database headline totals.
4. Filter differencing. A filtered cohort is shown only if it contains at
   least 11 admissions AND leaves out either none or at least 11 admissions.
   Otherwise "everyone except X" minus "everyone" would isolate a small group.
   Together with rounding, differences between two filtered views are uncertain
   by several admissions.
5. Statistics. Means and percentiles are shown only for groups with at least
   STATISTIC_MIN_N valid stays, and minima/maxima are never shown (an extreme
   value usually describes one individual). Box-plot whiskers are p10/p90.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import pandas as pd

SMALL_CELL_THRESHOLD = 11
ROUNDING_BASE = 5
STATISTIC_MIN_N = 30
OTHER_LABEL = "Other (small groups)"
SUPPRESSED_TEXT = f"<{SMALL_CELL_THRESHOLD}"


def is_small(n: int | float | None) -> bool:
    """True for counts that must be suppressed (1 .. threshold-1)."""
    return n is not None and not pd.isna(n) and 0 < n < SMALL_CELL_THRESHOLD


def round_count(n: int | float, base: int = ROUNDING_BASE) -> int:
    """Round half-up to the nearest `base` (12 -> 10, 13 -> 15, 491_699 -> 491_700)."""
    if base <= 1:
        return int(n)
    return int(math.floor(n / base + 0.5) * base)


def format_count(n: int | float | None, *, exact: bool = False) -> str:
    """Display string for one count after suppression and (unless exact) rounding."""
    if n is None or pd.isna(n):
        return "—"
    if is_small(n):
        return SUPPRESSED_TEXT
    return f"{int(n) if exact else round_count(n):,}"


def statistic_allowed(n_valid: int | float | None) -> bool:
    """Whether a mean/percentile over `n_valid` stays may be displayed."""
    return n_valid is not None and not pd.isna(n_valid) and n_valid >= STATISTIC_MIN_N


def suppression_mask(counts: Sequence[int | float]) -> list[bool]:
    """Primary + complementary suppression for a set of cells with a known total.

    Returns True for every cell that must be hidden.
    """
    values = [0 if pd.isna(c) else c for c in counts]
    mask = [is_small(v) for v in values]
    while any(mask):
        hidden = [v for v, m in zip(values, mask) if m]
        if len(hidden) >= 2 and sum(hidden) >= SMALL_CELL_THRESHOLD:
            break
        candidates = [i for i, (v, m) in enumerate(zip(values, mask)) if not m and v > 0]
        if not candidates:
            break  # everything non-zero is already hidden
        mask[min(candidates, key=lambda i: values[i])] = True
    return mask


def protect_categories(
    df: pd.DataFrame,
    label_col: str,
    count_col: str,
    additive_cols: Sequence[str] = (),
) -> pd.DataFrame:
    """Merge small category rows into a single "Other (small groups)" row.

    Only rows that are themselves small (n < 11) are merged. If the merged
    Other row is still small, its count (and additive columns) become NaN, i.e.
    it is shown as suppressed. Large categories are never hidden to protect a
    small one: breakdown counts are always rounded (rule 3), so subtracting
    visible cells from a total cannot recover a hidden cell exactly.

    `additive_cols` are summed into the Other row (e.g. los_valid_n); all other
    numeric columns become NaN for that row, because group statistics such as
    medians cannot be combined. Adds a boolean `is_other` column.
    The caller is responsible for rounding the counts for display.
    """
    out = df.copy()
    out["is_other"] = False
    if out.empty:
        return out
    mask = [is_small(v) for v in out[count_col]]
    if not any(mask):
        return out
    hidden = out[mask]
    other: dict[str, object] = {col: float("nan") for col in out.columns}
    other[label_col] = OTHER_LABEL
    other_count = hidden[count_col].sum()
    other_is_small = is_small(other_count)
    other[count_col] = float("nan") if other_is_small else other_count
    for col in additive_cols:
        other[col] = float("nan") if other_is_small else hidden[col].sum()
    other["is_other"] = True
    kept = out[[not m for m in mask]]
    return pd.concat([kept, pd.DataFrame([other])], ignore_index=True)


def round_or_nan(n: float | None) -> float:
    """Round a count for display; NaN stays NaN (already suppressed)."""
    return float("nan") if n is None or pd.isna(n) else float(round_count(n))


def protect_count_column(counts: pd.Series) -> pd.Series:
    """Suppress small cells (NaN) and round the rest to the nearest ROUNDING_BASE.

    Primary suppression only: every visible cell is rounded, so subtracting
    visible cells from a total leaves several admissions of uncertainty and
    cannot recover a hidden cell exactly.
    """
    mask = [is_small(v) or pd.isna(v) for v in counts]  # NaN = already suppressed upstream
    return pd.Series(
        [float("nan") if m else float(round_count(v)) for v, m in zip(counts, mask)],
        index=counts.index,
        dtype="float64",
    )


def safe_percent(numerator: float, denominator: float) -> float:
    """Percentage of two already-protected counts; NaN when undefined."""
    if pd.isna(numerator) or pd.isna(denominator) or denominator <= 0:
        return float("nan")
    return 100.0 * numerator / denominator


@dataclass(frozen=True)
class CohortCheck:
    allowed: bool
    message: str = ""


def check_cohort(cohort_n: int, population_n: int, filters_active: bool) -> CohortCheck:
    """Rule 4: block cohorts that are too small or exclude too few admissions."""
    if not filters_active:
        return CohortCheck(True)
    if cohort_n < SMALL_CELL_THRESHOLD:
        return CohortCheck(
            False,
            f"This filter combination matches fewer than {SMALL_CELL_THRESHOLD} admissions, "
            "so results are hidden to protect patient privacy. Broaden the filters.",
        )
    excluded = population_n - cohort_n
    if 0 < excluded < SMALL_CELL_THRESHOLD:
        return CohortCheck(
            False,
            f"This filter combination excludes fewer than {SMALL_CELL_THRESHOLD} admissions; "
            "comparing it with the full population would reveal a very small group, "
            "so results are hidden. Clear a filter or narrow the selection further.",
        )
    return CohortCheck(True)
