import unittest,os,json
from pathlib import Path
from unittest.mock import patch
import file_sync as fs
import git_sync as g
from test_git_sync import GitFixture
class Transactions(GitFixture,unittest.TestCase):
 def test_blueprint_conflict_preserves_both(self):
  v=self.initialize();(self.a['data']/'Blueprint/中文.txt').write_text('remote');v2=g.publish(self.a,self.ra,self.sa,v)
  (self.b['data']/'Blueprint/中文.txt').write_text('local');g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual((self.b['data']/'Blueprint/中文.txt').read_text(),'remote')
  copies=list((self.b['data']/'Blueprint').glob('中文.conflict-local-*.txt'));self.assertEqual(len(copies),1);self.assertEqual(copies[0].read_text(),'local')
 def test_replace_failure_rolls_back_all_completed_files(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');(self.a['data']/'Blueprint/中文.txt').write_text('B');v2=g.publish(self.a,self.ra,self.sa,v)
  before=fs.scan(self.b);original=fs.os.link
  def fail(src,dst):
   if str(dst)==str(self.b['data']/'Save/a.dsv') and Path(src).name.startswith('.dsp-sync-new-'):raise OSError('disk failure')
   return original(src,dst)
  with patch.object(fs.os,'link',side_effect=fail):
   with self.assertRaises(OSError):g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual(fs.scan(self.b),before);self.assertFalse((self.sb.parent/'apply-journal.json').exists())
 def test_failed_rollback_keeps_journal_and_original(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');v2=g.publish(self.a,self.ra,self.sa,v)
  original=fs.os.link
  def fail(src,dst):
   if str(dst)==str(self.b['data']/'Save/a.dsv'):raise OSError('persistent disk failure')
   return original(src,dst)
  with patch.object(fs.os,'link',side_effect=fail):
   with self.assertRaises(OSError):g.receive(self.b,self.rb,self.sb,v2)
  self.assertTrue((self.sb.parent/'apply-journal.json').exists())
  self.assertTrue(any(p.read_bytes()==b'save' for p in (self.b['data']/'Save').glob('.dsp-sync-original-*')))
  with self.assertRaises(ValueError):g.receive(self.b,self.rb,self.sb,v2)
 @unittest.skipIf(os.name=="nt", "Windows prevents renaming files held open by this test")
 def test_late_open_handle_write_preserved_in_backup(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'A');v2=g.publish(self.a,self.ra,self.sa,v)
  original=fs.os.replace
  with (self.b['data']/'Save/a.dsv').open('r+b') as handle:
   def late(src,dst):
    if Path(src).name.startswith('.dsp-sync-original-') and str(dst).endswith('/Save/a.dsv'):
     handle.seek(0);handle.write(b'late');handle.flush()
    return original(src,dst)
   with patch.object(fs.os,'replace',side_effect=late):g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),b'A')
  self.assertTrue(any(p.read_bytes()==b'late' for p in self.b['backup'].rglob('a.dsv')))
 def test_edit_while_replacement_is_prepared_is_preserved(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'remote');v2=g.publish(self.a,self.ra,self.sa,v)
  original=fs.shutil.copy2;target=self.b['data']/'Save/a.dsv';injected=[False]
  def copying(src,dst,*a,**kw):
   result=original(src,dst,*a,**kw)
   if Path(dst).name.startswith('.dsp-sync-new-') and Path(src).name=='a.dsv' and not injected[0]:
    injected[0]=True;target.write_bytes(b'external-new-save')
   return result
  with patch.object(fs.shutil,'copy2',side_effect=copying):
   with self.assertRaises(ValueError):g.receive(self.b,self.rb,self.sb,v2)
  self.assertEqual(target.read_bytes(),b'external-new-save')
  self.assertEqual(json.loads(self.sb.read_text())['revision'],v)
 def test_logging_cannot_fail_on_non_utf8_console(self):
  import io
  stream=io.TextIOWrapper(io.BytesIO(),encoding='cp1252')
  files=fs.scan(self.a);key='data/Blueprint/中文.txt';base={**files};local={**files};remote={**files}
  local[key]={'bytes':1,'sha256':'a'*64};remote[key]={'bytes':1,'sha256':'b'*64}
  with patch('sys.stdout',stream):result=fs.merge(base,local,remote)
  self.assertTrue(any('conflict-local' in k for k in result))
