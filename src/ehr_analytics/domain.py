"""Shared domain constants.

These mirror the labels produced by sql/queries/overview/_base.sql. If a label
changes there it must change here too; tests check that the two agree.
"""

NOT_RECORDED = "Not recorded"

# Display order for anchor-age bands (alphabetical order would be wrong).
AGE_GROUP_ORDER: tuple[str, ...] = (
    "<18",
    "18–29",
    "30–39",
    "40–49",
    "50–59",
    "60–69",
    "70–79",
    "80–89",
    "90+ (capped)",
    NOT_RECORDED,
)

# Length-of-stay validity categories (see _base.sql).
LOS_VALID = "valid"
LOS_MISSING = "missing_timestamp"
LOS_NEGATIVE = "negative_duration"

# Stays at or beyond this many days share one histogram overflow bin.
LOS_HISTOGRAM_CAP_DAYS = 30

# --------------------------------------------------------------------- medications
# Orders-per-admission bands, matching the CASE in
# sql/analytics/002_medication_summaries.sql (med_admission_profile).
ORDERS_BUCKET_LABELS: dict[int, str] = {
    0: "0",
    1: "1–9",
    2: "10–24",
    3: "25–49",
    4: "50–99",
    5: "100–199",
    6: "200+",
}

# Mirrors analytics.medication_placeholders (tests check they agree).
MEDICATION_PLACEHOLDERS: tuple[str, ...] = (
    "Bag",
    "Vial",
    "Syringe",
    "Click Change <--- To Choose A Base Solution",
    "Click Change To Choose A Base Solution",
)

# Analytics objects the Medication page needs (built by sql/analytics/*.sql).
MEDICATION_ANALYTICS_OBJECTS: tuple[str, ...] = (
    "analytics.med_drug_cell",
    "analytics.med_admission_profile",
    "analytics.med_route_summary",
    "analytics.med_pair_summary",
    "analytics.medication_names",
    "analytics.med_pair_metrics",
)

MEDICATION_ORDER_NOTE = (
    "A **medication order** (MED_ORDER) is a prescription entered for the patient. "
    "It is **not** proof the drug was given — administrations are not in this "
    "dataset. A **stop event** (MED_STOP) records that an order was discontinued. "
    "Most orders have a matching stop in the same admission; an order without one "
    "was usually still active at discharge."
)

ANCHOR_AGE_NOTE = (
    "Anchor age is MIMIC's de-identified `anchor_age`: the patient's age in their "
    "anchor year, not necessarily their exact age at a given admission. Ages above "
    "89 are capped (recorded as 91)."
)

# --------------------------------------------------------------------------- labs
# Analytics objects the Lab page needs (built by sql/analytics/004_lab_summaries.sql).
LAB_ANALYTICS_OBJECTS: tuple[str, ...] = (
    "analytics.lab_cell",
    "analytics.lab_admission_profile",
    "analytics.lab_day_counts",
    "analytics.lab_value_trend",
    "analytics.lab_value_bounds",
    "analytics.lab_value_histogram",
    "analytics.lab_tests",
)

LAB_HISTOGRAM_BINS = 30           # equal-width bins between p1 and p99 (+ 2 overflow bins)
LAB_HISTOGRAM_MIN_RESULTS = 1000  # matches HAVING COUNT(*) >= 1000 in lab_value_bounds
LAB_DAY_MIN, LAB_DAY_MAX = -1, 30  # -1 = before admission, 30 = day 30 or later

LAB_FLAG_NOTE = (
    "The `flag` column is used exactly as recorded. Only explicit values are "
    "classified ('abnormal', 'normal'); a blank flag means the result was not "
    "flagged, which is **not** the same as normal. No reference ranges are "
    "inferred: `ref_range` and `derived_flag` are empty in this dataset."
)

LAB_QUIRKS_NOTE = (
    "**Known data quirks (found in the source file, not created by the dashboard):** "
    "(1) Every lab is flagged 'abnormal', so no abnormal rate can be computed. "
    "(2) About 578,000 results (≈2% of all labs) are the literal text 'nan' (e.g. "
    "'nan nan'): the source wrote a missing value as text. They are counted separately as "
    "**missing results** and are never treated as text findings. "
    "(3) Lab names that differ only by capitalisation (e.g. 'Mesothelial cells' vs "
    "'Mesothelial Cells') are merged into the most frequent spelling. "
    "(4) Drug names on the Medication page were title-cased during preprocessing, "
    "so some read oddly (e.g. 'D5Ns' for D5NS); they are shown as stored."
)

LAB_DATE_NOTE = (
    "MIMIC shifts every patient's dates by a random offset for de-identification, "
    "so years (2105–2214) are not real calendar years. **Day of stay** is "
    "unaffected by the shift and is the meaningful time axis."
)
