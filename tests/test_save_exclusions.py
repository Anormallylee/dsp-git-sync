import unittest
from unittest.mock import patch
from test_git_sync import GitFixture
import git_sync as g
import file_sync as fs

STEMS = ['Codex-batched-dismantle-test', '_autosave_errored', *['_autosave_'+str(i) for i in range(4)]]
NAMES = [stem+ext for stem in STEMS for ext in ('.dsv', '.moddsv')]

class SaveExclusions(GitFixture, unittest.TestCase):
 def add_saves(self, device):
  for name in NAMES+['_lastexit_.dsv', '_lastexit_.moddsv']:
   (device['data']/'Save'/name).write_bytes(name.encode())
 def legacy_publish(self, parent=None):
  # Simulate a sender running the previous inventory policy.
  with patch.object(fs.f, 'excluded_save', return_value=False, create=True):
   return g.publish(self.a, self.ra, self.sa, parent)
 def test_inventory_excludes_requested_pairs_but_retains_exit_save(self):
  self.add_saves(self.a);files=fs.scan(self.a)
  for name in NAMES:self.assertNotIn('data/Save/'+name, files)
  for name in ['_lastexit_.dsv', '_lastexit_.moddsv']:
   self.assertIn('data/Save/'+name, files)
  (self.a['data']/'Blueprint/_autosave_0.dsv').write_bytes(b'blueprint')
  self.assertIn('data/Blueprint/_autosave_0.dsv', fs.scan(self.a))
 def test_legacy_receive_preserves_local_ignored_saves_without_conflict(self):
  self.add_saves(self.a);first=self.legacy_publish()
  with patch.object(fs.f, 'excluded_save', return_value=False):
   g.receive(self.b,self.rb,self.sb,first)
  for name in NAMES:(self.b['data']/'Save'/name).write_bytes(b'local-only')
  (self.a['data']/'Save/a.dsv').write_bytes(b'updated')
  for name in NAMES:(self.a['data']/'Save'/name).write_bytes(b'changed-remote')
  latest=self.legacy_publish(first)
  g.receive(self.b,self.rb,self.sb,latest)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),b'updated')
  for name in NAMES:self.assertEqual((self.b['data']/'Save'/name).read_bytes(),b'local-only')
 def test_fresh_receive_skips_ignored_payload_and_files(self):
  self.add_saves(self.a);head=self.legacy_publish()
  oid=self.ra.run('rev-parse',head+':files/data/Save/_autosave_0.dsv').decode().strip()
  g.receive(self.b,self.rb,self.sb,head)
  for name in NAMES:self.assertFalse((self.b['data']/'Save'/name).exists())
  self.assertTrue((self.b['data']/'Save/_lastexit_.dsv').exists())
  result=g.subprocess.run(self.rb.command('cat-file','-e',oid),env=self.rb.local_env,capture_output=True)
  self.assertNotEqual(result.returncode,0)
 def test_publish_removes_tracked_ignored_files_and_preserves_local_files(self):
  self.add_saves(self.a);head=self.legacy_publish()
  before={name:(self.a['data']/'Save'/name).read_bytes() for name in NAMES}
  latest=g.publish(self.a,self.ra,self.sa,head)
  self.assertNotEqual(head,latest)
  files=self.ra.manifest(latest)['files']
  for name in NAMES:
   self.assertNotIn('data/Save/'+name,files)
   self.assertEqual((self.a['data']/'Save'/name).read_bytes(),before[name])
  self.assertIn('data/Save/_lastexit_.dsv',files)
