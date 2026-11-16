# EHR Clinical Analytics Platform

**Healthcare data engineering | PostgreSQL analytics | Streamlit dashboard | Python**

A local, privacy-conscious pipeline and dashboard for MIMIC-derived electronic health record (EHR) data:

1. **Preprocess** raw admission timelines into clean, chronologically ordered patient records.
2. **Load** them into a PostgreSQL database (about 200k patients, 490k admissions, 27M lab results, 33M medication events).
3. **Explore** the data in a multipage Streamlit dashboard where every number comes from a visible SQL query.

> **Status: work in progress.** Three dashboard pages are finished (Hospital Overview, Medication Analytics, Lab Results Analytics). Three more are planned but not built yet. See [Project status](#project-status).

## Safety and privacy first

- **Everything runs locally.** The dashboard binds to `localhost`, sends no telemetry, and calls no external APIs.
- **No MIMIC data is in this repository.** Raw data, processed output (`output.jsonl`) and `.env` are git-ignored. Only a tiny synthetic sample (`data/synthetic_sample.jsonl`) is tracked.
- **Read-only access.** The dashboard connects as a dedicated `ehr_dashboard` role: SELECT only, read-only transactions, 15 s statement timeout, no access to `clinical_notes`. The app refuses to start as a superuser.
- **Aggregates only.** No patient identifiers, individual encounters or note text are ever displayed.
- **Provisional disclosure controls** (not proof of MIMIC/PhysioNet compliance): counts under 11 are suppressed or merged, complementary suppression where exact counts are shown, breakdown and filtered counts rounded to the nearest 5, filter-differencing check, statistics require 30 or more values, no min/max shown.
- Filter values are sent as bind parameters. There is no free-form SQL input.

You must hold the appropriate PhysioNet credentials to use MIMIC data. This project does not provide or redistribute it.

## Architecture

```text
Compressed MIMIC timelines (.jsonl.zst)           (local only, git-ignored)
        |  src/format.py            parse labs/meds/transfers/notes, deduplicate, order
        v
output.jsonl                                      (local only, git-ignored)
        |  src/load_to_sql.py       batched, transactional, resumable import
        v
PostgreSQL: ehr_analytics (7 tables, public schema)
        |  sql/analytics/*.sql      precomputed AGGREGATE-ONLY summaries (analytics schema)
        v
sql/queries/<page>/*.sql            readable page queries ({{ base }} / {{ where }} templates)
        |  repositories -> presenters -> charts
        v
dashboard/ (Streamlit, Plotly)      each card has SQL | Table | Chart tabs
```

Layers, all in `src/ehr_analytics/`:

| Layer | Responsibility |
|---|---|
| `db.py`, `sql_loader.py` | read-only engine; loads and renders `.sql` templates |
| `filters.py` | whitelisted filters turned into bind parameters |
| `repositories/` | run a query, return data plus the exact SQL and parameters |
| `presenters/` | apply privacy rules and formatting |
| `privacy.py` | suppression, rounding, differencing checks |
| `charts/` | pure Plotly functions (light and dark themes) |

Precomputed summaries exist because scanning 27M to 33M rows per click is too slow. They store only counts and quartiles by drug or test, unit, admission type, age band, year and day of stay.

## SQL showcase

The queries use CTEs, window functions (`ROW_NUMBER`, `FIRST_VALUE`), `FILTER (WHERE ...)`, `GROUPING SETS` with `GROUPING()`, `PERCENTILE_CONT`, `width_bucket` histograms, `HAVING`, `EXISTS`, and `string_agg`. Open any card's **SQL** tab in the dashboard to see the exact query behind it.

## Dashboard pages

| Page | What it shows | Status |
|---|---|---|
| **Hospital Overview** | admissions, length of stay, admission types, discharge destinations, anchor-age groups | done |
| **Medication Analytics** | top drugs, orders vs stops, utilization, drug explorer (routes, spelling variants), co-ordering pairs and lift | done |
| **Lab Results Analytics** | most common tests, results by day of stay and year, value distributions, flag and value-type breakdown | done |
| **Methods & Privacy** | definitions, disclosure controls, security notes, known data quirks | done |
| Patient Cohort Explorer | filter a cohort and see aggregate statistics | planned |
| Transfers & Patient Journeys | care-unit flow and time per unit | planned |
| Data Quality & ETL Monitoring | the data issues listed below, as a monitoring page | planned |

## Project status

In progress or not done yet:

- The **three planned pages** above are not built. The sidebar lists them as "In development".
- **Privacy rules are provisional.** They have not been formally reviewed.
- **Lab medians ignore the dashboard filters** (precomputed over all admissions), and the lab day-of-stay and histogram views ignore the year filter.
- **Preprocessing issues found but not fixed** in `src/format.py` (see below). Fixing them means rerunning the preprocessing and import, which has deliberately not been done.
- No screenshots yet. They should be made from synthetic data.

### Known data quirks (found in the source file)

- **Every lab is flagged "abnormal"** (27.2M of 27.2M), so an abnormal rate cannot be computed. The dashboard reports it as "Not estimable".
- **About 578,000 lab results are the literal text `nan`**, a missing value written as text. The summaries count them as *missing results*, not text findings.
- **Lab names that differ only by capitalisation are merged** in the summaries (for example "Mesothelial cells" and "Mesothelial Cells").
- **Drug names were title-cased** by `format.py`, so some read oddly (`D5Ns` for D5NS). The dashboard shows them as stored.
- 132 admissions lack admit/discharge times and 157 have a discharge before admission. They are excluded from length-of-stay statistics only and are never modified or deleted.
- MIMIC shifts dates per patient, so calendar years are not real. Day of stay is the meaningful time axis.

## Setup

Requires Python 3.11 or newer and PostgreSQL (developed on 18).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (use source .venv/bin/activate elsewhere)
pip install -r requirements.txt
pip install -e .
copy .env.example .env             # then fill in YOUR passwords locally; never commit .env
```

### Build the data (needs MIMIC access; slow)

```bash
python src/format.py               # compressed raw data -> output.jsonl (large, local only)
psql -d ehr_analytics -f sql/schema.sql
python src/load_to_sql.py          # import into PostgreSQL (batched, resumable)
```

### Create the dashboard role and summaries

Review each file first, then run as a PostgreSQL administrator:

```bash
psql -d ehr_analytics -f sql/admin/001_dashboard_role.sql     # then: \password ehr_dashboard
psql -d ehr_analytics -f sql/analytics/001_schema_and_views.sql
psql -d ehr_analytics -f sql/analytics/002_medication_summaries.sql
psql -d ehr_analytics -f sql/analytics/003_grants.sql
psql -d ehr_analytics -f sql/analytics/004_lab_summaries.sql   # about 12 minutes
```

Put the `ehr_dashboard` password in `.env` as `DASHBOARD_DB_PASSWORD`. Summary files can be rebuilt with the `refresh_*` and `drop_lab_summaries.sql` scripts.

### Run the dashboard

```bash
streamlit run dashboard/app.py
```

Open http://localhost:8501. Pages whose summaries have not been built show a setup message instead of failing.

## Tests

```bash
pytest
```

Unit and page tests run against a **synthetic** database named `ehr_analytics_test` (create it with `sql/admin/002_test_database.sql`). The tests refuse to run against any other database, and they never touch real data. Tests that need the synthetic database are skipped if it is missing. Opt-in checks against the real database: `RUN_LIVE_DB_TESTS=1 pytest tests/test_live_dashboard.py`.

## Repository layout

```text
dashboard/            Streamlit app: app.py, views/ (pages), components/
src/ehr_analytics/    analytics package (db, filters, privacy, repositories, presenters, charts)
src/format.py         raw timelines -> cleaned JSONL
src/load_to_sql.py    JSONL -> PostgreSQL
src/*.py              diagnostics (inspect_mimic, validate_output, analyze_lab_failure)
sql/schema.sql        table definitions and indexes
sql/admin/            dashboard role and test database
sql/analytics/        precomputed summary views (aggregate-only)
sql/queries/          one folder of readable queries per dashboard page
tests/                pytest suite (synthetic data only)
data/synthetic_sample.jsonl   synthetic example record
patient_checker.py    small script for inspecting a few records
```

## Limitations

- Orders are not confirmed administrations, and names are never merged or mapped to a standard vocabulary.
- No reference ranges are inferred, so lab abnormality is only what the source flag says.
- Nothing here is clinical decision support. It is a data-engineering and analytics demonstration.

## Author

**Jonathan Betancourt**, Computer Science, University of Florida

Research interests: Healthcare Data Science, Biomedical Informatics, Machine Learning, Computational Genomics

[GitHub](https://github.com/jbetancourt589) | [LinkedIn](https://www.linkedin.com/in/jonathan-a-betancourt)
