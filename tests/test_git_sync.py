import unittest,tempfile,subprocess,json,os,shutil
from pathlib import Path
from unittest.mock import patch
import git_sync as g
import file_sync as fs

class GitFixture:
 def setUp(self):
  self.assertTrue(hasattr(g,'Remote'),'Git transport is not implemented')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.origin=self.root/'origin.git';subprocess.run(['git','init','--bare',str(self.origin)],check=True,capture_output=True)
  self.a=self.device('a');self.b=self.device('b');self.sa=self.root/'a-state/state.json';self.sb=self.root/'b-state/state.json'
  self.ra=g.Remote({'git_remote':str(self.origin),'git_cache':str(self.root/'a-cache')})
  self.rb=g.Remote({'git_remote':str(self.origin),'git_cache':str(self.root/'b-cache')})
  p=patch.object(fs.f,'ensure_closed');p.start();self.addCleanup(p.stop)
 def device(self,n):
  c={k:self.root/n/k for k in ['data','game','backup']}
  for key,p in fs.f.targets(c).items():
   if key.endswith('/'):p.mkdir(parents=True,exist_ok=True)
   else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'loader')
  (c['data']/'Save/a.dsv').write_bytes(b'save');(c['data']/'Save/a.moddsv').write_bytes(b'modsave')
  (c['game']/'BepInEx/core/core.dll').write_bytes(b'core')
  (c['game']/'BepInEx/plugins/mod.dll').write_bytes(b'mod')
  (c['data']/'Blueprint/中文.txt').write_text('blueprint',encoding='utf-8')
  return c
 def initialize(self):
  v=g.publish(self.a,self.ra,self.sa,None);g.receive(self.b,self.rb,self.sb,v);return v
