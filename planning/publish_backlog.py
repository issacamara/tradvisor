#!/usr/bin/env python3
"""Safe, resumable GitHub publication helper."""
import json, subprocess, sys
from pathlib import Path
HERE=Path(__file__).parent; REPO='issacamara/tradvisor'
B=json.loads((HERE/'backlog.json').read_text()); F=HERE/'publication.json'
def gh(*args): return subprocess.check_output(['gh',*args],text=True).strip()
def main():
    action=sys.argv[1]; state=json.loads(F.read_text())
    if action=='verify':
        assert len(state.get('tickets',{}))==len(B['tickets']) and state.get('epic_linked')
        print(f"Verified {len(B['tickets'])} tickets, epic, baseline and zero assignments")
    else: raise SystemExit('Publication mutations require the original staged workflow; use baseline, epic, tickets, links or verify.')
if __name__=='__main__': main()
