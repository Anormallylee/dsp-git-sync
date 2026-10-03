import unittest,subprocess,os,threading
from unittest.mock import patch
from test_git_sync import GitFixture
import git_sync as g
import file_sync as fs

class PartialFetch(GitFixture,unittest.TestCase):
 def present(self,r,oid):
  return subprocess.run(r.command('cat-file','-e',oid),env=dict(r.env,GIT_NO_LAZY_FETCH='1'),capture_output=True).returncode==0
 def test_skips_intermediate_after_receive_publish_and_maintenance(self):
  first=self.initialize()
  (self.a['data']/'Save/a.dsv').write_bytes(os.urandom(100000))
  middle=g.publish(self.a,self.ra,self.sa,first)
  oid=self.ra.run('rev-parse',middle+':files/data/Save/a.dsv').decode().strip()
  (self.a['data']/'Save/a.dsv').write_bytes(b'latest')
  latest=g.publish(self.a,self.ra,self.sa,middle)
  self.assertEqual(self.rb.fetch(),latest)
  self.assertFalse(self.present(self.rb,oid))
  g.receive(self.b,self.rb,self.sb,latest)
  self.assertFalse(self.present(self.rb,oid))
  (self.b['data']/'Blueprint/new.txt').write_bytes(b'new')
  published=g.publish(self.b,self.rb,self.sb,latest)
  self.assertEqual(self.rb.fetch(),published)
  self.rb.maintain(force=True)
  self.assertFalse(self.present(self.rb,oid))
  self.assertTrue(self.rb.ancestor(first,published))
 def test_unsupported_filter_rejects_before_pack(self):
  head=g.publish(self.a,self.ra,self.sa,None)
  subprocess.run(['git','--git-dir='+str(self.origin),'config','uploadpack.allowFilter','false'],check=True)
  with self.assertRaises(RuntimeError):self.rb.fetch()
  self.assertFalse(list((self.rb.repo/'objects/pack').glob('*.pack')))
 def test_fresh_cache_fetches_only_latest_blobs(self):
  first=g.publish(self.a,self.ra,self.sa,None)
  (self.a['data']/'Save/a.dsv').write_bytes(os.urandom(100000))
  middle=g.publish(self.a,self.ra,self.sa,first)
  oid=self.ra.run('rev-parse',middle+':files/data/Save/a.dsv').decode().strip()
  (self.a['data']/'Save/a.dsv').write_bytes(b'latest')
  latest=g.publish(self.a,self.ra,self.sa,middle)
  self.assertEqual(self.rb.fetch(),latest)
  self.assertFalse(self.present(self.rb,oid))
  self.rb.materialize(latest,self.root/'materialized')
  self.assertFalse(self.present(self.rb,oid))
  self.assertEqual((self.root/'materialized/files/data/Save/a.dsv').read_bytes(),b'latest')
 def test_existing_full_cache_migrates_and_reuses_objects(self):
  first=g.publish(self.a,self.ra,self.sa,None)
  cache=self.root/'full-cache'
  subprocess.run(['git','clone','--bare',str(self.origin),str(cache)],check=True,capture_output=True)
  r=g.Remote({'git_remote':str(self.origin),'git_cache':str(cache)})
  with patch.object(r,'filter_capability',wraps=r.filter_capability) as capability:
   self.assertEqual(r.fetch(),first)
   r.materialize(first,self.root/'full-materialized')
  self.assertEqual(capability.call_count,1)
  self.assertEqual(r.run('config','remote.origin.promisor').strip(),b'true')
  (self.a['data']/'Save/a.dsv').write_bytes(os.urandom(100000))
  middle=g.publish(self.a,self.ra,self.sa,first)
  oid=self.ra.run('rev-parse',middle+':files/data/Save/a.dsv').decode().strip()
  (self.a['data']/'Save/a.dsv').write_bytes(b'latest')
  latest=g.publish(self.a,self.ra,self.sa,middle)
  self.assertEqual(r.fetch(),latest)
  r.materialize(latest,self.root/'new-materialized');r.maintain(force=True)
  self.assertFalse(self.present(r,oid))
 def test_undeclared_file_rejected_before_payload_fetch(self):
  head=g.publish(self.a,self.ra,self.sa,None)
  stage=self.root/'tampered';self.ra.materialize(head,stage)
  (stage/'.gitattributes').write_bytes(g.ATTRIBUTES)
  fs.atomic(stage/'manifest.json',self.ra.manifest(head))
  (stage/'unexpected.bin').write_bytes(os.urandom(100000))
  bad=self.ra.commit(stage,head);self.ra.push(bad,head)
  oid=self.ra.run('rev-parse',bad+':unexpected.bin').decode().strip()
  self.assertEqual(self.rb.fetch(),bad)
  with self.assertRaises(ValueError):self.rb.manifest(bad)
  self.assertFalse(self.present(self.rb,oid))
 def test_latest_blob_retrieval_failure_preserves_files_and_baseline(self):
  first=self.initialize();before=self.sb.read_bytes();files=fs.scan(self.b)
  (self.a['data']/'Save/a.dsv').write_bytes(b'latest')
  latest=g.publish(self.a,self.ra,self.sa,first)
  oid=self.ra.run('rev-parse',latest+':files/data/Save/a.dsv').decode().strip()
  original=self.rb.run
  def reject_blob(*args,**kwargs):
   if 'fetch' in args and oid in args:raise RuntimeError('Simulated latest blob retrieval failure')
   return original(*args,**kwargs)
  with patch.object(self.rb,'run',side_effect=reject_blob):
   with self.assertRaises(RuntimeError):g.receive(self.b,self.rb,self.sb,latest)
  self.assertEqual(self.sb.read_bytes(),before);self.assertEqual(fs.scan(self.b),files)
  self.assertFalse(self.present(self.rb,oid))
 def test_old_git_rejected_before_cache_initialization(self):
  with patch.object(g.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'git version 2.49.0\n',b'')):
   with self.assertRaises(RuntimeError):g.Remote({'git_remote':str(self.origin),'git_cache':str(self.root/'old-git')})
  self.assertFalse((self.root/'old-git/HEAD').exists())
 def test_similar_large_versions_do_not_require_missing_delta_base(self):
  # Protect the regression runner from the old wait-before-drain deadlock.
  original=g.subprocess.Popen
  def guarded(*args,**kwargs):
   p=original(*args,**kwargs)
   if 'archive' in args[0]:
    def terminate():
     if p.poll() is None:
      if os.name=='nt':subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
      else:p.kill()
    timer=threading.Timer(60,terminate);timer.daemon=True;timer.start();self.addCleanup(timer.cancel)
   return p
  guard=patch.object(g.subprocess,'Popen',side_effect=guarded);guard.start();self.addCleanup(guard.stop)
  data=bytearray(os.urandom(1024*1024));save=self.a['data']/'Save/a.dsv'
  save.write_bytes(data);first=self.initialize()
  data[100:200]=b'B'*100;save.write_bytes(data)
  middle=g.publish(self.a,self.ra,self.sa,first)
  oid=self.ra.run('rev-parse',middle+':files/data/Save/a.dsv').decode().strip()
  data[300:400]=b'C'*100;save.write_bytes(data)
  latest=g.publish(self.a,self.ra,self.sa,middle)
  # Force the origin to delta-compress the related versions before fetching.
  subprocess.run(['git','--git-dir='+str(self.origin),'repack','-a','-d','--window=50','--depth=50'],check=True,capture_output=True)
  g.receive(self.b,self.rb,self.sb,latest)
  self.assertEqual((self.b['data']/'Save/a.dsv').read_bytes(),bytes(data))
  self.assertFalse(self.present(self.rb,oid))
  (self.b['data']/'Blueprint/after.txt').write_bytes(b'after')
  published=g.publish(self.b,self.rb,self.sb,latest)
  self.assertEqual(self.rb.fetch(),published);self.rb.maintain(force=True)
  self.assertFalse(self.present(self.rb,oid))
