"""Stream MIMIC-derived admission timelines from JSONL.zst into cleaned JSONL.

Only run on data you're authorized to process in your local environment.
The output contains patient-level clinical records: do not commit or share it.
Requires: pip install zstandard
"""

import io
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import zstandard as zstd

# Works when this script lives either in src/ or at the project root.
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "src" else SCRIPT_DIR
INPUT_FILE = ROOT / "Compressed Raw Data" / "mimic_adm_timeline_text_train.jsonl.zst"
OUTPUT_FILE = ROOT / "output.jsonl"
MAX_RECORDS = None  # Change to None only after validating the test run.

# Your current .zst records expose event time/type/text; reference ranges
# are not established from those fields. Do not infer reference ranges.
REF_LOOKUP = {}

LAB_PATTERN = re.compile(r"^\s*LAB:\s*(.+?)\s*=\s*(.*?)\s*$", re.I | re.S)
FLAG_PATTERN = re.compile(r"\s*\[flag=([^\]]*)\]\s*$", re.I)
NUMBER_PATTERN = re.compile(
    r"^\s*([<>]=?)?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\s+(.*))?\s*$"
)


def parse_time(value):
    """Return datetime or None for a missing/invalid time."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def normalize_drug_name(name):
    return name.strip().lstrip(":").strip().title()


def parse_med(text):
    if not isinstance(text, str):
        return "MED_ORDER", {"drug": None, "dose": None, "route": None}
    category = "MED_STOP" if "MED STOP" in text.upper() else "MED_ORDER"
    clean_text = re.sub(r"\bMED\s+(?:STOP|ORDER)\b", "", text, flags=re.I).strip()
    drug = normalize_drug_name(clean_text.split("(", 1)[0]) or None
    dose_match = re.search(r"\bdose\s*=\s*([^,)]+)", clean_text, re.I)
    route_match = re.search(r"\broute\s*=\s*([^,)]+)", clean_text, re.I)
    return category, {
        "drug": drug,
        "dose": dose_match.group(1).strip() if dose_match else None,
        "route": route_match.group(1).strip() if route_match else None,
    }


def classify_lab_failure(text):
    if not isinstance(text, str) or not text.strip():
        return "missing_text"
    match = LAB_PATTERN.match(text)
    if not match:
        return "invalid_format"
    result = FLAG_PATTERN.sub("", match.group(2)).strip()
    return "missing_result" if not result else "other_unparsed"


def parse_lab(text):
    """Parse numeric labs and preserve text-only results without inventing numbers."""
    if not isinstance(text, str):
        return "LAB", None
    match = LAB_PATTERN.match(text)
    if not match:
        return "LAB", None

    lab_name = match.group(1).strip()
    result_text = match.group(2).strip()
    flag_match = FLAG_PATTERN.search(result_text)
    flag = flag_match.group(1).strip() if flag_match else None
    if flag_match:
        result_text = result_text[:flag_match.start()].strip()
    if not lab_name or not result_text:
        return "LAB", None

    ref_info = REF_LOOKUP.get(lab_name, {})
    value_match = NUMBER_PATTERN.fullmatch(result_text)
    common = {
        "lab_name": lab_name,
        "flag": flag,
        "ref_range": ref_info.get("ref_range"),
        "derived_flag": ref_info.get("derived_flag"),
    }

    if value_match:
        return "LAB", {
            **common,
            "value": float(value_match.group(2)),
            "text_value": None,
            "units": (value_match.group(3) or "").strip() or None,
            "operator": value_match.group(1),
            "result_type": "numeric",
        }

    # Non-numeric is not necessarily a valid categorical result.
    # Retain as text for subsequent classification / QA.
    return "LAB", {
        **common,
        "value": None,
        "text_value": result_text,
        "units": None,
        "operator": None,
        "result_type": "text",
    }


def parse_transfer(text):
    if not isinstance(text, str):
        return {"direction": None, "careunit": None}
    direction_match = re.match(r"^TRANSFER\s+(IN|OUT)\b", text, re.I)
    unit_match = re.search(r"\bcareunit\s*=\s*(.*)$", text, re.I)
    return {
        "direction": direction_match.group(1).upper() if direction_match else None,
        "careunit": unit_match.group(1).strip() if unit_match else None,
    }


def clean_note(text):
    if not isinstance(text, str):
        return None
    text = re.sub(r"(?:\\n|/n)+", "\n", text, flags=re.I)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    half = len(text) // 2
    if len(text) % 2 == 0 and text[:half] == text[half:]:
        text = text[:half]
    headings = (
        "NOTES|INDICATION|COMPARISON|TECHNIQUE|FINDINGS|IMPRESSION|"
        "Chief Complaint|Major Surgical or Invasive Procedure|History of Present Illness|"
        "Past Medical History|Social History|Family History|Physical Exam|"
        "Pertinent Results|Brief Hospital Course|Medications on Admission|"
        "Discharge Medications|Discharge Disposition|Facility|Discharge Diagnosis|"
        "Discharge Condition|Discharge Instructions|Followup Instructions"
    )
    text = re.sub(rf"\s*({headings}):", r"\n\1:", text, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean_patient(raw, stats=None):
    context = raw.get("context") or {}
    patient_info = {
        "subject_id": raw.get("subject_id"),
        "hadm_id": raw.get("hadm_id"),
        "age": context.get("anchor_age"),
        "gender": context.get("gender"),
        "race": context.get("race"),
        "insurance": context.get("insurance"),
        "marital_status": context.get("marital_status"),
        "language": context.get("language"),
    }
    if patient_info["subject_id"] is None or patient_info["hadm_id"] is None:
        raise ValueError("missing patient or admission identifier")

    admission = {
        "time": context.get("admittime"),
        "category": "ADMISSION",
        "data": {
            "admission_type": context.get("admission_type"),
            "admission_location": context.get("admission_location"),
        },
        "notes": None,
    }
    discharge = {
        "time": context.get("dischtime"),
        "category": "DISCHARGE",
        "data": {"discharge_location": context.get("discharge_location")},
        "notes": None,
    }

    grouped = {}
    seen = set()
    for event in raw.get("events") or []:
        if not isinstance(event, dict):
            if stats is not None:
                stats["non_dict_events"] += 1
            continue
        event_time = event.get("time")
        category = event.get("type")
        event_text = event.get("text")
        # Keep original record-level deduplication semantics.
        key = (event_time, category, event_text)
        if key in seen:
            if stats is not None:
                stats["duplicate_events"] += 1
            continue
        seen.add(key)

        if stats is not None and event_time is not None and parse_time(event_time) is None:
            stats["invalid_event_timestamps"] += 1

        data = None
        if category == "MED":
            category, data = parse_med(event_text)
        elif category == "LAB":
            _, data = parse_lab(event_text)
            if stats is not None:
                stats["lab_" + (data.get("result_type") if data else "failed")] += 1
            if data is None:
                data = {
                    "parse_status": "failed",
                    "failure_reason": classify_lab_failure(event_text),
                }
        elif category == "TRANSFER":
            data = parse_transfer(event_text)
        elif category == "NOTE":
            data = clean_note(event_text)
        else:
            # Preserve MICRO and other categories rather than dropping their text.
            data = {"text": event_text} if isinstance(event_text, str) else {"text": None}

        bucket = grouped.setdefault(event_time, {"time": event_time, "events": {}})
        items = bucket["events"].setdefault(category, [])
        if category == "NOTE":
            if data and data not in items:
                items.append(data)
        else:
            items.append(data)

    # Attach discharge summary to the discharge event, as in your original format.py.
    for bucket in sorted(grouped.values(), key=lambda x: (parse_time(x["time"]) is None, parse_time(x["time"]) or datetime.max)):
        notes = bucket["events"].get("NOTE", [])
        discharge_notes = [note for note in notes if note and "[DISCHARGE]" in note[:20]]
        if discharge_notes:
            discharge["notes"] = discharge_notes[0]
            remaining = [note for note in notes if note not in discharge_notes]
            if remaining:
                bucket["events"]["NOTE"] = remaining
            else:
                del bucket["events"]["NOTE"]
            break

    timeline = [admission]
    for bucket in sorted(grouped.values(), key=lambda x: (parse_time(x["time"]) is None, parse_time(x["time"]) or datetime.max)):
        bucket["events"] = {k: v for k, v in bucket["events"].items() if v}
        if bucket["events"]:
            timeline.append(bucket)
    timeline.append(discharge)
    return {"patient_info": patient_info, "timeline": timeline}


def main():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(f"Dataset not found: {INPUT_FILE}")
    print("Input:", INPUT_FILE.name)
    print("Output:", OUTPUT_FILE.name)
    print("Record limit:", MAX_RECORDS if MAX_RECORDS is not None else "full dataset")

    stats = Counter()
    with INPUT_FILE.open("rb") as compressed_file:
        decompressor = zstd.ZstdDecompressor()
        with decompressor.stream_reader(compressed_file) as reader:
            with io.TextIOWrapper(reader, encoding="utf-8") as input_stream:
                with OUTPUT_FILE.open("w", encoding="utf-8") as output_stream:
                    for line_number, line in enumerate(input_stream, start=1):
                        if MAX_RECORDS is not None and stats["processed"] + stats["failed"] >= MAX_RECORDS:
                            break
                        if not line.strip():
                            stats["blank_lines"] += 1
                            continue
                        try:
                            record = json.loads(line)
                            if not isinstance(record, dict):
                                raise ValueError("record is not a JSON object")
                            # Use per-record counters, so failed records don't inflate metrics.
                            record_stats = Counter()
                            cleaned = clean_patient(record, record_stats)
                            serialized = json.dumps(cleaned, ensure_ascii=False)
                            output_stream.write(serialized + "\n")
                            stats.update(record_stats)
                            stats["processed"] += 1
                        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
                            stats["failed"] += 1
                            stats["error_" + type(exc).__name__] += 1
                            # Never print raw patient data or clinical text.
                            print(f"Input line {line_number}: {type(exc).__name__}")
                        if stats["processed"] and stats["processed"] % 10000 == 0:
                            print(f"Processed {stats['processed']:,} records")

    print("\n=== PREPROCESSING SUMMARY ===")
    for key in ("processed", "failed", "duplicate_events", "invalid_event_timestamps", "lab_numeric", "lab_text", "lab_failed"):
        print(f"{key}: {stats[key]}")
    print("Finished. Output:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
