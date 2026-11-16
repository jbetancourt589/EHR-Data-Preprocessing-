"""Shared fixtures.

The `test_engine` fixture connects to the SYNTHETIC test database only.
Safety checks before any DDL:
  * the target name must not be the production database name, and
  * the connected server must report current_database() == TEST_DB_NAME.
If the test database is unreachable, database tests are skipped (not failed).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = "ehr_analytics"

PATIENTS = [
    # subject_id, age, gender
    (1, 25, "F"),
    (2, 65, "M"),
    (3, 91, "F"),     # capped anchor age
    (4, None, None),  # missing demographics
]


def ts(text_value: str | None) -> datetime | None:
    return datetime.fromisoformat(text_value) if text_value else None


ADMISSIONS = [
    # hadm_id, subject_id, admit, discharge, type, discharge_location
    (101, 1, "2100-01-01 00:00", "2100-01-03 12:00", "EW EMER.", "HOME"),                      # 2.5 d
    (102, 1, "2100-02-01 08:00", "2100-02-01 08:00", "URGENT", None),                          # 0 d (valid)
    (103, 2, "2100-01-01 00:00", "2100-01-11 00:00", "EW EMER.", "DIED"),                      # 10 d
    (104, 2, None, None, None, None),                                                          # missing
    (105, 3, "2100-05-10 00:00", "2100-05-09 00:00", "ELECTIVE", "HOME"),                      # negative
    (106, 4, "2100-03-01 00:00", "2100-04-15 00:00", "EW EMER.", "SKILLED NURSING FACILITY"),  # 45 d
    (107, 3, "2100-06-01 00:00", None, "EW EMER.", None),                                      # missing
]


# hadm_id, drug, event_type, route. Hand-checked expectations are documented
# in tests/test_medication_sql.py.
O, S = "MED_ORDER", "MED_STOP"
MEDICATIONS = [
    (101, "Insulin", O, "SC"), (101, "Insulin", O, "SC"), (101, "Insulin", S, None),
    (101, "Heparin", O, "IV"), (101, "Heparin", S, None),
    (101, "Bag", O, None),                       # container placeholder
    (101, "*Nf* Warfarin", O, "PO"),             # non-formulary spelling
    (101, "", O, None),                          # blank name: excluded everywhere
    (102, "Insulin", O, "SC"), (102, "Insulin", S, None),
    (102, "Acetaminophen", O, "PO"),
    (103, "Insulin", O, "SC"),
    (103, "Heparin", O, "IV"), (103, "Heparin", O, "SC"), (103, "Heparin", O, "SC"),
    (103, "Heparin", S, None), (103, "Heparin", S, None),
    (103, "Acetaminophen", O, "IV"),
    (104, "Heparin", S, None),                   # stop without an order
    (105, "Warfarin", O, "PO"),
    *[(107, "Acetaminophen", O, "PO")] * 6,      # six orders in one admission
]

# Lab results: (hadm_id, event_time, lab_name, value, units, flag, text_value, result_type, operator).
# Expected values are worked out in tests/test_lab_sql.py.
def _glucose_rows():
    """1,200 numeric Glucose results (enough for a histogram: >= 1,000).

    value = 50 + i * 0.25 (50 .. 349.75). Even i: hadm 101 day 0; odd i: hadm 103 day 1.
    """
    rows = []
    for i in range(1200):
        hadm, day = (101, 0) if i % 2 == 0 else (103, 1)
        rows.append((hadm, f"2100-01-0{1 + day} 06:00", "Glucose", 50 + i * 0.25, "mg/dL",
                     "abnormal", None, "numeric", None))
    return rows


LABS = [
    *_glucose_rows(),
    (102, "2100-02-01 09:00", "Glucose", 500.0, "mg/dL", "abnormal", None, "numeric", ">"),       # censored
    (102, "2100-02-01 10:00", "Glucose", None, None, "abnormal", "HEMOLYZED", "text", None),       # text
    # Source quirk: missing value written as the text "nan", under a case-variant name.
    (102, "2100-02-01 11:00", "glucose", None, None, "abnormal", "nan nan", "text", None),
    (101, "2100-01-01 07:00", "MCHC", 33.0, "g/dL", "abnormal", None, "numeric", None),
    (101, "2100-01-02 07:00", "MCHC", 34.0, "g/dL", "abnormal", None, "numeric", None),
    (103, "2100-01-01 07:00", "MCHC", 92.0, "%", "abnormal", None, "numeric", None),             # other unit
    (105, "2100-05-09 12:00", "Potassium", 3.1, "mEq/L", None, None, "numeric", None),           # before admission, no flag
    (107, "2100-07-15 00:00", "Sodium", 140.0, "mEq/L", "normal", None, "numeric", None),        # day 30+, normal flag
    (106, "2100-03-02 00:00", "Lactate", 2.0, "", "abnormal", None, "numeric", None),            # blank unit
]

ANALYTICS_DDL = (
    "001_schema_and_views.sql", "002_medication_summaries.sql", "003_grants.sql", "004_lab_summaries.sql",
)


def run_sql_file(conn, path: Path) -> None:
    """Execute a multi-statement SQL file with NO bind parameters.

    A plain DB-API cursor is used because SQL files may contain literal "%"
    (e.g. in regular expressions), which psycopg would otherwise read as a
    parameter placeholder.
    """
    cursor = conn.connection.cursor()
    try:
        cursor.execute(path.read_text(encoding="utf-8"))
    finally:
        cursor.close()


@pytest.fixture(scope="session")
def test_engine():
    load_dotenv(ROOT / ".env")
    name = os.getenv("TEST_DB_NAME", "ehr_analytics_test")
    if name in (PRODUCTION_DB, os.getenv("DB_NAME")):
        pytest.exit("Refusing to run database tests against the production database.", returncode=2)
    user, password = os.getenv("DB_USER"), os.getenv("DB_PASSWORD")
    if not user or not password:
        pytest.skip("DB_USER/DB_PASSWORD not configured")

    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username=user,
            password=password,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=name,
        )
    )
    try:
        with engine.connect() as conn:
            actual = conn.execute(text("SELECT current_database()")).scalar()
    except OperationalError:
        pytest.skip(f"Test database {name!r} is not reachable")
    if actual != name or actual == PRODUCTION_DB:
        pytest.exit(f"Connected to {actual!r}, expected {name!r}; aborting.", returncode=2)

    with engine.begin() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar() == name
        conn.exec_driver_sql("DROP SCHEMA IF EXISTS analytics CASCADE")
        conn.exec_driver_sql(
            "DROP TABLE IF EXISTS microbiology, clinical_notes, transfers, medications, "
            "lab_results, admissions, patients CASCADE"
        )
        conn.exec_driver_sql((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        conn.execute(
            text("INSERT INTO patients (subject_id, age, gender) VALUES (:s, :a, :g)"),
            [{"s": s, "a": a, "g": g} for s, a, g in PATIENTS],
        )
        conn.execute(
            text(
                "INSERT INTO admissions (hadm_id, subject_id, admission_time, discharge_time, "
                "admission_type, discharge_location) VALUES (:h, :s, :ad, :di, :t, :d)"
            ),
            [
                {"h": h, "s": s, "ad": ts(ad), "di": ts(di), "t": t, "d": d}
                for h, s, ad, di, t, d in ADMISSIONS
            ],
        )
        conn.execute(
            text(
                "INSERT INTO medications (hadm_id, event_time, event_type, drug, route) "
                "VALUES (:h, '2100-01-01', :e, :d, :r)"
            ),
            [{"h": h, "d": d, "e": e, "r": r} for h, d, e, r in MEDICATIONS],
        )
        conn.execute(
            text(
                "INSERT INTO lab_results (hadm_id, event_time, lab_name, value, units, flag, "
                "text_value, result_type, operator) VALUES (:h, :t, :n, :v, :u, :f, :tv, :rt, :op)"
            ),
            [
                {"h": h, "t": ts(t), "n": n, "v": v, "u": u, "f": f, "tv": tv, "rt": rt, "op": op}
                for h, t, n, v, u, f, tv, rt, op in LABS
            ],
        )
        # Build the same analytics objects the real database uses.
        for name in ANALYTICS_DDL:
            run_sql_file(conn, ROOT / "sql" / "analytics" / name)
    yield engine
    engine.dispose()
