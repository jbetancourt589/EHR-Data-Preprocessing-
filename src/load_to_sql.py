"""Batch-import cleaned MIMIC timeline JSONL into the existing ehr_analytics schema.

Run only on a local machine/environment approved for storing MIMIC-derived data.
Requires: sqlalchemy, psycopg, python-dotenv. Never commit source/output data or .env.

Place this script at: <project>/src/load_to_sql.py
Expected input:     <project>/output.jsonl, created by corrected format.py

Design:
- Reads JSONL incrementally, not all into memory.
- Batches up to BATCH_SIZE admissions; uses SQLAlchemy executemany per table.
- Each batch is a transaction: it either commits fully or rolls back fully.
- Skips previously imported hadm_id values for safe reruns.
- Does not print source records, notes, or patient/admission identifiers.
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import bindparam, text
from db_connection import engine

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT / "output.jsonl"
BATCH_SIZE = 100  # Admissions per database transaction; increase cautiously later.
PROGRESS_EVERY = 1000

TABLE_COLUMNS = {
    "patients": ("subject_id", "age", "gender", "race", "insurance", "marital_status", "language"),
    "admissions": ("hadm_id", "subject_id", "admission_time", "discharge_time", "admission_type", "admission_location", "discharge_location"),
    "lab_results": ("hadm_id", "event_time", "lab_name", "value", "text_value", "units", "flag", "ref_range", "derived_flag", "result_type", "operator"),
    "medications": ("hadm_id", "event_time", "event_type", "drug", "dose", "route"),
    "transfers": ("hadm_id", "event_time", "direction", "careunit"),
    "clinical_notes": ("hadm_id", "event_time", "note_text"),
    "microbiology": ("hadm_id", "event_time", "result_text"),
}

# Explicit columns reduce risk of schema drift and permit SQLAlchemy executemany.
INSERTS = {
    table: text(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(':' + c for c in columns)})"
    )
    for table, columns in TABLE_COLUMNS.items()
}
PATIENT_INSERT = text("""
    INSERT INTO patients (subject_id, age, gender, race, insurance, marital_status, language)
    VALUES (:subject_id, :age, :gender, :race, :insurance, :marital_status, :language)
    ON CONFLICT (subject_id) DO NOTHING
