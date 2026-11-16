import json,os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_runtime import Scope

class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/'daemon.json'
        self.db.write_text(json.dumps({'resources':{}}))
        shutil.copyfile(Path(__file__).with_name('fake-docker.py'),self.root/'docker');(self.root/'docker').chmod(0o755)
        self.env=patch.dict(os.environ,{'PATH':str(self.root)+os.pathsep+os.environ['PATH'],'AFFINE_FAKE_DOCKER':str(self.db)});self.env.start()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def state(self):return json.loads(self.db.read_text())
    def write(self,state):self.db.write_text(json.dumps(state))
    def test_create_error_after_daemon_success_is_still_cleaned_up(self):
        scope=Scope();state=self.state();state['fail_create']='volume';self.write(state)
        with self.assertRaises(subprocess.CalledProcessError):scope.create()
        scope.close();self.assertEqual(self.state()['resources'],{})
    def test_foreign_volume_is_never_removed(self):
        scope=Scope();name=scope.name+'-storage';scope.volumes.append(name)
        state=self.state();state['resources']['volume:'+name]={'affine-adapter-test':'another-owner'};self.write(state)
        with self.assertRaises(RuntimeError):scope.close()
        self.assertIn('volume:'+name,self.state()['resources'])
    def test_timeout_on_one_resource_does_not_skip_other_resources(self):
        scope=Scope(timeout=0.2);scope.create()
        stuck=scope.volumes[-1];state=self.state();state['sleep_rm']=['volume:'+stuck];self.write(state)
        with self.assertRaises(RuntimeError):scope.close()
        self.assertEqual(list(self.state()['resources']),['volume:'+stuck])
    def test_inspect_errors_are_not_treated_as_absent(self):
        scope=Scope();scope.create();state=self.state();name=scope.volumes[0]
        state['inspect_fail']=['volume:'+name];self.write(state)
        with self.assertRaises(RuntimeError):scope.close()
        self.assertIn('volume:'+name,self.state()['resources'])
