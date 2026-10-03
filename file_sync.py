"""Manifest checks, three-way reconciliation, and backed-up file transactions."""
import hashlib,json,os,re,shutil,errno,unicodedata
from pathlib import Path,PurePosixPath
import sync_core as f
HASH=re.compile(r"[0-9a-f]{64}")
def atomic(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(t,p)
def bare(files):return {k:{'sha256':v['sha256'],'bytes':v['bytes']} for k,v in files.items()}
def fingerprint(files):
 h=hashlib.sha256()
 for k,v in sorted(files.items()):h.update(k.encode());h.update(bytes.fromhex(v['sha256']))
 return h.hexdigest()
def scan(c,require_complete=True):
 paths=f.inventory(c,require_complete);before={k:(p.stat().st_size,p.stat().st_mtime_ns) for k,p in paths.items()}
 result={k:{'sha256':f.sha(p),'bytes':before[k][0]} for k,p in paths.items()}
 after=f.inventory(c,require_complete)
 if paths.keys()!=after.keys() or any((p.stat().st_size,p.stat().st_mtime_ns)!=before[k] for k,p in after.items()):raise ValueError('扫描期间本地文件改变，请重试。')
 validate(result,complete=require_complete);return result

def validate(files,refs=False,complete=True):
 if not isinstance(files,dict) or len(files)>30000:raise ValueError('文件清单异常。')
 folded=set();total=0
 for k,v in files.items():
  p=PurePosixPath(k)
  if unicodedata.normalize('NFC',k)!=k or str(p)!=k or p.is_absolute() or not (k in f.FILES or any(k.startswith(t) for t in f.TREES)):raise ValueError('非法同步路径：'+k)
  if any(x in ('..','.') or any(ord(ch)<32 or ch in '<>\"|?*' for ch in x) or ':' in x or '\\' in x or x.endswith((' ','.')) or x.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*['COM'+str(i) for i in range(1,10)],*['LPT'+str(i) for i in range(1,10)]} for x in p.parts):raise ValueError('路径不兼容Windows：'+k)
  if k.casefold() in folded or any('stutterprobe' in x.lower() for x in p.parts):raise ValueError('大小写冲突或不允许同步的文件：'+k)
  folded.add(k.casefold())
  if not isinstance(v,dict) or not HASH.fullmatch(v.get('sha256','')) or type(v.get('bytes')) is not int or not 0<=v['bytes']<=20*1024**3:raise ValueError('文件元数据异常。')
  total+=v['bytes']
  if refs:
   if not re.fullmatch(r'(packs|snapshots)/[A-Za-z0-9-]{1,100}\.zip',v.get('pack','')) or not HASH.fullmatch(v.get('pack_sha256','')):raise ValueError('文件包引用异常。')
 if total>20*1024**3:raise ValueError('同步范围超过20GiB。')
 if complete and (not all(k in files for k in f.FILES) or not any(k.startswith('data/Save/') and k.endswith('.dsv') for k in files) or not any(k.startswith('game/BepInEx/core/') for k in files)):raise ValueError('清单缺少存档或必要加载器文件。')

def group(k):
 if k.startswith('data/Save/'):return 'save:'+k.rsplit('.',1)[0].casefold()
 if k.startswith('game/'):return 'mods'
 return 'blueprint:'+k.casefold()
def sync_files(files):return {k:v for k,v in files.items() if not f.excluded_save(k)}
def merge(base,local,remote):
 base,local,remote=map(sync_files,(base,local,remote))
 result={};keys=set(base)|set(local)|set(remote)
 for g in {group(k) for k in keys if not group(k).startswith('blueprint:')}:
  ks={k for k in keys if group(k)==g}
  b={k:base[k] for k in ks if k in base};a={k:local[k] for k in ks if k in local};r={k:remote[k] for k in ks if k in remote}
  if a!=b and r!=b and a!=r:raise ValueError('双方修改了同一存档组或Mod配置，停止自动覆盖：'+g)
  result.update(r if a==b else a)
 for k in sorted(k for k in keys if group(k).startswith('blueprint:')):
  b,a,r=base.get(k),local.get(k),remote.get(k)
  if a==b:chosen=r
  elif r==b or a==r:chosen=a
  elif a is not None and r is not None and k.lower().endswith('.txt'):
   conflict=k[:-4]+'.conflict-local-'+a['sha256'][:12]+'.txt'
   if conflict in keys or conflict in result:raise ValueError('蓝图冲突副本已存在，需人工检查：'+k)
   result[conflict]=a;chosen=r;f.log('蓝图双端修改，保留本地冲突副本：'+conflict)
  else:raise ValueError('蓝图删除/修改冲突，保留双方并停止：'+k)
  if chosen is not None:result[k]=chosen
 validate(result);return result

