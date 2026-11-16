-- =============================================================================
-- schema.sql — relational schema for the ehr_analytics database
-- =============================================================================
-- Synchronized with the live PostgreSQL 18 database (information_schema,
-- pg_constraint, pg_indexes) on 2026-11-12. Column order matches the live tables.
--
-- Grain of each table
--   patients        one row per patient (subject_id)
--   admissions      one row per hospital admission (hadm_id)
--   lab_results     one row per laboratory observation
--   medications     one row per medication ORDER or STOP event (not administrations)
--   transfers       one row per care-unit transfer event (direction IN / OUT)
--   clinical_notes  one row per note; discharge summaries use the discharge time
--   microbiology    one row per microbiology result text
--
-- Notes
--   * patients.age is MIMIC "anchor_age": the age in the patient's anchor year,
--     NOT necessarily the age at a given admission. Values > 89 are capped (91).
--   * Every child table references admissions(hadm_id). The child hadm_id
--     columns are nullable in the live database; the loader always sets them.
-- =============================================================================

-- PATIENTS --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    subject_id      BIGINT PRIMARY KEY,
    age             INTEGER,            -- MIMIC anchor_age
    gender          TEXT,
    race            TEXT,
    insurance       TEXT,
    marital_status  TEXT,
    language        TEXT
);

-- HOSPITAL ADMISSIONS ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS admissions (
    hadm_id             BIGINT PRIMARY KEY,
    subject_id          BIGINT NOT NULL REFERENCES patients (subject_id),
    admission_time      TIMESTAMP,
    discharge_time      TIMESTAMP,
    admission_type      TEXT,
    admission_location  TEXT,
    discharge_location  TEXT
);

-- LABORATORY RESULTS ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS lab_results (
    lab_id        BIGSERIAL PRIMARY KEY,
    hadm_id       BIGINT REFERENCES admissions (hadm_id),
    event_time    TIMESTAMP,
    lab_name      TEXT,
    value         DOUBLE PRECISION,   -- numeric results only; see operator for censoring
    units         TEXT,               -- parsed text after the number; NULL for text results
    flag          TEXT,               -- source flag, e.g. abnormal indicator
    ref_range     TEXT,               -- currently always NULL (no reference source)
    text_value    TEXT,               -- non-numeric results, kept verbatim for QA
    result_type   TEXT,               -- 'numeric' | 'text'
    operator      TEXT,               -- '<', '>', '<=', '>=' for censored values, else NULL
    derived_flag  TEXT                -- currently always NULL
);

-- MEDICATION EVENTS -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS medications (
    medication_id  BIGSERIAL PRIMARY KEY,
    hadm_id        BIGINT REFERENCES admissions (hadm_id),
    event_time     TIMESTAMP,
    event_type     TEXT,              -- 'MED_ORDER' | 'MED_STOP'
    drug           TEXT,
    dose           TEXT,
    route          TEXT
);

-- HOSPITAL TRANSFERS ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS transfers (
    transfer_id  BIGSERIAL PRIMARY KEY,
    hadm_id      BIGINT REFERENCES admissions (hadm_id),
    event_time   TIMESTAMP,
    direction    TEXT,                -- 'IN' | 'OUT'
    careunit     TEXT
);

-- CLINICAL NOTES --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clinical_notes (
    note_id     BIGSERIAL PRIMARY KEY,
    hadm_id     BIGINT REFERENCES admissions (hadm_id),
    event_time  TIMESTAMP,
    note_text   TEXT
);

-- MICROBIOLOGY ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS microbiology (
    microbiology_id  BIGSERIAL PRIMARY KEY,
    hadm_id          BIGINT REFERENCES admissions (hadm_id),
    event_time       TIMESTAMP,
    result_text      TEXT
);

-- INDEXES ON JOIN KEYS --------------------------------------------------------
-- PostgreSQL indexes primary keys automatically but NOT foreign-key columns.
-- These support admission-level joins and lookups from child tables.
CREATE INDEX IF NOT EXISTS idx_admissions_subject ON admissions     (subject_id);
CREATE INDEX IF NOT EXISTS idx_labs_hadm          ON lab_results    (hadm_id);
CREATE INDEX IF NOT EXISTS idx_meds_hadm          ON medications    (hadm_id);
CREATE INDEX IF NOT EXISTS idx_transfers_hadm     ON transfers      (hadm_id);
CREATE INDEX IF NOT EXISTS idx_notes_hadm         ON clinical_notes (hadm_id);
CREATE INDEX IF NOT EXISTS idx_micro_hadm         ON microbiology   (hadm_id);
