"""Reference page — definitions, data sources, and disclosure-control rules."""

from __future__ import annotations

import streamlit as st

from components.ui import page_header
from ehr_analytics.domain import ANCHOR_AGE_NOTE, LAB_QUIRKS_NOTE, LOS_HISTOGRAM_CAP_DAYS
from ehr_analytics.privacy import ROUNDING_BASE, SMALL_CELL_THRESHOLD, STATISTIC_MIN_N

page_header(
    "Reference",
    "Methods & Privacy",
    "How the numbers on each page are defined, computed, and protected.",
)

col_left, col_right = st.columns(2, gap="large")

with col_left:
    st.subheader("Data pipeline", anchor=False)
    st.markdown(
        """
1. **Source** — MIMIC-derived admission timelines (`.jsonl.zst`, streamed).
2. **Preprocessing** (`src/format.py`) — parses medications, labs, transfers,
   notes, and microbiology; removes duplicate events; orders timelines.
3. **Load** (`src/load_to_sql.py`) — batched, transactional, resumable import
   into seven PostgreSQL tables.
4. **Analytics** — every dashboard figure is an aggregate SQL query in
   `sql/queries/`, executed by a read-only database role.
"""
    )
    st.subheader("Definitions", anchor=False)
    st.markdown(
        f"""
- **Admission** — one `hadm_id`. **Patient** — one `subject_id`.
- **Length of stay (LOS)** — `discharge_time − admission_time` in days.
- **Valid stay** — both timestamps present and discharge ≥ admission.
  Zero-length stays are valid. Missing or negative stays are **excluded from
  LOS statistics only**; the records are never modified or deleted, and they
  remain in every count.
- **Anchor age** — {ANCHOR_AGE_NOTE}
- **'Not recorded'** — the source field is NULL. It is shown as its own
  category so it cannot silently inflate the other categories' shares.
- **Histogram overflow** — stays ≥ {LOS_HISTOGRAM_CAP_DAYS} days share the last bin.
- **Dates** — MIMIC shifts dates per patient, so calendar trends are not shown.
"""
    )

    st.subheader("Medication definitions", anchor=False)
    st.markdown(
        """
- **Order** (`MED_ORDER`) — a prescription entered; **not** a confirmed
  administration. **Stop** (`MED_STOP`) — the order was discontinued.
- **Names** are used exactly as recorded and never merged. `*Nf*` marks a
  non-formulary item. Related spellings are shown side by side in the explorer.
- **Container placeholders** (Bag, Vial, Syringe, "Click Change…") are flagged in
  `analytics.medication_placeholders` and excluded by default.
- **Co-ordering** — two drugs both ordered at least once in the same admission
  (not necessarily simultaneously), among the 100 most widely ordered drugs.
  **Lift** = P(A and B) / (P(A)·P(B)); above 1 means more often than chance.
- **Precomputed summaries** (`sql/analytics/`) store only aggregate counts by
  drug, admission type and age band — no identifiers, timestamps or doses.
"""
    )

    st.subheader("Lab definitions", anchor=False)
    st.markdown(
        """
- **Units** — every numeric statistic is grouped by test **and** unit; values in
  different units (e.g. MCHC in g/dL vs %) are never combined. A blank unit is
  shown as "Not recorded".
- **Censored** results (`<`, `>`, `<=`, `>=`) are counted but excluded from
  medians and histograms: the number is a detection limit, not a measurement.
  **Text** results are counted, never interpreted.
- **Flags** are used as recorded; a blank flag is "not flagged", not normal. No
  reference ranges are inferred. In this extract every result is flagged
  "abnormal", so an abnormal *rate* is reported as **not estimable**.
- **Day of stay** — whole days from admission (−1 = before admission, 30 = 30+).
  Unlike calendar years, it is unaffected by MIMIC's per-patient date shifting.
- **Histograms** — 30 bins between the 1st and 99th percentiles (built only for
  test–units with ≥ 1,000 numeric results); extreme values fall in end bins.
"""
    )

    st.subheader("Known data quirks", anchor=False)
    st.markdown(LAB_QUIRKS_NOTE)

with col_right:
    st.subheader("Disclosure controls", anchor=False)
    st.markdown(
        f"""
These are **provisional safeguards** for a local research tool. They reduce, but
do not formally eliminate, re-identification risk and are **not** proof of
MIMIC/PhysioNet compliance.

1. **Small cells** — counts of 1–{SMALL_CELL_THRESHOLD - 1} are shown as
   "<{SMALL_CELL_THRESHOLD}" or merged into *Other (small groups)*.
2. **Complementary suppression** — where exact counts are shown, if a hidden
   cell could be recovered by subtracting the visible cells from a known total,
   the next-smallest cell is hidden too. Breakdowns merge small groups into
   *Other (small groups)*, which is itself suppressed if under 11. Rounded
   counts can't be subtracted to an exact value, so large groups are never
   hidden to protect a small one.
3. **Rounding** — breakdown counts and all filtered-cohort counts are rounded to
   the nearest {ROUNDING_BASE}; percentages are computed from the rounded counts.
   Rounding is deterministic, so repeating a query reveals nothing new.
4. **Filter differencing** — a filtered cohort must contain ≥ {SMALL_CELL_THRESHOLD}
   admissions and must leave out either none or ≥ {SMALL_CELL_THRESHOLD}.
5. **Statistics** — means and percentiles need ≥ {STATISTIC_MIN_N} valid stays;
   minima and maxima are never shown.
6. **No patient-level data** — no identifiers, individual encounters, or
   clinical notes are displayed. The dashboard's database role cannot read
   `clinical_notes` at all.
"""
    )
    st.subheader("Security", anchor=False)
    st.markdown(
        """
- The app binds to **localhost** only and sends no usage telemetry.
- It connects as `ehr_dashboard`: SELECT-only, read-only transactions,
  15-second statement timeout, and it refuses to start as a superuser.
- Filter values are sent as **bind parameters**, never inserted into SQL text;
  column names come from a fixed whitelist. There is no free-form SQL input.
"""
    )
