#!/usr/bin/env python3
"""Render publication files from the canonical checked-in issue bodies."""
import json
from pathlib import Path
HERE=Path(__file__).parent
def main():
    bundle=json.loads((HERE/'backlog.json').read_text())
    bodies=json.loads((HERE/'issue_bodies.json').read_text()) if (HERE/'issue_bodies.json').exists() else {'epic':'','tickets':{}}
    (HERE/'tradvisor_backlog.md').write_text(bodies.get('epic',''))
    (HERE/'issues').mkdir(exist_ok=True)
    for key,body in bodies.get('tickets',{}).items(): (HERE/'issues'/f'{key}.md').write_text(body)
    print(f"Rendered {len(bodies.get('tickets',{}))} ticket bodies from canonical publication artifacts.")
if __name__=='__main__': main()
