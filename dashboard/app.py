"""EHR Clinical Analytics — Streamlit entry point.

Run from the project root:
    streamlit run dashboard/app.py

The app binds to localhost only (.streamlit/config.toml) and connects to
PostgreSQL as the read-only `ehr_dashboard` role.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="EHR Clinical Analytics",
    page_icon=":material/monitoring:",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components.ui import inject_base_css  # noqa: E402  (must follow set_page_config)

inject_base_css()

pages = {
    "Analytics": [
        st.Page(
            "views/overview.py",
            title="Hospital Overview",
            icon=":material/local_hospital:",
            default=True,
        ),
        st.Page(
            "views/medications.py",
            title="Medication Analytics",
            icon=":material/medication:",
        ),
        st.Page(
            "views/labs.py",
            title="Lab Results Analytics",
            icon=":material/biotech:",
        ),
    ],
    "Reference": [
        st.Page("views/methods.py", title="Methods & Privacy", icon=":material/policy:"),
    ],
}

navigation = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.markdown("### EHR Clinical Analytics")
    st.caption(
        "MIMIC-derived admissions · PostgreSQL 18 · local only, read-only connection"
    )
    st.divider()
    st.caption("In development")
    for upcoming in (
        "Cohort Explorer",
        "Transfers & Patient Journeys",
        "Data Quality & ETL",
    ):
        st.markdown(f"<span class='upcoming'>{upcoming}</span>", unsafe_allow_html=True)

navigation.run()
