"""Medication Analytics charts (pure functions on PROTECTED presenter tables)."""

from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd
import plotly.graph_objects as go

from ehr_analytics.charts.theme import SEQUENTIAL, base_layout, empty_figure, get_theme

# (column, label, plotly number format) shown in a bar's hover tooltip
HoverField = tuple[str, str, str]


def ranked_bar(
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    *,
    value_title: str,
    mode: str = "light",
    muted: Iterable[bool] | None = None,
    hover_fields: Sequence[HoverField] = (),
    value_format: str = ",.0f",
    tick_suffix: str = "",
) -> go.Figure:
    """Horizontal bars in the given row order (first row at the top).

    `muted` flags rows drawn in gray (placeholders, 'Not recorded', 'Other').
    """
    theme = get_theme(mode)
    if df.empty:
        return empty_figure(theme)
    data = df.reset_index(drop=True)
    mask = list(muted) if muted is not None else [False] * len(data)
    plotted = data[value_col].notna()
    if not plotted.any():
        return empty_figure(theme, "All values are suppressed for this selection")
    hover = f"<b>%{{y}}</b><br>{value_title}: %{{x:{value_format}}}{tick_suffix}"
    for i, (_, label, fmt) in enumerate(hover_fields):
        hover += f"<br>{label}: %{{customdata[{i}]:{fmt}}}"
    custom = data[[c for c, _, _ in hover_fields]].to_numpy() if hover_fields else None
    fig = go.Figure(
        go.Bar(
            x=data[value_col],
            y=data[label_col],
            orientation="h",
            marker=dict(color=[theme.muted if m else theme.series for m in mask]),
            customdata=custom,
            hovertemplate=hover + "<extra></extra>",
        )
    )
    fig.update_layout(**base_layout(theme, height=max(150, 26 * len(data) + 90)))
    fig.update_layout(bargap=0.3)
    fig.update_yaxes(autorange="reversed", showgrid=False, title=None, tickfont=dict(size=11))
    fig.update_xaxes(title=dict(text=value_title), tickformat=",", ticksuffix=tick_suffix)
    return fig


def orders_vs_stops(df: pd.DataFrame, *, mode: str = "light") -> go.Figure:
    """Grouped bars: orders (slot 1, blue) beside stop events (slot 2, orange)."""
    theme = get_theme(mode)
    if df.empty:
        return empty_figure(theme)
    fig = go.Figure()
    for col, name, color in (("orders", "Orders", theme.series), ("stops", "Stop events", theme.series_2)):
        fig.add_bar(
            x=df[col],
            y=df["drug"],
            name=name,
            orientation="h",
            marker=dict(color=color),
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:,.0f}}<extra></extra>",
        )
    layout = base_layout(theme, height=max(220, 40 * len(df) + 110))
    layout.update(
        barmode="group",
        bargap=0.28,
        bargroupgap=0.08,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(color=theme.text_secondary, size=12)),
    )
    fig.update_layout(**layout)
    fig.update_yaxes(autorange="reversed", showgrid=False, title=None, tickfont=dict(size=11))
    fig.update_xaxes(title=dict(text="Events"), tickformat=",")
    return fig


def ordinal_columns(
    df: pd.DataFrame, label_col: str, value_col: str, *, value_title: str, x_title: str, mode: str = "light"
) -> go.Figure:
    """Vertical columns over ordered bands (e.g. orders per admission)."""
    theme = get_theme(mode)
    if df.empty or df[value_col].dropna().empty:
        return empty_figure(theme)
    fig = go.Figure(
        go.Bar(
            x=df[label_col],
            y=df[value_col],
            marker=dict(color=theme.series),
            customdata=df[["share_pct"]].fillna(0).to_numpy() if "share_pct" in df else None,
            hovertemplate=(
                f"<b>%{{x}}</b><br>{value_title}: %{{y:,.0f}}"
                + ("<br>Share: %{customdata[0]:.1f}%" if "share_pct" in df else "")
                + "<extra></extra>"
            ),
        )
    )
    layout = base_layout(theme, height=320)
    layout["bargap"] = 0.2
    fig.update_layout(**layout)
    fig.update_xaxes(type="category", title=dict(text=x_title), showgrid=False)
    fig.update_yaxes(title=dict(text=value_title), tickformat=",")
    return fig


def co_ordering_heatmap(matrix: pd.DataFrame, *, mode: str = "light") -> go.Figure:
    """Square heatmap: row drug -> % of its admissions that also ordered column drug."""
    theme = get_theme(mode)
    if matrix.empty:
        return empty_figure(theme, "No co-ordering data")
    labels = list(matrix.index)
    ramp = SEQUENTIAL["dark" if mode == "dark" else "light"]
    fig = go.Figure(
        go.Heatmap(
            z=matrix.to_numpy(),
            x=labels,
            y=labels,
            colorscale=[[i / (len(ramp) - 1), c] for i, c in enumerate(ramp)],
            zmin=0,
            zmax=100,
            xgap=2,
            ygap=2,
            hoverongaps=False,
            colorbar=dict(
                title=dict(text="% of row drug's<br>admissions", font=dict(size=11, color=theme.text_secondary)),
                ticksuffix="%",
                tickfont=dict(color=theme.text_secondary, size=11),
                thickness=12,
                outlinewidth=0,
            ),
            hovertemplate=(
                "Admissions ordering <b>%{y}</b><br>that also ordered <b>%{x}</b>: "
                "%{z:.1f}%<extra></extra>"
            ),
        )
    )
    layout = base_layout(theme, height=max(420, 34 * len(labels) + 170))
    fig.update_layout(**layout)
    fig.update_xaxes(showgrid=False, tickangle=-40, tickfont=dict(size=11), side="bottom")
    fig.update_yaxes(showgrid=False, autorange="reversed", tickfont=dict(size=11))
    return fig
