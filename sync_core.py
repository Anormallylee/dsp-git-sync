"""Read-only inventory of supported DSP user data and loader files."""
import os,sys,json,hashlib,datetime,uuid,subprocess,unicodedata
from contextlib import contextmanager
from pathlib import Path
TREES=['data/Save/','data/Blueprint/','data/Blueprints/','game/BepInEx/core/','game/BepInEx/plugins/','game/BepInEx/patchers/','game/BepInEx/config/']
FILES=['game/winhttp.dll','game/doorstop_config.ini','game/.doorstop_version']
def targets(roots):return {k:Path(roots[k.split('/')[0]])/k.split('/',1)[1].rstrip('/') for k in TREES+FILES}
def excluded(p):return any(x.lower().startswith('.') for x in p.parts) or any('stutterprobe' in x.lower() for x in p.parts)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def token():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
@contextmanager
def sync_lock(path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a+b') as handle:
  try:
   if os.name=='nt':
    import msvcrt
    handle.seek(0,os.SEEK_END)
    if handle.tell()==0:handle.write(b'0');handle.flush()
    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except (BlockingIOError,OSError):raise ValueError('Sync is already active.') from None
  handle.seek(0);handle.truncate();handle.write(str(os.getpid()).encode());handle.flush()
  try:yield
  finally:
   if os.name=='nt':
    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
def inventory(roots,require_complete=True):
 result={}
 for key,p in targets(roots).items():
  if p.is_symlink():raise ValueError('同步根不能是符号链接：'+str(p))
  if key in FILES:
   if p.is_file():result[key]=p
  elif p.exists():
   for f in p.rglob('*'):
    if f.is_symlink():raise ValueError('范围内有符号链接：'+str(f))
    if f.is_file() and not excluded(f.relative_to(p)) and not (key=='data/Save/' and f.suffix not in ['.dsv','.moddsv']):
     name=unicodedata.normalize('NFC',key+f.relative_to(p).as_posix())
     if name in result:raise ValueError('Unicode-normalized paths collide: '+name)
     result[name]=f
 if require_complete and not any(k.startswith('data/Save/') and k.endswith('.dsv') for k in result):raise ValueError('没有存档。')
 if require_complete and not any(k.startswith('game/BepInEx/core/') for k in result):raise ValueError('没有 BepInEx core；请检查游戏目录。')
 if require_complete and not all(k in result for k in FILES):raise ValueError('缺少 Doorstop 启动文件。')
 return result

def ensure_closed():
 if os.name=='nt':
  r=subprocess.run(['tasklist','/FI','IMAGENAME eq DSPGAME.exe','/FO','CSV','/NH'],capture_output=True,check=True)
  running=b'dspgame.exe' in r.stdout.lower()
 else:
  r=subprocess.run(['ps','-axo','comm='],capture_output=True,text=True,check=True)
  running=any('dspgame.exe' in line.lower() for line in r.stdout.splitlines())
 if running:raise ValueError('游戏仍在运行，请正常保存并退出后再操作。')

def log(message):
 try:print(message,flush=True)
 except UnicodeEncodeError:print(str(message).encode('ascii',errors='backslashreplace').decode('ascii'),flush=True)
