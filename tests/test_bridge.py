import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import git_sync as g
import file_sync as fs
from test_git_sync import GitFixture
try:import steam_bridge as bridge
except ImportError:bridge=None
class SteamLifecycle(GitFixture,unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(bridge,'Steam Git lifecycle is not implemented');super().setUp()
 def test_remote_receive_before_ready_and_upload_on_exit(self):
  v=self.initialize();(self.a['data']/'Save/a.dsv').write_bytes(b'from A');v2=g.publish(self.a,self.ra,self.sa,v)
  parent=bridge.prepare(self.b,self.rb,self.sb.parent);self.assertEqual(parent,v2)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),b'from A')
  (self.b['data']/'Save/a.dsv').write_bytes(b'played B');bridge.finish(self.b,self.rb,self.sb.parent,parent)
  self.assertFalse((self.sb.parent/'pending.json').exists());self.assertNotEqual(self.rb.fetch(),v2)
 def test_pending_plus_new_remote_blocks_start(self):
  v=self.initialize();fs.atomic(self.sb.parent/'pending.json',{'parent':v});(self.a['data']/'Save/a.dsv').write_bytes(b'A');g.publish(self.a,self.ra,self.sa,v)
  with self.assertRaises(ValueError):bridge.prepare(self.b,self.rb,self.sb.parent)
 def test_journal_blocks_even_when_remote_unchanged(self):
  self.initialize();(self.sb.parent/'apply-journal.json').write_text('{}')
  with self.assertRaises(ValueError):bridge.prepare(self.b,self.rb,self.sb.parent)
 def test_failed_finish_preserves_pending(self):
  self.initialize();parent=bridge.prepare(self.b,self.rb,self.sb.parent);(self.b['data']/'Save/a.dsv').write_bytes(b'new')
  with patch.object(self.rb,'push',side_effect=RuntimeError('offline')):
   with self.assertRaises(RuntimeError):bridge.finish(self.b,self.rb,self.sb.parent,parent)
  self.assertTrue((self.sb.parent/'pending.json').exists())
 def test_prelaunch_recovers_uncertain_previous_exit(self):
  self.initialize();parent=bridge.prepare(self.b,self.rb,self.sb.parent);(self.b['data']/'Save/a.dsv').write_bytes(b'new');real=self.rb.push
  def uncertain(commit,old):real(commit,old);raise RuntimeError('lost confirmation')
  with patch.object(self.rb,'push',side_effect=uncertain):
   with self.assertRaises(RuntimeError):bridge.finish(self.b,self.rb,self.sb.parent,parent)
  head=self.rb.fetch();self.assertEqual(bridge.prepare(self.b,self.rb,self.sb.parent),head)
