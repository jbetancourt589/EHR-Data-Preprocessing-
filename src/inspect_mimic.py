
import json
from pathlib import Path
import zstandard as zstd

ROOT = Path(__file__).resolve().parent.parent

file_path = (
    ROOT
    / "Compressed Raw Data"
    / "mimic_adm_timeline_text_train.jsonl.zst"
)

with open(file_path, "rb") as f:
    dctx = zstd.ZstdDecompressor()

    with dctx.stream_reader(f) as reader:
        import io
        text_reader = io.TextIOWrapper(reader, encoding="utf-8")

        first_line = text_reader.readline()
        record = json.loads(first_line)

        print("Top-level fields:")
        print(list(record.keys()))

        print("\nContext fields:")
        context = record.get("context", {})
        if isinstance(context, dict):
            print(list(context.keys()))

        print("\nNumber of events in first record:")
        events = record.get("events", [])
        print(len(events) if isinstance(events, list) else "Not a list")

        if isinstance(events, list) and events:
            print("\nFirst event fields:")
            print(list(events[0].keys()))
