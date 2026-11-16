"""Reusable Streamlit layout components."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import psycopg
import sqlalchemy.exc
import streamlit as st

from ehr_analytics.db import DashboardConfigError

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def inject_base_css() -> None:
    """Small, theme-aware polish on top of Streamlit's own theme."""
    st.markdown(
        """
        <style>
          .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }
          [data-testid="stMetricValue"] { font-size: 1.85rem; font-weight: 600; }
          [data-testid="stMetricLabel"] p { font-size: 0.86rem; opacity: 0.8; }
          .page-eyebrow { font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase;
                          opacity: 0.65; margin-bottom: -0.4rem; }
          .page-subtitle { opacity: 0.75; margin-top: -0.6rem; margin-bottom: 1rem; }
          .card-caption { font-size: 0.85rem; opacity: 0.72; margin-top: -0.5rem; }
          .upcoming { font-size: 0.86rem; opacity: 0.5; display: block; padding: 2px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def theme_mode() -> str:
    """'light' or 'dark', following the viewer's active Streamlit theme."""
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # older Streamlit or bare mode
        return "light"


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(f"<div class='page-eyebrow'>{eyebrow}</div>", unsafe_allow_html=True)
    st.title(title, anchor=False)
    st.markdown(f"<div class='page-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def sql_panel(sql: str, params: dict[str, Any]) -> None:
    """Show the exact SQL a visual was computed from, plus its bind parameters."""
    st.code(sql.strip(), language="sql", line_numbers=False)
    if params:
        st.caption("Bind parameters (sent separately from the SQL text):")
        st.code(json.dumps(params, indent=2, ensure_ascii=False), language="json")
    else:
        st.caption("No filters applied — no bind parameters.")


def chart_card(
    title: str,
    caption: str,
    figure: go.Figure,
    table: pd.DataFrame,
    sql: str,
    params: dict[str, Any],
    *,
    key: str,
) -> None:
    """Bordered card with Chart / Table / SQL tabs.

    The Table tab is the accessible twin of every chart: every plotted value is
    readable without hovering.
    """
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.markdown(f"<div class='card-caption'>{caption}</div>", unsafe_allow_html=True)
        chart_tab, table_tab, sql_tab = st.tabs(["Chart", "Table", "SQL"])
        with chart_tab:
            st.plotly_chart(figure, theme=None, config=PLOTLY_CONFIG, key=key, width="stretch")
        with table_tab:
            st.dataframe(table, hide_index=True, width="stretch")
        with sql_tab:
            sql_panel(sql, params)


def stop_with_error(exc: Exception) -> None:
    """Show a friendly message for a data-loading failure and stop the page.

    Exception details go to the local console only (showErrorDetails="type").
    """
    if isinstance(exc, DashboardConfigError):
        st.error(f"**Database configuration needed.** {exc}", icon=":material/key:")
    elif isinstance(getattr(exc, "orig", None), psycopg.errors.QueryCanceled):
        st.error(
            "A query exceeded the 15-second time limit and was cancelled. "
            "Try a narrower filter or reload the page.",
            icon=":material/timer_off:",
        )
    elif isinstance(getattr(exc, "orig", None), psycopg.errors.InsufficientPrivilege):
        st.error(
            "The read-only dashboard role lacks access to a required object. "
            "Run sql/analytics/003_grants.sql as postgres.",
            icon=":material/lock:",
        )
    elif isinstance(exc, sqlalchemy.exc.OperationalError):
        st.error(
            "Could not connect to PostgreSQL. Check that the server is running and "
            "that the dashboard credentials in `.env` are correct.",
            icon=":material/cloud_off:",
        )
    else:
        st.error(f"Unexpected error while loading data ({type(exc).__name__}).")
    st.stop()