class GitHandoff(GitFixture,unittest.TestCase):
 def test_roundtrip_updates_only_changes(self):
  v=self.initialize();unchanged=self.b['game']/'BepInEx/plugins/mod.dll';mtime=unchanged.stat().st_mtime_ns
  (self.a['data']/'Save/a.dsv').write_bytes(b'new')
  v2=g.publish(self.a,self.ra,self.sa,v);self.assertNotEqual(v,v2);g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),b'new');self.assertEqual(unchanged.stat().st_mtime_ns,mtime)
 def test_local_blueprint_and_remote_save_merge(self):
  v=self.initialize();(self.b['data']/'Blueprint/新蓝图.txt').write_text('local',encoding='utf-8');(self.a['data']/'Save/a.dsv').write_bytes(b'new')
  v2=g.publish(self.a,self.ra,self.sa,v);g.receive(self.b,self.rb,self.sb,v2)
  self.assertTrue((self.b['data']/'Blueprint/新蓝图.txt').exists());v3=g.publish(self.b,self.rb,self.sb,v2);g.receive(self.a,self.ra,self.sa,v3)
  self.assertEqual((self.a['data']/'Blueprint/新蓝图.txt').read_text(encoding='utf-8'),'local')
 def test_binary_pair_conflict_preserves_local(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');(self.b['data']/'Save/a.moddsv').write_bytes(b'B');v2=g.publish(self.a,self.ra,self.sa,v)
  with self.assertRaises(ValueError):g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual((self.b['data']/'Save/a.moddsv').read_bytes(),b'B')
 def test_delete_preserves_backup(self):
  v=self.initialize();(self.a['game']/'BepInEx/plugins/mod.dll').unlink();v2=g.publish(self.a,self.ra,self.sa,v);g.receive(self.b,self.rb,self.sb,v2)
  self.assertFalse((self.b['game']/'BepInEx/plugins/mod.dll').exists());self.assertTrue(list(self.b['backup'].rglob('mod.dll')))
 def test_no_change_does_not_commit(self):
  v=self.initialize();self.assertEqual(g.publish(self.a,self.ra,self.sa,v),v)
 def test_stale_parent_cannot_overwrite_remote(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');v2=g.publish(self.a,self.ra,self.sa,v)
  (self.b['data']/'Save/a.dsv').write_bytes(b'B')
  with self.assertRaises(ValueError):g.publish(self.b,self.rb,self.sb,v)
  self.assertEqual(self.rb.fetch(),v2)
 def test_uncertain_push_recovered_without_duplicate_commit(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');original=self.ra.push
  def uncertain(commit,parent):original(commit,parent);raise RuntimeError('network ended before confirmation')
  with patch.object(self.ra,'push',side_effect=uncertain):
   with self.assertRaises(RuntimeError):g.publish(self.a,self.ra,self.sa,v)
  pushed=self.ra.fetch();self.assertNotEqual(pushed,v)
  result=g.publish(self.a,self.ra,self.sa,v)
  self.assertEqual(result,pushed);self.assertEqual(json.loads(self.sa.read_text())['revision'],pushed)
 def test_changed_live_data_during_stage_blocks(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');v2=g.publish(self.a,self.ra,self.sa,v);original=self.rb.materialize
  def race(commit,dest):
   result=original(commit,dest);(self.b['data']/'Save/a.dsv').write_bytes(b'external');return result
  with patch.object(self.rb,'materialize',side_effect=race):
   with self.assertRaises(ValueError):g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),b'external')
 def test_unresolved_transaction_blocks_receive(self):
  v=self.initialize();(self.sb.parent/'apply-journal.json').write_text('{}')
  with self.assertRaises(ValueError):g.receive(self.b,self.rb,self.sb,v)
 def test_credentials_in_remote_url_rejected(self):
  with self.assertRaises(ValueError):g.Remote({'git_remote':'https://user:secret@example.com/a.git','git_cache':str(self.root/'bad')})
 def test_executable_blueprint_is_normalized(self):
  (self.a['data']/'Blueprint/中文.txt').chmod(0o755)
  v=g.publish(self.a,self.ra,self.sa,None);g.receive(self.b,self.rb,self.sb,v)
  self.assertEqual((self.b['data']/'Blueprint/中文.txt').read_text(encoding='utf-8'),'blueprint')
 def test_git_ignores_do_not_exclude_supported_files(self):
  ignore=self.root/'ignore';ignore.write_text('*.dsv\n*.dll\n')
  self.ra.run('config','core.excludesFile',str(ignore))
  v=g.publish(self.a,self.ra,self.sa,None);g.receive(self.b,self.rb,self.sb,v)
  self.assertTrue((self.b['data']/'Save/a.dsv').exists())
 def test_windows_invalid_name_is_rejected(self):
  files=fs.scan(self.a);entry=next(iter(files.values()))
  for name in ['bad?.txt','bad*.txt','bad|.txt','bad<.txt','bad>.txt','bad".txt','bad\x01.txt']:
   with self.subTest(name=name),self.assertRaises(ValueError):fs.validate(dict(files,**{'data/Blueprint/'+name:entry}))
 def test_remote_content_tampering_is_rejected(self):
  v=self.initialize()
  with tempfile.TemporaryDirectory() as td:
   stage=Path(td);self.ra.materialize(v,stage);(stage/'.gitattributes').write_bytes(g.ATTRIBUTES)
   fs.atomic(stage/'manifest.json',self.ra.manifest(v));(stage/'files/data/Save/a.dsv').write_bytes(b'evil')
   bad=self.ra.commit(stage,v);self.ra.push(bad,v)
   with self.assertRaises(ValueError):g.receive(self.b,self.rb,self.sb,bad)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),b'save')
 def test_maintenance_preserves_committed_state(self):
  v=self.initialize();self.assertTrue(hasattr(self.ra,'maintain'),'Cache compaction is not implemented')
  self.ra.maintain(force=True);self.assertEqual(self.ra.manifest(v)['files'],fs.scan(self.a))
if __name__=='__main__':unittest.main()
