"""Data-access functions, one module per dashboard page.

Repositories run SQL and return RAW aggregates. They never apply privacy rules
or formatting; see ehr_analytics.presenters for that.
"""
