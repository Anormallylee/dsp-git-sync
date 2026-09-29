"""Private Git transport. The bare cache is separate from live game data."""
import base64,hashlib,json,os,re,shutil,subprocess,tarfile,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit
import file_sync as fs

ATTRIBUTES=b'* -text -filter -diff -merge\n'
REV=re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?')

class Remote:
 def __init__(self,raw):
  self.remote=raw['git_remote'];self.branch=raw.get('git_branch','sync-v1');self.bin=raw.get('git','git')
  if self.remote.startswith('-') or '\n' in self.remote or '\r' in self.remote:raise ValueError('Invalid Git remote')
  u=urlsplit(self.remote)
  if u.scheme in ('http','https') and (u.username or u.password):raise ValueError('Use the OS Git credential helper; do not put credentials in URLs.')
  self.local_push_url=raw.get('git_local_push_url')
  if self.local_push_url:
   v=urlsplit(self.local_push_url)
   if u.scheme!='https' or v.scheme not in ('http','https') or v.hostname not in ('localhost','127.0.0.1','::1') or v.username or v.password or v.query or v.fragment or v.path!=u.path:
    raise ValueError('Local push URL must point to the same HTTPS repository through loopback, without embedded credentials.')
  if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*',self.branch) or '..' in self.branch or self.branch.endswith(('/','.lock')):raise ValueError('Invalid sync branch')
  self.repo=Path(raw['git_cache']).expanduser().resolve();self.repo.parent.mkdir(parents=True,exist_ok=True)
  self.env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never',GIT_LFS_SKIP_SMUDGE='1',LC_ALL='C')
  self.env.update(GIT_AUTHOR_NAME='DSP Git Sync',GIT_AUTHOR_EMAIL='dsp-sync@localhost',GIT_COMMITTER_NAME='DSP Git Sync',GIT_COMMITTER_EMAIL='dsp-sync@localhost')
  self.hooks=self.repo.parent/'empty-hooks';self.hooks.mkdir(exist_ok=True)
  if not (self.repo/'HEAD').exists():
   if self.repo.exists() and any(self.repo.iterdir()):raise ValueError('Git cache is not empty; refusing to overwrite it.')
   p=subprocess.run([self.bin,'init','--bare',str(self.repo)],env=self.env,capture_output=True)
   if p.returncode:raise RuntimeError('Cannot initialize Git cache.')
   self.run('remote','add','origin',self.remote)
  else:
   if self.run('rev-parse','--is-bare-repository').strip()!=b'true':raise ValueError('Sync cache must be a dedicated bare repository.')
   if self.run('remote','get-url','origin').decode().strip()!=self.remote:raise ValueError('Git cache belongs to another remote.')
  self.run('config','gc.auto','0')
 def command(self,*args):
  return [self.bin,'-c','core.hooksPath='+str(self.hooks),'-c','core.autocrlf=false','-c','core.precomposeUnicode=true','-c','commit.gpgSign=false','--git-dir='+str(self.repo),*args]
 def run(self,*args,input=None,env=None):
  p=subprocess.run(self.command(*args),input=input,env=env or self.env,capture_output=True,timeout=3600)
  if p.returncode:
   # Git diagnostics can contain credential-bearing proxy/helper output. Keep
   # errors generic and leave authentication to the user's normal Git tools.
   raise RuntimeError('Git '+args[0]+' failed. Check connectivity, credentials, and remote history; local progress is retained.')
  return p.stdout
 def fetch(self):
  ref='refs/heads/'+self.branch
  if not self.run('ls-remote','origin',ref).strip():return None
  self.run('fetch','--no-tags','--keep','origin','+'+ref+':refs/remotes/origin/'+self.branch)
  return self.run('rev-parse','refs/remotes/origin/'+self.branch).decode().strip()
 def ancestor(self,old,new):
  if not REV.fullmatch(old) or not REV.fullmatch(new):raise ValueError('Invalid revision')
  p=subprocess.run(self.command('merge-base','--is-ancestor',old,new),env=self.env,capture_output=True)
  if p.returncode not in (0,1):raise ValueError('Baseline Git history is missing.')
  return p.returncode==0
 def manifest(self,commit):
  if not commit or not REV.fullmatch(commit):raise ValueError('Missing or invalid remote revision.')
  entries={}
  for row in self.run('ls-tree','-r','-l','-z',commit).split(b'\0'):
   if not row:continue
   meta,path=row.split(b'\t',1);mode,kind,oid,size=meta.split();name=path.decode('utf-8')
   if mode!=b'100644' or kind!=b'blob':raise ValueError('Unsupported file mode in data repository.')
   entries[name]=int(size)
  if entries.get('manifest.json',0)>32*1024**2 or 'manifest.json' not in entries:raise ValueError('Missing or oversized data manifest.')
  if entries.get('.gitattributes')!=len(ATTRIBUTES) or self.run('show',commit+':.gitattributes')!=ATTRIBUTES:raise ValueError('Unexpected Git attributes in data repository.')
  m=json.loads(self.run('show',commit+':manifest.json'))
  if m.get('format')!='dsp-git-sync-v1':raise ValueError('This branch is not a DSP Git Sync data branch.')
  fs.validate(m['files'])
  expected={'.gitattributes':len(ATTRIBUTES),'manifest.json':entries['manifest.json']}
  expected.update({'files/'+k:v['bytes'] for k,v in m['files'].items()})
  if entries!=expected:raise ValueError('Git tree differs from the declared data manifest.')
  return m
 def materialize(self,commit,dest):
  m=self.manifest(commit);dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
  allowed={'files/'+k:v for k,v in m['files'].items()};seen=set()
  p=subprocess.Popen(self.command('archive','--format=tar',commit),env=self.env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  try:
   with tarfile.open(fileobj=p.stdout,mode='r|') as archive:
    for item in archive:
     if item.isdir():continue
     if item.name in ('.gitattributes','manifest.json'):continue
     if not item.isfile() or item.name not in allowed or item.name in seen:raise ValueError('Unexpected archived file.')
     meta=allowed[item.name]
     if item.size!=meta['bytes']:raise ValueError('File length mismatch.')
     out=dest/item.name;out.parent.mkdir(parents=True,exist_ok=True)
     with archive.extractfile(item) as src,out.open('xb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
     if fs.f.sha(out)!=meta['sha256']:raise ValueError('Downloaded file checksum mismatch: '+item.name)
     seen.add(item.name)
   if p.wait()!=0 or seen!=set(allowed):raise ValueError('Incomplete Git archive.')
  finally:
   if p.poll() is None:p.kill();p.wait()
   p.stdout.close()
  return m
 def commit(self,stage,parent):
  stage=Path(stage)
  with tempfile.TemporaryDirectory(dir=self.repo.parent) as td:
   env=dict(self.env,GIT_INDEX_FILE=str(Path(td)/'index'))
   if parent:self.run('read-tree',parent,env=env)
   self.run('--work-tree='+str(stage),'-c','core.bare=false','add','--all','--force','--chmod=-x','--','.',env=env)
   tree=self.run('write-tree',env=env).decode().strip()
   args=['commit-tree',tree]
   if parent:args+=['-p',parent]
   return self.run(*args,input=b'DSP game state\n',env=env).decode().strip()
 def maintain(self,force=False):
  stats={k.strip():int(v) for k,v in (line.split(':',1) for line in self.run('count-objects','-v').decode().splitlines())}
  if not force and stats.get('size',0)<65536 and stats.get('packs',0)<20:return
  fs.f.log('Compacting verified local Git cache.')
  try:self.run('-c','pack.windowMemory=256m','-c','pack.threads=2','repack','-a','-d','-l','--window=10','--depth=20')
  except RuntimeError:fs.f.log('Git cache compaction deferred; verified progress is retained.')
 def push(self,commit,parent):
  # A normal push rejects non-fast-forward history; never use force.
  if not self.local_push_url:
   self.run('push','--porcelain','origin',commit+':refs/heads/'+self.branch);return
  u=urlsplit(self.remote)
  answer=subprocess.run([self.bin,'credential','fill'],input=('protocol=https\nhost='+u.netloc+'\n\n').encode(),env=self.env,capture_output=True,timeout=30)
  if answer.returncode:raise RuntimeError('Git credential helper could not supply credentials for the configured remote.')
  fields=dict(line.split('=',1) for line in answer.stdout.decode().splitlines() if '=' in line)
  if not fields.get('username') or not fields.get('password'):raise RuntimeError('Git credential helper returned incomplete credentials.')
  token=base64.b64encode((fields['username']+':'+fields['password']).encode()).decode()
  env=dict(self.env,GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='http.'+self.local_push_url+'.extraHeader',GIT_CONFIG_VALUE_0='Authorization: Basic '+token,GIT_CONFIG_KEY_1='http.followRedirects',GIT_CONFIG_VALUE_1='false')
  self.run('push','--porcelain',self.local_push_url,commit+':refs/heads/'+self.branch,env=env)

def state_for(r,commit,files):
 return {'backend':'git','remote':r.remote,'branch':r.branch,'revision':commit,'files':files,'fingerprint':fs.fingerprint(files)}
def load_state(r,p):
 if not p.exists():return None
 s=json.loads(p.read_text(encoding='utf-8'));fs.validate(s['files'])
 if s.get('backend')!='git' or s.get('remote')!=r.remote or s.get('branch')!=r.branch:raise ValueError('Baseline belongs to a different backend, remote, or branch.')
 if fs.fingerprint(s['files'])!=s['fingerprint']:raise ValueError('Baseline manifest is damaged.')
 return s

def recover_publish(c,r,statefile):
 statefile=Path(statefile);attempt=statefile.parent/'publish-attempt.json'
 if not attempt.exists():return False
 a=json.loads(attempt.read_text(encoding='utf-8'));head=r.fetch()
 if a.get('remote')!=r.remote or a.get('branch')!=r.branch:raise ValueError('Interrupted upload belongs to another remote.')
 if head==a['commit']:
  m=r.manifest(head)
  if m['files']!=a['files']:raise ValueError('Interrupted upload manifest mismatch.')
  fs.atomic(statefile,state_for(r,head,m['files']));attempt.unlink();return True
 if head==a['parent']:
  if fs.scan(c)!=a['files']:raise ValueError('Local files changed after an interrupted upload; preserve both states for review.')
  r.push(a['commit'],a['parent'])
  if r.fetch()!=a['commit']:raise ValueError('Remote changed during upload recovery.')
  fs.atomic(statefile,state_for(r,a['commit'],a['files']));attempt.unlink();return True
 raise ValueError('Remote changed after an interrupted upload; automatic overwrite is blocked.')

def receive(c,r,statefile,commit):
 fs.f.ensure_closed();statefile=Path(statefile);base=statefile.parent;base.mkdir(parents=True,exist_ok=True)
 if (base/'apply-journal.json').exists():raise ValueError('Unfinished file transaction: inspect backup before continuing.')
 if (base/'publish-attempt.json').exists():raise ValueError('Recover the interrupted upload before receiving.')
 current=fs.scan(c,False);state=load_state(r,statefile)
 if r.fetch()!=commit:raise ValueError('Remote changed before import; retry.')
 m=r.manifest(commit);remote=m['files']
 if state:
  if not r.ancestor(state['revision'],commit):raise ValueError('Remote history was rewritten; refusing to replace progress.')
  desired=fs.merge(state['files'],current,remote)
 else:desired=remote
 fs.validate(desired)
 with tempfile.TemporaryDirectory(dir=base) as td:
  stage=Path(td);r.materialize(commit,stage/'remote')
  source_by_hash={(v['sha256'],v['bytes']):k for k,v in current.items()};actual=fs.f.inventory(c,False)
  for k,v in desired.items():
   out=stage/'apply'/k;out.parent.mkdir(parents=True,exist_ok=True)
   if remote.get(k)==v:src=stage/'remote/files'/k
   else:
    local=source_by_hash.get((v['sha256'],v['bytes']))
    if local is None:raise ValueError('Missing local content for reconciliation.')
    src=actual[local]
   shutil.copy2(src,out)
  if r.fetch()!=commit:raise ValueError('Remote changed during preparation; retry.')
  backup=fs.apply(c,desired,current,stage/'apply',base)
 fs.atomic(statefile,state_for(r,commit,remote))
 r.maintain()
 fs.f.log('Git receive verified; backup: '+str(backup))
 return commit

def publish(c,r,statefile,parent):
 fs.f.ensure_closed();statefile=Path(statefile);base=statefile.parent;base.mkdir(parents=True,exist_ok=True)
 if (base/'apply-journal.json').exists():raise ValueError('Unfinished file transaction.')
 if recover_publish(c,r,statefile):parent=load_state(r,statefile)['revision']
 state=load_state(r,statefile)
 if (state is None and parent is not None) or (state and state['revision']!=parent):raise ValueError('Publish parent differs from the local baseline.')
 if r.fetch()!=parent:raise ValueError('Remote changed; reconcile before publishing.')
 current=fs.scan(c)
 if parent:
  m=r.manifest(parent)
  if current==m['files']:
   fs.atomic(statefile,state_for(r,parent,current));return parent
 with tempfile.TemporaryDirectory(dir=base) as td:
  stage=Path(td);actual=fs.f.inventory(c)
  for k in current:
   root,rel=k.split('/',1);out=stage/'files'/k;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(actual[k],out)
   if fs.f.sha(out)!=current[k]['sha256']:raise ValueError('Live data changed while staging; retry after the game exits.')
  (stage/'.gitattributes').write_bytes(ATTRIBUTES);fs.atomic(stage/'manifest.json',{'format':'dsp-git-sync-v1','files':current})
  commit=r.commit(stage,parent)
  if r.manifest(commit)['files']!=current:raise ValueError('Commit verification failed.')
  if fs.scan(c)!=current:raise ValueError('Live data changed during commit.')
  fs.f.ensure_closed()
  if r.fetch()!=parent:raise ValueError('Remote changed before push.')
  fs.atomic(base/'publish-attempt.json',{'remote':r.remote,'branch':r.branch,'commit':commit,'parent':parent,'files':current})
  r.push(commit,parent)
  if r.fetch()!=commit:raise ValueError('Remote changed before upload confirmation.')
 fs.atomic(statefile,state_for(r,commit,current));(base/'publish-attempt.json').unlink()
 r.maintain()
 fs.f.log('Git upload confirmed: '+commit[:12])
 return commit
