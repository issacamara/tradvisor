#!/usr/bin/env python3
"""Select implementation models and persist confirmed failure attempts."""
import json, os, re, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
BACKLOG = json.loads((HERE / "backlog.json").read_text())
SOL, TERRA = "gpt-5.6-sol", "gpt-5.6-terra"
LEDGER = HERE.parent / ".agent-runs" / "ticket-failures.json"

def ticket(ticket_id):
    for item in BACKLOG["tickets"]:
        if item["id"] == ticket_id: return item
    raise ValueError(f"Unknown ticket: {ticket_id}")

def read_failures(path=LEDGER):
    return json.loads(Path(path).read_text()) if Path(path).exists() else {}

def record_failure(ticket_id, attempt_id, path=LEDGER):
    ticket(ticket_id)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{5,127}", attempt_id):
        raise ValueError("Invalid attempt ID")
    failures = read_failures(path)
    attempts = failures.get(ticket_id, [])
    if attempt_id in attempts: return len(attempts)
    failures[ticket_id] = attempts + [attempt_id]
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".")
    with os.fdopen(fd, "w") as handle: json.dump(failures, handle, indent=2); handle.write("\n")
    os.replace(temporary, target)
    return len(failures[ticket_id])

def for_ticket(item, failures=None):
    count = len((failures or read_failures()).get(item["id"], []))
    upgraded = count >= 2
    return {"issue": item["id"], "failed_implementation_attempts": count,
            "implementation_model": SOL if upgraded else TERRA,
            "implementation_effort": "high" if upgraded else "medium",
            "review_model": TERRA, "review_effort": "high",
            "reason": "two or more confirmed implementation failures" if upgraded else "Terra default"}

if __name__ == "__main__":
    if sys.argv[1:2] == ["record-failure"]:
        print(record_failure(sys.argv[2], sys.argv[3]))
    else:
        print(json.dumps(for_ticket(ticket(sys.argv[1])), indent=2))
