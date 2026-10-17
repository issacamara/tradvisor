#!/usr/bin/env python3
"""Canonical ticket dataset interface; generated backlog remains JSON-owned."""
import json
from pathlib import Path

def tickets():
    return json.loads((Path(__file__).parent / "backlog.json").read_text())["tickets"]

if __name__ == "__main__":
    print(json.dumps(tickets(), indent=2))
