#!/usr/bin/env python3
import json, subprocess
from pathlib import Path
B = json.loads((Path(__file__).parent/'backlog.json').read_text())
repo=B['repository']; existing=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/labels?per_page=100']))
names={x['name'] for x in existing}; created=[]
for name in B['labels']:
    if name in names: continue
    color='bfd4f2' if name.startswith('wave-') else ('c2e0c6' if name.startswith('domain:') else 'd4c5f9')
    desc='Not dispatchable: dependency, approval, or explicit dispatch hold' if name=='blocked' else 'Tradvisor V1 architecture delivery classification'
    subprocess.check_call(['gh','api','--method','POST',f'repos/{repo}/labels','-f',f'name={name}','-f',f'color={color}','-f',f'description={desc}'])
    created.append(name)
print(f'Verified label setup; created {len(created)}, preserved {len(names)} existing labels.')
