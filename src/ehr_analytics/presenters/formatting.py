"""Cell formatting for display tables.

NaN has two different meanings in protected tables, so they are rendered
differently:
* a NaN COUNT or a percentage of one  -> "Suppressed" (privacy rule)
* a NaN LOS statistic                 -> "n/a"  (too few valid stays)
"""

from __future__ import annotations

import pandas as pd

SUPPRESSED = "Suppressed"
NOT_AVAILABLE = "n/a"


def count_cell(value: float | None) -> str:
    return SUPPRESSED if value is None or pd.isna(value) else f"{value:,.0f}"


def percent_cell(value: float | None, digits: int = 1) -> str:
    return SUPPRESSED if value is None or pd.isna(value) else f"{value:.{digits}f}%"


def days_cell(value: float | None) -> str:
    return NOT_AVAILABLE if value is None or pd.isna(value) else f"{value:.1f}"


def range_cell(low: float | None, high: float | None) -> str:
    if low is None or high is None or pd.isna(low) or pd.isna(high):
        return NOT_AVAILABLE
    return f"{low:.1f}–{high:.1f}"
