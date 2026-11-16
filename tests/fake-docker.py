#!/usr/bin/env python3
"""File-backed Docker boundary fixture for ambiguous failures and ownership."""
import json,os,sys,time
from pathlib import Path
p=Path(os.environ['AFFINE_FAKE_DOCKER']);state=json.loads(p.read_text());args=sys.argv[1:]
def save():p.write_text(json.dumps(state))
def key(kind,name):return kind+':'+name
if args[0]=='inspect':
    kind=args[args.index('--type')+1];name=args[-1];item=state['resources'].get(key(kind,name))
    if key(kind,name) in state.get('inspect_fail',[]):print('daemon permission denied',file=sys.stderr);sys.exit(1)
    if not item:print('No such '+kind+': '+name,file=sys.stderr);sys.exit(1)
    print(json.dumps([{'Name':name,'Labels':item,'Config':{'Labels':item}}]));sys.exit(0)
if len(args)>1 and args[1]=='create':
    kind=args[0];name=args[-1];label=args[args.index('--label')+1];k,v=label.split('=',1)
    state['resources'].setdefault(key(kind,name),{k:v});save()
    if kind==state.get('fail_create'):print('ambiguous daemon response',file=sys.stderr);sys.exit(1)
    print(name);sys.exit(0)
if args[0]=='stop':sys.exit(0)
if args[0]=='rm':kind='container';name=args[-1]
elif len(args)>1 and args[1]=='rm':kind=args[0];name=args[-1]
else:raise SystemExit('Unsupported fake Docker command: '+repr(args))
if key(kind,name) in state.get('sleep_rm',[]):time.sleep(3)
state['resources'].pop(key(kind,name),None);save();print(name)
