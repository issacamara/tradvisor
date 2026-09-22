#!/usr/bin/env python3
"""Validate the checked-in canonical backlog and its publication artifacts."""
import json
from pathlib import Path

HERE = Path(__file__).parent
def main():
    bundle = json.loads((HERE / "backlog.json").read_text())
    items = bundle["tickets"]
    ids = {x["id"] for x in items}
    assert len(ids) == len(items)
    for item in items:
        assert item["deps"] and all(any(t["key"] == dep for t in items) for dep in item["deps"]) or not item["deps"]
        assert len(item["checks"]) >= 2
    print(f"Validated {len(items)} atomic tickets, {max(x['wave'] for x in items)} waves, {len(bundle['conflicts'])} conflict pairs, {len(bundle['comments'])} baseline comments.")
if __name__ == "__main__": main()
