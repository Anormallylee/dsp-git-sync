import unittest,json
from unittest.mock import patch
from test_git_sync import GitFixture
import launcher

class AdminRecovery(GitFixture,unittest.TestCase):
 def test_initial_source_can_resume_uncertain_push(self):
  real=self.ra.push
  def uncertain(commit,parent):real(commit,parent);raise RuntimeError('confirmation lost')
  patches=[patch.object(launcher,'load_settings',return_value=(self.a,{},self.sa.parent)),patch.object(launcher,'Remote',return_value=self.ra),patch('sys.argv',['launcher.py','init-source'])]
  with patches[0],patches[1],patches[2]:
   with patch.object(self.ra,'push',side_effect=uncertain):
    with self.assertRaises(RuntimeError):launcher.main()
   self.assertFalse(self.sa.exists());head=self.ra.fetch();launcher.main()
   self.assertEqual(json.loads(self.sa.read_text())['revision'],head)
