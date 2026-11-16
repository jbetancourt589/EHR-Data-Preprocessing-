"""Analytics layer for the local EHR Clinical Analytics dashboard.

This package is intentionally free of Streamlit imports so it can be unit-tested
and reused from notebooks or scripts:

    db            read-only database engine and query execution
    sql_loader    loads and renders the .sql files in sql/queries/
    filters       whitelisted dashboard filters -> parameterized WHERE clause
    privacy       small-cell suppression and rounding rules
    domain        shared constants (age bands, labels)
    repositories  one module per dashboard page; returns small DataFrames
    charts        pure functions: DataFrame -> Plotly figure
"""
