"""Presenters turn raw aggregates into disclosure-controlled display tables.

Every number the dashboard shows passes through a presenter, which applies the
rules in ehr_analytics.privacy (suppression, rounding, statistic minimums).
"""
