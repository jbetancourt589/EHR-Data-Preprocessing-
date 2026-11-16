
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "output.jsonl"

# If PyCharm saved output.jsonl elsewhere, adjust this path to its actual location.

categories = Counter()
total_records = 0
total_events = 0
missing_times = 0
missing_labs = 0
unique_patients = set()
unique_admissions = set()
failure_reasons = Counter()
lab_types = Counter()

with OUTPUT_FILE.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue

        record = json.loads(line)
        total_records += 1

        info = record.get("patient_info", {})
        unique_patients.add(info.get("subject_id"))
        unique_admissions.add(info.get("hadm_id"))

        for entry in record.get("timeline", []):
            if not entry.get("time"):
                missing_times += 1

            if "events" in entry:
                for category, items in entry["events"].items():
                    categories[category] += len(items)
                    total_events += len(items)

                    if category == "LAB":
                        for item in items:
                            if isinstance(item, dict) and item.get("parse_status") == "failed":
                                # format.py marks unparsed labs this way
                                missing_labs += 1
                                failure_reasons[item.get("failure_reason") or "unknown"] += 1
                                lab_types["failed"] += 1
                            elif isinstance(item, dict):
                                lab_types[item.get("result_type", "unknown")] += 1
                            else:
                                missing_labs += 1
                                failure_reasons["unparsed (legacy None)"] += 1
                                lab_types["unknown"] += 1

print("=== EHR PREPROCESSING VALIDATION ===")
print("Records processed:", total_records)
print("Unique patients:", len(unique_patients))
print("Unique admissions:", len(unique_admissions))
print("Clinical events:", total_events)
print("Timeline entries missing timestamps:", missing_times)
print("Unparsed laboratory events:", missing_labs)

print("\nEvent categories:")
for category, count in categories.most_common():
    print(f"  {category}: {count}")

print("\n=== LAB FAILURE REASONS ===")

for reason, count in failure_reasons.most_common():
    print(f"{reason}: {count}")

print("\n=== LAB RESULT TYPES ===")

for result_type, count in lab_types.most_common():
    print(f"{result_type}: {count}")

