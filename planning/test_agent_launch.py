#!/usr/bin/env python3
"""Smoke-test the Python planning interfaces."""
import json, tempfile
from pathlib import Path
from model_policy import BACKLOG, TERRA, SOL, for_ticket, record_failure
def main():
    assert len(BACKLOG['tickets'])==77
    item=BACKLOG['tickets'][0]
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'failures.json'
        assert for_ticket(item, {})['implementation_model']==TERRA
        assert record_failure(item['id'],'attempt-1',p)==1
        assert record_failure(item['id'],'attempt-2',p)==2
        assert for_ticket(item,json.loads(p.read_text()))['implementation_model']==SOL
    print('1 run, 4 assertions, 0 failures, 0 errors')
if __name__=='__main__': main()
