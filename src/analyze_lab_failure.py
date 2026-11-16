"""Count laboratory events that format.py could not parse, grouped by reason.

format.py writes an unparsed LAB event as
    {"parse_status": "failed", "failure_reason": "<reason>"}
(older versions wrote None). Both shapes are counted here.

Reads output.jsonl locally; prints only aggregate counts, never record content.
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "output.jsonl"


def failure_reason(item):
    """Return the failure reason for an unparsed LAB item, or None if it parsed."""
    if item is None:
        return "unparsed (legacy None)"
    if isinstance(item, dict) and item.get("parse_status") == "failed":
        return item.get("failure_reason") or "unknown"
    return None


def main():
    failure_reasons = Counter()
    with OUTPUT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            for entry in record.get("timeline", []):
                for item in (entry.get("events") or {}).get("LAB", []):
                    reason = failure_reason(item)
                    if reason is not None:
                        failure_reasons[reason] += 1

    print("=== LAB PARSING FAILURE REPORT ===")
    print("Total unparsed labs:", sum(failure_reasons.values()))
    print("\nFailure categories:")
    for reason, count in failure_reasons.most_common():
        print(f"{reason}: {count}")


if __name__ == "__main__":
    main()
