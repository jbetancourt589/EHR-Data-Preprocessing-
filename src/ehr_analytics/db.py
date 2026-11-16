"""Database access for the dashboard.

The dashboard connects ONLY as the read-only `ehr_dashboard` role. Several
independent safeguards apply (any one of them blocks writes):

1. The role is granted SELECT only, and nothing on clinical_notes.
2. Role defaults: read-only transactions, 15 s statement timeout, JIT off.
3. The same settings are also sent by this module at connection time, so they
   still apply if the role defaults are ever changed.
4. `get_dashboard_engine()` refuses to run if the connected role is a superuser.

Credentials come from the project's .env file and are never logged.
"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Applied to every dashboard connection via libpq "options".
_SESSION_OPTIONS = " ".join(
    [
        "-c default_transaction_read_only=on",
        "-c statement_timeout=15000",  # milliseconds
        "-c idle_in_transaction_session_timeout=60000",
        "-c jit=off",
        # Percentile aggregates sort every stay in a group. With the server's
        # default 4 MB these sorts spill to disk (~25 MB); 64 MB keeps them in
        # memory. Applies to dashboard sessions only, not the server.
        "-c work_mem=64MB",
    ]
)


class DashboardConfigError(RuntimeError):
    """Raised when the dashboard's database settings are missing or unsafe."""


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def _build_url(user: str, password: str, database: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=database,
    )


@lru_cache(maxsize=1)
def get_dashboard_engine() -> Engine:
    """Return the shared read-only engine (created once per process)."""
    _load_env()
    user = os.getenv("DASHBOARD_DB_USER")
    password = os.getenv("DASHBOARD_DB_PASSWORD")
    database = os.getenv("DB_NAME")
    missing = [
        name
        for name, value in (
            ("DASHBOARD_DB_USER", user),
            ("DASHBOARD_DB_PASSWORD", password),
            ("DB_NAME", database),
        )
        if not value
    ]
    if missing:
        raise DashboardConfigError(
            "Missing settings in .env: " + ", ".join(missing)
            + ". See .env.example and sql/admin/001_dashboard_role.sql."
        )

    engine = create_engine(
        _build_url(user, password, database),
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,  # transparently replace connections dropped by the server
        pool_recycle=1800,
        connect_args={
            "options": _SESSION_OPTIONS,
            "application_name": "ehr_dashboard",
            "connect_timeout": 5,
        },
    )
    _assert_not_superuser(engine)
    return engine


def _assert_not_superuser(engine: Engine) -> None:
    with engine.connect() as conn:
        is_super = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    if is_super:
        engine.dispose()
        raise DashboardConfigError(
            "The dashboard must not connect as a superuser. "
            "Set DASHBOARD_DB_USER to the read-only ehr_dashboard role."
        )


def run_query(engine: Engine, sql: str, params: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """Execute one parameterized SELECT and return the (small) result.

    All user-controlled values must be passed in `params`; `sql` must come from
    sql_loader, never from user input.
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql), dict(params or {}))
        frame = pd.DataFrame(result.fetchall(), columns=list(result.keys()))
    return _decimals_to_float(frame)


def _decimals_to_float(frame: pd.DataFrame) -> pd.DataFrame:
    """PostgreSQL SUM(bigint) returns NUMERIC, which psycopg maps to Decimal.

    Aggregates are counts or rates, so float64 is exact enough (integers up to
    2**53) and lets pandas do vectorized math.
    """
    for column in frame.columns:
        values = frame[column].dropna()
        if not values.empty and all(isinstance(v, Decimal) for v in values):
            frame[column] = frame[column].astype("float64")
    return frame
