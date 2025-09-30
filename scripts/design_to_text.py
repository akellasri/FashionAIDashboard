#!/usr/bin/env python3
# design_to_text.py
"""
Utility: Print the `design_text` field from a design JSON.
Assumes apply_text_change.py (or design generation) has already inserted it.
"""
import json
import sys
from pathlib import Path


def main(argv):
    if len(argv) < 2:
        print("Usage: python design_to_text.py path/to/design.json", file=sys.stderr)
        return 2

    path = Path(argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 3

    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:
        print(f"Failed to read/parse JSON: {e}", file=sys.stderr)
        return 4

    txt = d.get("design_text")
    if not txt:
        print("[no design_text field found in JSON]")
    else:
        # print as-is (may be multi-line)
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