def apply(c,desired,current,staged,base):
 f.ensure_closed()
 if scan(c,False)!=current:raise ValueError('下载期间本地内容改变，已停止导入；新文件仍保留。请重新启动同步。')
 journal=base/'apply-journal.json'
 if journal.exists():raise ValueError('存在未完成的文件事务，请先检查备份，禁止自动继续。')
 changed=sorted(k for k in set(current)|set(desired) if current.get(k)!=desired.get(k))
 backup=c['backup']/('incremental-'+f.token());backup.mkdir(parents=True,exist_ok=True)
 actual=f.inventory(c,False)
 def target(k):
  if k in actual:return actual[k]
  root,rel=k.split('/',1);return c[root]/rel
 # Prepare every replacement before touching the live files.
 for k in changed:
  if k in desired:
   p=staged/k
   if not p.is_file() or p.stat().st_size!=desired[k]['bytes'] or f.sha(p)!=desired[k]['sha256']:raise ValueError('暂存文件校验失败：'+k)
  t=target(k)
  if any(p.is_symlink() for p in [t,*t.parents] if p==c[k.split('/')[0]] or c[k.split('/')[0]] in p.parents):raise ValueError('目标路径含符号链接：'+k)
 tx=f.token()
 atomic(journal,{'backup':str(backup),'files':changed,'previous':current,'transaction':tx})
 done=[]
 try:
  for index,k in enumerate(changed):
   t=target(k);old=backup/k;old.parent.mkdir(parents=True,exist_ok=True);t.parent.mkdir(parents=True,exist_ok=True)
   displaced=t.with_name('.dsp-sync-original-'+tx+'-'+str(index))
   tmp=t.with_name('.dsp-sync-new-'+tx+'-'+str(index))
   if displaced.exists() or tmp.exists():raise ValueError('事务暂存路径已存在。')
   try:
    if k in desired:shutil.copy2(staged/k,tmp)
    # Move the actual original atomically; do not discard an edit which arrived
    # while the replacement was being prepared. Hidden sidecar is same-volume.
    if k in current:
     os.rename(t,displaced);entry=[k,displaced,False];done.append(entry)
     shutil.copy2(displaced,old)
     if f.sha(displaced)!=current[k]['sha256']:raise ValueError('提交前本地文件改变，保留最新内容并停止：'+k)
    else:entry=[k,None,False];done.append(entry)
    if k in desired:
     # Exclusive link prevents overwriting a new external file in the rename gap.
     os.link(tmp,t);entry[2]=True
    elif t.exists():raise ValueError('删除时发现外部新文件，停止：'+k)
   finally:tmp.unlink(missing_ok=True)
  if scan(c)!=desired:raise ValueError('提交期间本地文件变化，停止并回滚。')
  for k,displaced,installed in done:
   if displaced is not None and f.sha(displaced)!=current[k]['sha256']:raise ValueError('原文件仍被外部写入，停止并回滚：'+k)
 except BaseException:
  rollback_ok=True;withdrawn_files=[]
  for index,(k,displaced,installed) in enumerate(reversed(done)):
   try:
    t=target(k)
    if t.exists():
     if not installed or f.sha(t)!=desired[k]['sha256']:raise ValueError('回滚目标有外部修改，保留双方及事务记录。')
     withdrawn=t.with_name('.dsp-sync-withdrawn-'+tx+'-'+str(index))
     os.rename(t,withdrawn)
     withdrawn_files.append({'file':k,'retained':str(withdrawn)})
    if displaced is not None:
     # Keep the displaced file until exclusive restoration succeeds.
     os.link(displaced,t);shutil.copy2(displaced,backup/k);displaced.unlink()
   except BaseException:rollback_ok=False
  if withdrawn_files:atomic(backup/'rollback-retained.json',withdrawn_files)
  if rollback_ok:journal.unlink(missing_ok=True)
  raise
 retained=[]
 for k,displaced,installed in done:
  if displaced is not None:
   try:os.replace(displaced,backup/k)
   except OSError as e:
    if e.errno!=errno.EXDEV:raise
    retained.append({'file':k,'original':str(displaced)})
 if retained:atomic(backup/'retained-originals.json',retained)
 journal.unlink();return backup
