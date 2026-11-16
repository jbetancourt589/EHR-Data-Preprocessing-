"""Hospital Overview charts.

Inputs are the PROTECTED tables from ehr_analytics.presenters.overview, so
every value plotted has already passed suppression and rounding.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from ehr_analytics.charts.theme import base_layout, empty_figure, get_theme
from ehr_analytics.domain import NOT_RECORDED
from ehr_analytics.privacy import OTHER_LABEL


def _with_alpha(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def _bar_colors(labels: pd.Series, theme) -> list[str]:
    return [theme.muted if label in (NOT_RECORDED, OTHER_LABEL) else theme.series for label in labels]


def category_bar(
    df: pd.DataFrame,
    label_col: str,
    *,
    mode: str = "light",
    value_col: str = "admissions",
    value_title: str = "Admissions",
) -> go.Figure:
    """Horizontal bars, largest at the top, one hue; missing/merged rows in gray."""
    theme = get_theme(mode)
    data = df.dropna(subset=[value_col]) if not df.empty else df
    if data.empty:
        return empty_figure(theme)

    hover = (
        "<b>%{y}</b><br>"
        f"{value_title}: %{{x:,.0f}}<br>"
        "Share of cohort: %{customdata[0]:.1f}%<extra></extra>"
    )
    fig = go.Figure(
        go.Bar(
            x=data[value_col],
            y=data[label_col],
            orientation="h",
            marker=dict(color=_bar_colors(data[label_col], theme)),
            customdata=data[["share_pct"]].fillna(0).to_numpy(),
            hovertemplate=hover,
        )
    )
    # Height grows with the number of bars so a single bar stays a slim bar.
    layout = base_layout(theme, height=max(150, 34 * len(data) + 90))
    fig.update_layout(**layout)
    fig.update_yaxes(autorange="reversed", showgrid=False, title=None)
    fig.update_xaxes(title=dict(text=value_title), tickformat=",")
    return fig


def los_box_by_type(df: pd.DataFrame, *, mode: str = "light") -> go.Figure:
    """Box plot built from SQL-computed percentiles (no raw stays are fetched).

    Box = interquartile range (p25–p75), solid line = median, dashed line =
    mean, whiskers = p10 and p90. Min/max are intentionally not drawn.
    """
    theme = get_theme(mode)
    needed = ["los_p10_days", "los_p25_days", "los_median_days", "los_p75_days", "los_p90_days"]
    data = df.dropna(subset=needed) if not df.empty else df
    if data.empty:
        return empty_figure(theme, "Not enough valid stays to show a distribution")

    fig = go.Figure(
        go.Box(
            y=data["admission_type"],
            q1=data["los_p25_days"],
            median=data["los_median_days"],
            q3=data["los_p75_days"],
            lowerfence=data["los_p10_days"],
            upperfence=data["los_p90_days"],
            mean=data["los_mean_days"],
            orientation="h",
            boxpoints=False,
            boxmean=True,  # draw the SQL-computed mean as a dashed marker line
            # Translucent fill keeps the median line (drawn in the series color) visible.
            fillcolor=_with_alpha(theme.series, 0.22),
            line=dict(color=theme.series, width=2),
            whiskerwidth=0.4,
            hoverinfo="y+x",
        )
    )
    # Plotly's built-in box hover labels the whiskers "lower/upper fence"; the
    # caption in the dashboard explains that these are p10/p90 here.
    layout = base_layout(theme, height=max(170, 40 * len(data) + 100))
    fig.update_layout(**layout)
    fig.update_yaxes(autorange="reversed", showgrid=False, title=None)
    fig.update_xaxes(title=dict(text="Length of stay (days)"), rangemode="tozero")
    return fig


def los_histogram(df: pd.DataFrame, *, mode: str = "light") -> go.Figure:
    """Vertical histogram of valid stays in 1-day bins with a final overflow bin."""
    theme = get_theme(mode)
    if df.empty or df["admissions"].dropna().empty:
        return empty_figure(theme)

    is_overflow = df["bin_label"].str.endswith("+")
    # Suppressed bins have no bar (value NaN); the data table marks them "<11".
    status = [" (suppressed)" if s else "" for s in df["suppressed"]]
    fig = go.Figure(
        go.Bar(
            x=df["bin_label"],
            y=df["admissions"],
            marker=dict(color=[theme.muted if o else theme.series for o in is_overflow]),
            customdata=list(zip(status)),
            hovertemplate=(
                "<b>%{x} days</b><br>Admissions: %{y:,.0f}%{customdata[0]}<extra></extra>"
            ),
        )
    )
    layout = base_layout(theme, height=340)
    layout["bargap"] = 0.12
    fig.update_layout(**layout)
    # Label every 5th bin by its starting day, plus the overflow bin, instead of
    # 31 rotated range labels. The hover and Table tab show the exact range.
    labels = list(df["bin_label"])
    tick_vals = labels[::5] if not labels[-1].endswith("+") else labels[:-1][::5] + [labels[-1]]
    tick_text = [v if v.endswith("+") else v.split("–")[0] for v in tick_vals]
    fig.update_xaxes(
        title=dict(text="Length of stay (days; final bar = 30 days or longer)"),
        type="category",
        showgrid=False,
        tickvals=tick_vals,
        ticktext=tick_text,
        tickangle=0,
    )
    fig.update_yaxes(title=dict(text="Admissions"), tickformat=",")
    return fig
