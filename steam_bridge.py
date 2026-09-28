"""Steam wrapper bridge; native worker owns the sync lock until game exit."""
import json,os,re,sys,time,traceback
from pathlib import Path
import launcher as l
import git_sync as g

def prepare(c,r,base):
 l.f.ensure_closed()
 if (base/'apply-journal.json').exists():raise ValueError('Unfinished file transaction; inspect backup before starting.')
 p=base/'state.json';g.recover_publish(c,r,p);state=g.load_state(r,p)
 if state is None:raise ValueError('Initialize this device before the first Steam launch.')
 remote=r.fetch()
 if remote is None:raise ValueError('Remote data branch is missing.')
 if remote!=state['revision']:
  if (base/'pending.json').exists():raise ValueError('Previous session is unpublished and the remote changed; inspect conflicts.')
  g.receive(c,r,p,remote)
 l.atomic(base/'pending.json',{'started':l.f.token(),'parent':remote,'entry':'steam'})
 return remote

def finish(c,r,base,parent):
 l.f.ensure_closed();g.publish(c,r,base/'state.json',parent)
 (base/'pending.json').unlink(missing_ok=True)

def write(path,text):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf-8');os.replace(tmp,path)

def session(c,raw,base,ipc,sid):
 out=ipc/'sessions'/sid;out.mkdir(parents=True,exist_ok=True)
 def status(text):
  write(out/'status.txt',text)
  print(time.strftime('%Y-%m-%d %H:%M:%S'),sid,text,flush=True)
 status('正在检查 Git 远端最新状态，请勿关闭此窗口。')
 lock=base/'active.lock';fd=None
 try:
  fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,str(os.getpid()).encode());os.close(fd)
  if (out/'cancel').exists():raise ValueError('启动已取消。')
  r=l.Remote(raw);parent=prepare(c,r,base)
  if (out/'cancel').exists():raise ValueError('启动已取消；本地数据保留。')
  status('同步检查完成，正在启动游戏。');write(out/'ready','ok')
  deadline=time.monotonic()+180
  while not (out/'started').exists():
   if (out/'cancel').exists() or time.monotonic()>deadline:raise ValueError('游戏未启动；保留本地状态，下次检查后重试。')
   time.sleep(1)
  status('游戏运行中。退出后将自动上传，请保留同步窗口。')
  absent=0
  while absent<5:
   time.sleep(2);absent=0 if l.running() else absent+1
  status('游戏已退出，正在增量上传最终状态。完成前不要切换设备。')
  finish(c,r,base,parent)
  status('同步完成，可以换设备。');write(out/'done','ok')
 except Exception as e:
  status('同步已停止：'+str(e));write(out/'error',str(e));traceback.print_exc()
 finally:
  if fd is not None:lock.unlink(missing_ok=True)
  (ipc/'requests'/(sid+'.request')).unlink(missing_ok=True)

def main():
 c,raw,base=l.load_settings();base.mkdir(parents=True,exist_ok=True)
 ipc=Path(raw.get('bridge_dir',str(Path(__file__).parent/'ipc'))).expanduser();q=ipc/'requests';q.mkdir(parents=True,exist_ok=True)
 only=sys.argv[2] if len(sys.argv)==3 and sys.argv[1]=='--once' else None
 while True:
  for request in sorted(q.glob('*.request')):
   sid=request.stem
   if not re.fullmatch('[0-9a-f-]{36}',sid) or (only and only!=sid):continue
   session(c,raw,base,ipc,sid)
  if '--serve' not in sys.argv:break
  time.sleep(1)
if __name__=='__main__':main()
