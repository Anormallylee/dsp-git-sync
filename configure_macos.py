"""Install the native macOS worker and CrossOver wrapper from a prepared package."""
import json,os,plistlib,shutil,subprocess,sys
from pathlib import Path
import launcher as l

def main():
 if sys.platform!='darwin':raise ValueError('macOS only')
 c,raw,base=l.load_settings();l.f.ensure_closed()
 for p in [base/'active.lock',c['backup']/'launcher-state/active.lock']:
  if p.exists():raise ValueError('Sync is active or a stale lock needs inspection.')
 root=Path(__file__).resolve().parent;exe=root/'SteamSync.exe'
 if not exe.is_file():raise ValueError('Build SteamSync.exe or use a release package first.')
 ipc=Path(raw['bridge_dir']).expanduser().resolve();windows=raw['bridge_windows_ipc']
 if not windows.lower().endswith('\\ipc'):raise ValueError('bridge_windows_ipc must end in \\ipc')
 (ipc/'requests').mkdir(parents=True,exist_ok=True);(ipc/'sessions').mkdir(exist_ok=True)
 raw['bridge_dir']=str(ipc);l.atomic(root/'config.json',raw)
 home=Path.home();agent=home/'Library/LaunchAgents/local.dsp.steam-sync.plist';agent.parent.mkdir(parents=True,exist_ok=True)
 backup=c['backup']/('agent-before-git-'+l.f.token());backup.mkdir(parents=True)
 for p in [agent,ipc.parent/'SteamSync.exe',ipc.parent/'bridge.ini']:
  if p.exists():shutil.copy2(p,backup/p.name)
 subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/local.dsp.steam-sync'],capture_output=True)
 shutil.copy2(exe,ipc.parent/'SteamSync.exe');(ipc.parent/'bridge.ini').write_text('[bridge]\nipc='+windows+'\n',encoding='utf-16')
 logs=c['backup']/'logs';logs.mkdir(parents=True,exist_ok=True)
 config={'Label':'local.dsp.steam-sync','ProgramArguments':[sys.executable,'-u',str(root/'steam_bridge.py'),'--serve'],'RunAtLoad':True,'KeepAlive':True,'StandardOutPath':str(logs/'git-steam-sync.log'),'StandardErrorPath':str(logs/'git-steam-sync-error.log')}
 with agent.open('wb') as f:plistlib.dump(config,f)
 subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(agent)],check=True)
 print('Steam launch option: "'+windows[:-4]+'\\SteamSync.exe" %command%')
 print('Installed worker; backups:',backup)
if __name__=='__main__':main()
