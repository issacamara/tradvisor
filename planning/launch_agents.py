#!/usr/bin/env python3
"""Checkpointed dispatcher entry point for the autonomous Codex workflow."""
import json, os, subprocess, sys, time
from pathlib import Path
HERE=Path(__file__).parent; ROOT=HERE.parent; RUNS=ROOT/'.agent-runs'; STATE=RUNS/'active.json'
def command(*args): return subprocess.check_output(args,cwd=ROOT,text=True).strip()
def check():
    if command('git','branch','--show-current')!='V1': raise RuntimeError('Expected V1 checkout')
    if 'issacamara/tradvisor' not in command('git','remote','get-url','origin'): raise RuntimeError('Unexpected repository')
    b=json.loads((HERE/'backlog.json').read_text()); p=json.loads((HERE/'publication.json').read_text())
    if len(p.get('tickets',{}))!=len(b['tickets']) or not p.get('epic_linked'): raise RuntimeError('Backlog publication is incomplete')
    dirty=command('git','status','--porcelain').splitlines()
    print(f"Repository: issacamara/tradvisor / V1; published tickets: {len(b['tickets'])}; local changes: {len(dirty)}")
def start():
    check(); RUNS.mkdir(exist_ok=True)
    state=json.loads(STATE.read_text()) if STATE.exists() else {'version':1,'phase':'ready','cycle':1,'attempt':0}
    if state.get('phase') in ('complete','blocked','decision_required'): raise RuntimeError(f"Dispatcher is {state['phase']}")
    state.update(updated_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    print('Checkpoint ready. Run the Codex dispatcher with the approved prompt; no ticket work was started.')
if __name__=='__main__':
    if (sys.argv[1:] or ['check'])[0]=='check': check()
    elif sys.argv[1]=='start': start()
    else: raise SystemExit('Usage: python planning/launch_agents.py [check|start]')
