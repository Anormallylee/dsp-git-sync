"""Administrative initialization; actual gameplay starts from Steam."""
import json,os,subprocess,sys
from pathlib import Path
import git_sync as g
import file_sync as fs
f=fs.f
Remote=g.Remote
atomic=fs.atomic
publish=g.publish
receive=g.receive

def fingerprint(c):return fs.fingerprint(fs.scan(c))
def running():
 try:f.ensure_closed();return False
 except ValueError:return True

def load_settings():
 p=Path(__file__).with_name('config.json')
 if not p.exists():raise ValueError('Create machine-local config.json from config.example.json first.')
 raw=json.loads(p.read_text(encoding='utf-8-sig'))
 c={k:Path(raw[k]).expanduser().resolve() for k in ['data','game','backup']}
 base=c['backup']/'git-launcher-state'
 raw.setdefault('git_cache',str(base/'repository.git'))
 cache=Path(raw['git_cache']).expanduser().resolve()
 for root in (c['data'],c['game']):
  for out in (c['backup'],cache):
   if out==root or root in out.parents or out in root.parents:raise ValueError('Backup and Git cache must be outside live game/data directories.')
 if not (c['game']/'DSPGAME.exe').is_file():raise ValueError('Game path does not contain DSPGAME.exe.')
 return c,raw,base

def main():
 action=sys.argv[1] if len(sys.argv)>1 else ''
 if action not in ('init-source','init-download','recover-upload','status'):raise ValueError('Start gameplay from Steam. Administrative commands: init-source, init-download, recover-upload, status.')
 c,raw,base=load_settings();base.mkdir(parents=True,exist_ok=True)
 with f.sync_lock(base/'active.lock'):
  f.ensure_closed()
  if (base/'apply-journal.json').exists():raise ValueError('Unfinished file transaction; inspect backups.')
  r=Remote(raw);p=base/'state.json'
  recovered=g.recover_publish(c,r,p) if action in ('init-source','recover-upload') else False
  state=g.load_state(r,p);head=r.fetch()
  if action=='status':
   print(json.dumps({'local_revision':state['revision'] if state else None,'remote_revision':head,'pending':(base/'pending.json').exists()},indent=2));return
  if action.startswith('init-'):
   if state and recovered and action=='init-source':
    print('Initial upload recovered and verified.');return
   if state:raise ValueError('Already initialized; do not overwrite the baseline.')
   if action=='init-source':
    if head is not None:raise ValueError('Remote branch already has data; initialize by downloading.')
    publish(c,r,p,None)
   else:
    if head is None:raise ValueError('Remote data branch is empty.')
    receive(c,r,p,head)
  else:
   if not state:raise ValueError('No baseline for recovery.')
   publish(c,r,p,state['revision']);(base/'pending.json').unlink(missing_ok=True)
if __name__=='__main__':
 try:main()
 except Exception as e:f.log('Sync stopped: '+str(e));sys.exit(1)
