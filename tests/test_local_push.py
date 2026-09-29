"""The local GitLab push path reuses existing credentials without persisting them."""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import git_sync as g

class LocalPush(unittest.TestCase):
 def test_loopback_push_uses_origin_identity_without_storing_secret(self):
  with tempfile.TemporaryDirectory() as td:
   remote='https://gitlab.example.test/owner/saves.git'
   local='http://127.0.0.1:8081/owner/saves.git'
   r=g.Remote({'git_remote':remote,'git_local_push_url':local,'git_cache':str(Path(td)/'cache.git')})
   sent=[]
   def run(*args,**kwargs):sent.append((args,kwargs));return b''
   r.run=run
   credential=subprocess.CompletedProcess(['git','credential','fill'],0,stdout=b'protocol=https\nhost=gitlab.example.test\nusername=oauth2\npassword=test-secret\n',stderr=b'')
   with patch.object(g.subprocess,'run',return_value=credential):r.push('a'*40,None)
   self.assertEqual(len(sent),1)
   args,kw=sent[0];self.assertEqual(args[:3],('push','--porcelain',local))
   self.assertEqual(kw['env']['GIT_CONFIG_KEY_0'],'http.'+local+'.extraHeader')
   self.assertTrue(kw['env']['GIT_CONFIG_VALUE_0'].startswith('Authorization: Basic '))
   self.assertNotIn('test-secret',str(args))
   self.assertNotIn('test-secret',(r.repo/'config').read_text())
 def test_local_push_refuses_another_host_or_repository(self):
  with tempfile.TemporaryDirectory() as td:
   for url in ['http://example.test/owner/saves.git','http://127.0.0.1:8081/other/repo.git','http://user:pass@127.0.0.1:8081/owner/saves.git']:
    with self.subTest(url=url),self.assertRaises(ValueError):g.Remote({'git_remote':'https://gitlab.example.test/owner/saves.git','git_local_push_url':url,'git_cache':str(Path(td)/('cache-'+str(len(url))+'.git'))})