""")
FIND_EXISTING = text("SELECT hadm_id FROM admissions WHERE hadm_id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)


def parse_time(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("timestamp has unsupported type")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is not None:
        raise ValueError("timezone-aware timestamp requires explicit handling")
    return parsed


def as_row(table, fields):
    return {column: fields.get(column) for column in TABLE_COLUMNS[table]}


def prepare_record(record):
    """Convert one preprocessed JSONL record to 7 sets of table rows."""
    if not isinstance(record, dict):
        raise ValueError("record is not a JSON object")
    info = record.get("patient_info")
    timeline = record.get("timeline")
    if not isinstance(info, dict) or not isinstance(timeline, list):
        raise ValueError("missing patient_info or timeline")
    sid, aid = info.get("subject_id"), info.get("hadm_id")
    if not isinstance(sid, int) or isinstance(sid, bool) or not isinstance(aid, int) or isinstance(aid, bool):
        raise ValueError("missing or invalid subject_id/hadm_id")

    admission = next((e for e in timeline if isinstance(e, dict) and e.get("category") == "ADMISSION"), None)
    discharge = next((e for e in timeline if isinstance(e, dict) and e.get("category") == "DISCHARGE"), None)
    if admission is None or discharge is None:
        raise ValueError("missing admission/discharge event")
    admission_data, discharge_data = admission.get("data") or {}, discharge.get("data") or {}
    if not isinstance(admission_data, dict) or not isinstance(discharge_data, dict):
        raise ValueError("invalid admission/discharge fields")

    rows = {table: [] for table in TABLE_COLUMNS}
    rows["patients"].append(as_row("patients", info))
    rows["admissions"].append(as_row("admissions", {
        "hadm_id": aid,
        "subject_id": sid,
        "admission_time": parse_time(admission.get("time")),
        "discharge_time": parse_time(discharge.get("time")),
        "admission_type": admission_data.get("admission_type"),
        "admission_location": admission_data.get("admission_location"),
        "discharge_location": discharge_data.get("discharge_location"),
    }))
    if isinstance(discharge.get("notes"), str) and discharge["notes"]:
        rows["clinical_notes"].append(as_row("clinical_notes", {
            "hadm_id": aid, "event_time": parse_time(discharge.get("time")),
            "note_text": discharge["notes"]
        }))

    counts = Counter()
    for entry in timeline:
        if not isinstance(entry, dict):
            raise ValueError("invalid timeline entry")
        events = entry.get("events")
        if not events:
            continue
        if not isinstance(events, dict):
            raise ValueError("invalid events grouping")
        event_time = parse_time(entry.get("time"))
        for category, items in events.items():
            if not isinstance(items, list):
                raise ValueError("event category does not contain list")
            for item in items:
                base = {"hadm_id": aid, "event_time": event_time}
                if category == "LAB":
                    if not isinstance(item, dict):
                        raise ValueError("invalid LAB item")
                    if item.get("parse_status") == "failed":
                        # Existing SQL lab schema has no parse-failure metadata fields.
                        counts["unloaded_lab_failures"] += 1
                        continue
                    if not item.get("lab_name"):
                        raise ValueError("lab missing name")
                    rows["lab_results"].append(as_row("lab_results", {**base, **item}))
                elif category in ("MED_ORDER", "MED_STOP"):
                    if not isinstance(item, dict):
                        raise ValueError("invalid medication item")
                    rows["medications"].append(as_row("medications", {
                        **base, "event_type": category, "drug": item.get("drug"),
                        "dose": item.get("dose"), "route": item.get("route"),
                    }))
                elif category == "TRANSFER":
                    if not isinstance(item, dict):
                        raise ValueError("invalid transfer item")
                    rows["transfers"].append(as_row("transfers", {**base, **item}))
                elif category == "NOTE":
                    if not isinstance(item, str):
                        raise ValueError("invalid note item")
                    rows["clinical_notes"].append(as_row("clinical_notes", {
                        **base, "note_text": item,
                    }))
                elif category == "MICRO":
                    result_text = item.get("text") if isinstance(item, dict) else item if isinstance(item, str) else None
                    rows["microbiology"].append(as_row("microbiology", {
                        **base, "result_text": result_text,
                    }))
                else:
                    # Make unsupported categories visible; do not falsely claim complete import.
                    counts["unsupported_" + str(category)] += 1
    return aid, rows, counts


def import_batch(batch):
    """Return counters for a fully committed batch, or raise and roll back."""
    counts = Counter()
    if not batch:
        return counts
    ids = [item[0] for item in batch]
    with engine.begin() as connection:
        present = set(connection.execute(FIND_EXISTING, {"ids": ids}).scalars())
        new_items = [item for item in batch if item[0] not in present]
        counts["existing_admissions"] = len(batch) - len(new_items)
        if not new_items:
            return counts

        grouped = {table: [] for table in TABLE_COLUMNS}
        for _, rows, warnings in new_items:
            for table, entries in rows.items():
                grouped[table].extend(entries)
            counts.update(warnings)
        # Patient demographics are keyed by subject_id; do not insert the same patient twice.
        unique_patients = {row["subject_id"]: row for row in grouped["patients"]}
        if unique_patients:
            connection.execute(PATIENT_INSERT, list(unique_patients.values()))
        for table in ("admissions", "lab_results", "medications", "transfers", "clinical_notes", "microbiology"):
            if grouped[table]:
                connection.execute(INSERTS[table], grouped[table])
                counts[table + "_inserted"] += len(grouped[table])
        counts["imported_admissions"] = len(new_items)
    return counts


def main():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(f"Processed output not found: {INPUT_FILE}")

    totals = Counter()
    batch = []
    batch_ids = set()
    last_progress = 0
    print("Loading cleaned output.jsonl into PostgreSQL...")
    print(f"Batch size: {BATCH_SIZE} admissions")
    with INPUT_FILE.open("r", encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                totals["blank_lines"] += 1
                continue
            try:
                prepared = prepare_record(json.loads(line))
                if prepared[0] in batch_ids:
                    totals["duplicate_admissions_in_input"] += 1
                    continue
                batch.append(prepared)
                batch_ids.add(prepared[0])
                totals["valid_input_records"] += 1
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                totals["invalid_input_records"] += 1
                totals["input_" + type(exc).__name__] += 1
                # Do not print IDs or clinical text.
                print(f"Input line {line_no}: skipped ({type(exc).__name__})")
                continue

            if len(batch) >= BATCH_SIZE:
                totals.update(import_batch(batch))
                batch.clear()
                batch_ids.clear()
                if totals["valid_input_records"] - last_progress >= PROGRESS_EVERY:
                    print(f"Read from output: {totals['valid_input_records']:,}; "
                          f"newly imported: {totals['imported_admissions']:,}; "
                          f"already in database (skipped): {totals['existing_admissions']:,}")
                    last_progress = totals["valid_input_records"]

        if batch:
            totals.update(import_batch(batch))

    print("\n=== SQL IMPORT SUMMARY ===")
    for name in (
        "valid_input_records", "imported_admissions", "existing_admissions",
        "duplicate_admissions_in_input", "invalid_input_records", "unloaded_lab_failures",
        "lab_results_inserted", "medications_inserted", "transfers_inserted",
        "clinical_notes_inserted", "microbiology_inserted",
    ):
        print(f"{name}: {totals[name]}")
    for name in sorted(k for k in totals if k.startswith("unsupported_")):
        print(f"{name}: {totals[name]}")


if __name__ == "__main__":
    main()


