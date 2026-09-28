"""Run after Windows-specific config.json and Git authentication exist."""
import os,json,subprocess,sys
from pathlib import Path
from sync_core import log
if os.name!='nt':raise SystemExit('Windows only')
root=Path(__file__).resolve().parent
p=root/'config.json';cfg=json.loads(p.read_text(encoding='utf-8-sig'))
for key in ['data','game','backup','git_remote']:
 if key not in cfg:raise SystemExit('Missing config: '+key)
if not (Path(cfg['game'])/'DSPGAME.exe').is_file():raise SystemExit('Wrong game path')
if not (root/'SteamSync.exe').is_file():raise SystemExit('Missing SteamSync.exe')
ipc=root/'ipc';(ipc/'requests').mkdir(parents=True,exist_ok=True);(ipc/'sessions').mkdir(exist_ok=True)
cfg['bridge_dir']=str(ipc);p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
# UTF-16 INI is supported by the Windows profile API, including Chinese paths.
(root/'bridge.ini').write_text('[bridge]\nipc='+str(ipc)+'\npython='+sys.executable+'\nworker_script='+str(root/'steam_bridge.py')+'\n',encoding='utf-16')
log('Steam launch options:')
log('"'+str(root/'SteamSync.exe')+'" %command%')
log('Configure Git baseline before first launch. Do not initialize Windows as source.')
