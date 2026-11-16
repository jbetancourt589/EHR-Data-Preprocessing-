"""Lab Results Analytics charts (pure functions on PROTECTED presenter tables)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from ehr_analytics.charts.theme import base_layout, empty_figure, get_theme


def sparse_ticks(labels: list[str], every: int) -> list[str]:
    """First and last labels plus every `every`-th label between, skipping the
    one right after the first so a wide first label ("Before adm.") never
    collides with its neighbour."""
    if len(labels) <= 2 or every <= 1:
        return labels
    # index 0 is the wide first label and index 1 is bucket 0, so labels[every + 1]
    # is bucket `every` (5, 10, 15, ...) and never touches the first label.
    middle = labels[every + 1:-1:every] if every > 2 else labels[1:-1:every]
    return [labels[0], *middle, labels[-1]]


def counts_over_time(df: pd.DataFrame, *, x_title: str, mode: str = "light", tick_every: int = 1) -> go.Figure:
    """Columns of result counts per time bucket (day of stay or shifted year)."""
    theme = get_theme(mode)
    if df.empty or df["results"].dropna().empty:
        return empty_figure(theme)
    fig = go.Figure(
        go.Bar(
            x=df["label"],
            y=df["results"],
            marker=dict(color=theme.series),
            hovertemplate="<b>%{x}</b><br>Results: %{y:,.0f}<extra></extra>",
        )
    )
    layout = base_layout(theme, height=320)
    layout["bargap"] = 0.15
    fig.update_layout(**layout)
    fig.update_xaxes(type="category", title=dict(text=x_title), showgrid=False,
                     tickvals=sparse_ticks(list(df["label"]), tick_every), tickangle=0)
    fig.update_yaxes(title=dict(text="Results"), tickformat=",")
    return fig


def median_with_iqr(df: pd.DataFrame, *, units: str, x_title: str, mode: str = "light", tick_every: int = 1) -> go.Figure:
    """Median line with a shaded interquartile band (p25–p75). One series."""
    theme = get_theme(mode)
    data = df.dropna(subset=["p50"]) if not df.empty else df
    if data.empty:
        return empty_figure(theme, "Not enough numeric results to show a median")
    band = _rgba(theme.series, 0.18)
    fig = go.Figure()
    fig.add_scatter(x=data["label"], y=data["p75"], mode="lines", line=dict(width=0),
                    hoverinfo="skip", showlegend=False)
    fig.add_scatter(x=data["label"], y=data["p25"], mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor=band, hoverinfo="skip", showlegend=False)
    fig.add_scatter(
        x=data["label"], y=data["p50"], mode="lines+markers",
        line=dict(color=theme.series, width=2), marker=dict(size=8, color=theme.series,
                                                             line=dict(width=2, color=theme.surface)),
        customdata=data[["p25", "p75", "n_shown"]].to_numpy(),
        hovertemplate=(
            "<b>%{x}</b><br>Median: %{y:.4g} " + units
            + "<br>IQR: %{customdata[0]:.4g}–%{customdata[1]:.4g}"
            + "<br>Results: %{customdata[2]:,.0f}<extra></extra>"
        ),
        showlegend=False,
    )
    fig.update_layout(**base_layout(theme, height=320))
    fig.update_xaxes(type="category", title=dict(text=x_title), showgrid=False,
                     tickvals=sparse_ticks(list(data["label"]), tick_every), tickangle=0)
    fig.update_yaxes(title=dict(text=f"Value ({units})"))
    return fig


def value_histogram(df: pd.DataFrame, *, units: str, mode: str = "light") -> go.Figure:
    """Histogram from SQL-computed bins. Overflow bins (outside p1–p99) in gray."""
    theme = get_theme(mode)
    if df.empty or df["results"].dropna().empty:
        return empty_figure(theme, "No histogram for this test and unit")
    overflow = df["low"].isna() | df["high"].isna()
    fig = go.Figure(
        go.Bar(
            x=df["label"],
            y=df["results"],
            marker=dict(color=[theme.muted if o else theme.series for o in overflow]),
            customdata=df[["share_pct"]].fillna(0).to_numpy(),
            hovertemplate=(
                "<b>%{x} " + units + "</b><br>Results: %{y:,.0f}"
                "<br>Share: %{customdata[0]:.1f}%<extra></extra>"
            ),
        )
    )
    layout = base_layout(theme, height=340)
    layout["bargap"] = 0.08
    fig.update_layout(**layout)
    labels = list(df["label"])
    ticks = [labels[0], *labels[6:-1:6], labels[-1]] if len(labels) > 8 else labels
    fig.update_xaxes(type="category", title=dict(text=f"Value ({units}); gray = below 1st / above 99th percentile"),
                     showgrid=False, tickvals=ticks, tickangle=-30)
    fig.update_yaxes(title=dict(text="Results"), tickformat=",")
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i: i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"
