"""Chart colors and base layout for light and dark mode.

Colors come from a validated reference palette (checked with the dataviz
palette validator: CVD separation and contrast pass in both modes).

* SERIES   — the single categorical hue used by every one-series chart.
* SERIES_2 — second categorical slot (orange), for two-series comparisons.
* MUTED    — deliberately gray, used only for "Not recorded" and
             "Other (small groups)" so missing or merged data recedes. It is never
             the only cue: those bars are also named in their axis labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import plotly.graph_objects as go

Mode = Literal["light", "dark"]


@dataclass(frozen=True)
class ChartTheme:
    series: str
    series_2: str  # second categorical slot; validated against `series` (CVD ΔE ≥ 24)
    muted: str
    surface: str
    text_primary: str
    text_secondary: str
    gridline: str
    baseline: str


THEMES: dict[str, ChartTheme] = {
    "light": ChartTheme(
        series="#2a78d6",
        series_2="#eb6834",
        muted="#898781",
        surface="#fcfcfb",
        text_primary="#0b0b0b",
        text_secondary="#52514e",
        gridline="#e1e0d9",
        baseline="#c3c2b7",
    ),
    "dark": ChartTheme(
        series="#3987e5",
        series_2="#d95926",
        muted="#898781",
        surface="#1a1a19",
        text_primary="#f0efec",
        text_secondary="#c3c2b7",
        gridline="#2c2c2a",
        baseline="#383835",
    ),
}

# Continuous one-hue (blue) sequential scales for heatmaps. In light mode low
# values recede toward the light surface; in dark mode toward the dark surface.
SEQUENTIAL = {
    "light": ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
    "dark": ["#104281", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
}

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def get_theme(mode: str | None) -> ChartTheme:
    return THEMES["dark" if mode == "dark" else "light"]


def base_layout(theme: ChartTheme, *, height: int = 360) -> dict:
    """Recessive chrome: hairline solid grid, no chart border, transparent paper."""
    axis = dict(
        gridcolor=theme.gridline,
        gridwidth=1,
        zeroline=False,
        linecolor=theme.baseline,
        tickfont=dict(color=theme.text_secondary, size=12),
        title=dict(font=dict(color=theme.text_secondary, size=12)),
        automargin=True,
    )
    return dict(
        height=height,
        margin=dict(l=8, r=16, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, color=theme.text_primary, size=13),
        hoverlabel=dict(
            bgcolor=theme.surface,
            bordercolor=theme.gridline,
            font=dict(family=FONT_FAMILY, color=theme.text_primary, size=13),
        ),
        showlegend=False,
        xaxis=axis,
        yaxis=dict(axis),
        bargap=0.25,
        barcornerradius=4,
    )


def empty_figure(theme: ChartTheme, message: str = "No data for the current filters") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**base_layout(theme, height=240))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(
        text=message,
        showarrow=False,
        font=dict(color=theme.text_secondary, size=14),
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
    )
    return fig
