#!/usr/bin/env python3
import json, sys
from pathlib import Path
file=Path(__file__).parent/'publication.json'; state=json.loads(file.read_text()) if file.exists() else {}
kind,key,number,url=sys.argv[1:5]
if not number.isdigit() or not url.startswith('https://github.com/issacamara/tradvisor/issues/'): raise ValueError('Invalid issue/comment')
entry={'number':int(number),'url':url}
if kind in ('gate','epic'):
    if kind in state: raise ValueError('Already recorded')
    state[kind]=entry
elif kind=='ticket':
    if key in state.setdefault('tickets',{}): raise ValueError('Already recorded')
    state['tickets'][key]=entry
elif kind=='comment':
    document,part=key.split(':',1); part=int(part)
    if any(x['document']==document and x['part']==part for x in state.setdefault('comments',[])): raise ValueError('Already recorded')
    state['comments'].append({'document':document,'part':part,**entry})
else: raise ValueError('Invalid publication kind')
tmp=file.with_suffix('.json.tmp'); tmp.write_text(json.dumps(state,indent=2)+'\n'); tmp.replace(file)
print(f'Recorded {kind} {key} #{number}')
