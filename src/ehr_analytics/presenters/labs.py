"""Lab Results Analytics presenter: raw summary rows -> privacy-protected views.

Abnormality rule (no invented reference ranges)
------------------------------------------------
Only explicit source flags are classified: 'abnormal' and 'normal'. A blank
flag means "not flagged", which is NOT the same as normal, so it is reported
separately and never enters the abnormal percentage.

An abnormal *rate* is only estimable if the data contain BOTH explicit
classes. In this MIMIC-derived extract every result is flagged 'abnormal'
(none 'normal'), which indicates the extract keeps only abnormal-flagged
results; a "100% abnormal" figure would be an artefact of how the data were
selected, so the rate is reported as not estimable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from ehr_analytics.domain import LAB_DAY_MAX, LAB_DAY_MIN, LAB_HISTOGRAM_BINS
from ehr_analytics.privacy import (
    STATISTIC_MIN_N,
    format_count,
    is_small,
    protect_count_column,
    round_count,
    safe_percent,
    statistic_allowed,
)


def _rounded(n: float | None) -> float:
    if n is None or pd.isna(n) or is_small(n):
        return float("nan")
    return float(round_count(n))


# ---------------------------------------------------------------- abnormality
@dataclass(frozen=True)
class AbnormalAssessment:
    estimable: bool
    percent: float          # NaN unless estimable
    interpretable_n: float  # abnormal + normal results in the cohort
    reason: str


def assess_abnormal_rate(row: Mapping[str, float], population: Mapping[str, float]) -> AbnormalAssessment:
    """Decide whether an abnormal percentage can be shown, and compute it."""
    abnormal = float(row["flag_abnormal"] or 0)
    normal = float(row["flag_normal"] or 0)
    interpretable = abnormal + normal
    if float(population["flag_normal"] or 0) == 0:
        return AbnormalAssessment(
            False, float("nan"), interpretable,
            "No result in the dataset carries an explicit 'normal' flag — every flagged result "
            "is 'abnormal'. The extract appears to contain only abnormal-flagged results, so an "
            "abnormal rate would be 100% by construction and is not estimable.",
        )
    if not statistic_allowed(interpretable):
        return AbnormalAssessment(
            False, float("nan"), interpretable,
            f"Fewer than {STATISTIC_MIN_N} results in this selection have an explicit "
            "abnormal/normal flag.",
        )
    return AbnormalAssessment(True, 100.0 * abnormal / interpretable, interpretable, "")


# ----------------------------------------------------------------------- KPIs
@dataclass(frozen=True)
class LabKpiView:
    results: str
    unique_tests: str
    unique_test_units: str
    abnormal: str
    abnormal_help: str
    admissions_with_labs: str
    cohort_admissions: str
    exact: bool


def present_kpis(row: Mapping[str, float], population: Mapping[str, float], *, exact: bool) -> LabKpiView:
    assessment = assess_abnormal_rate(row, population)
    if assessment.estimable:
        abnormal = f"{assessment.percent:.1f}%"
        help_text = (f"Abnormal ÷ (abnormal + normal) among results with an explicit flag "
                     f"({format_count(assessment.interpretable_n, exact=exact)} results). "
                     "Unflagged results are excluded.")
    else:
        abnormal = "Not estimable"
        help_text = assessment.reason
    return LabKpiView(
        results=format_count(row["results"], exact=exact),
        unique_tests=f"{int(row['unique_tests']):,}",          # counts of NAMES, not people
        unique_test_units=f"{int(row['unique_test_units']):,}",
        abnormal=abnormal,
        abnormal_help=help_text,
        admissions_with_labs=format_count(row["admissions_with_labs"], exact=exact),
        cohort_admissions=format_count(row["admissions"], exact=exact),
        exact=exact,
    )


# ------------------------------------------------------- flag & value classes
FLAG_CLASSES = (
    ("flag_abnormal", "Abnormal (flagged)"),
    ("flag_normal", "Normal (flagged)"),
    ("flag_other", "Other recorded flag"),
    ("flag_missing", "Not flagged (unknown)"),
)
VALUE_CLASSES = (
    ("numeric_results", "Numeric"),
    ("censored_results", "Censored (<, >)"),
    ("text_results", "Text / non-numeric"),
    ("missing_results", "Missing ('nan' in source)"),
)


def _class_table(row: Mapping[str, float], classes) -> pd.DataFrame:
    raw = pd.Series([float(row[c] or 0) for c, _ in classes], dtype="float64")
    out = pd.DataFrame({"key": [c for c, _ in classes], "label": [label for _, label in classes]})
    out["results"] = protect_count_column(raw).to_numpy()
    total = round_count(raw.sum())
    out["share_pct"] = [safe_percent(n, total) for n in out["results"]]
    return out


def present_flag_classes(row: Mapping[str, float]) -> pd.DataFrame:
    return _class_table(row, FLAG_CLASSES)


def present_value_classes(row: Mapping[str, float]) -> pd.DataFrame:
    return _class_table(row, VALUE_CLASSES)


# ----------------------------------------------------------------- top tests
def present_top_tests(df: pd.DataFrame, total_results: float) -> pd.DataFrame:
    """Round counts; shares are computed from the rounded values."""
    out = df.copy()
    total = round_count(total_results) if total_results else float("nan")
    out["results"] = out["results"].map(_rounded).astype("float64")
    out["numeric_results"] = out["numeric_results"].map(_rounded).astype("float64")
    out["share_pct"] = [safe_percent(n, total) for n in out["results"]]
    out["numeric_pct"] = [safe_percent(n, r) for n, r in zip(out["numeric_results"], out["results"])]
    out["units_list"] = out["units_list"].fillna("—")
    return out.reset_index(drop=True)


# ------------------------------------------------------------- time series
def day_label(day: int) -> str:
    if day <= LAB_DAY_MIN:
        return "Before adm."
    if day >= LAB_DAY_MAX:
        return f"{LAB_DAY_MAX}+"
    return str(day)


def present_counts_over_time(df: pd.DataFrame, axis: str) -> pd.DataFrame:
    """Result counts per bucket; empty day buckets are filled with 0."""
    counts = df.set_index("bucket")["results"] if not df.empty else pd.Series(dtype=float)
    if axis == "day":
        buckets = list(range(LAB_DAY_MIN, LAB_DAY_MAX + 1))
    else:
        buckets = sorted(int(b) for b in counts.index)
    out = pd.DataFrame({"bucket": buckets})
    out["label"] = [day_label(b) if axis == "day" else str(b) for b in buckets]
    raw = out["bucket"].map(counts).fillna(0).astype("float64")
    out["results"] = protect_count_column(raw)
    return out


def present_value_trend(df: pd.DataFrame, axis: str) -> pd.DataFrame:
    """Quartiles per bucket, shown only where n >= STATISTIC_MIN_N."""
    out = df.copy()
    if out.empty:
        return out.assign(label=pd.Series(dtype=str))
    blocked = ~out["n"].apply(statistic_allowed)
    for col in ("p25", "p50", "p75"):
        out[col] = out[col].astype("float64").where(~blocked)
    out["n_shown"] = out["n"].map(_rounded)
    out["label"] = [day_label(int(b)) if axis == "day" else str(int(b)) for b in out["bucket"]]
    return out.sort_values("bucket").reset_index(drop=True)


# ----------------------------------------------------------------- histogram
def present_histogram(df: pd.DataFrame) -> pd.DataFrame:
    """All 32 bins in order with edges and labels; small bins suppressed.

    bin 0  = below the 1st percentile, bin 31 = at/above the 99th percentile,
    bins 1..30 = equal-width bins between them.
    """
    if df.empty:
        return pd.DataFrame(columns=["bin", "label", "results", "low", "high", "share_pct"])
    lo, hi = float(df["lo"].iloc[0]), float(df["hi"].iloc[0])
    width = (hi - lo) / LAB_HISTOGRAM_BINS if hi > lo else 0.0
    counts = df.set_index("bin")["results"]
    out = pd.DataFrame({"bin": list(range(0, LAB_HISTOGRAM_BINS + 2))})
    raw = out["bin"].map(counts).fillna(0).astype("float64")
    out["results"] = protect_count_column(raw)
    out["low"] = [float("nan") if b == 0 else lo + (b - 1) * width for b in out["bin"]]
    out["high"] = [float("nan") if b == LAB_HISTOGRAM_BINS + 1 else lo + b * width for b in out["bin"]]

    def fmt(v: float) -> str:
        return f"{v:.4g}"

    out["label"] = [
        f"< {fmt(lo)}" if b == 0 else f"≥ {fmt(hi)}" if b == LAB_HISTOGRAM_BINS + 1
        else f"{fmt(l)}–{fmt(h)}"
        for b, l, h in zip(out["bin"], out["low"], out["high"])
    ]
    total = round_count(raw.sum())
    out["share_pct"] = [safe_percent(n, total) for n in out["results"]]
    if width == 0.0:  # constant-valued test: everything is in bin 1
        out = out[out["bin"] == 1].assign(label=f"{fmt(lo)}")
    return out.reset_index(drop=True)


__all__ = [
    "AbnormalAssessment",
    "LabKpiView",
    "assess_abnormal_rate",
    "present_kpis",
    "present_flag_classes",
    "present_value_classes",
    "present_top_tests",
    "present_counts_over_time",
    "present_value_trend",
    "present_histogram",
    "day_label",
]
