from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from registry import checked_json, content_hash, verify_local

class RegistryTests(unittest.TestCase):
    def test_faithful_copy_of_initially_unlabeled_image_has_same_identity(self):
        import copy
        cfg={'os':'linux','architecture':'amd64','rootfs':{'diff_ids':['sha256:'+'a'*64]},'config':{'Cmd':['node']}}
        copied=copy.deepcopy(cfg);copied['config']['Labels']={'cloud.lazycat.image.origin_image':'ghcr.io/example/app:1','cloud.lazycat.image.origin_hash':'sha256:'+'b'*64,'cloud.lazycat.image.maintainer':'test'}
        self.assertEqual(content_hash(cfg),content_hash(copied))
        copied['config']['Labels']['real-runtime-label']='different'
        self.assertNotEqual(content_hash(cfg),content_hash(copied))
    def test_classic_and_containerd_docker_image_ids_still_require_exact_layers(self):
        image={'digest':'sha256:'+'a'*64,'config_digest':'sha256:'+'b'*64,
               'config':{'rootfs':{'diff_ids':['sha256:'+'c'*64]},'config':{'Cmd':['node','main.js']}}}
        for identity in (image['digest'],image['config_digest']):
            local={'Id':identity,'Os':'linux','Architecture':'amd64','RootFS':{'Layers':['sha256:'+'c'*64]},'Config':{'Cmd':['node','main.js']}}
            self.assertEqual(verify_local(image,local),identity)
            local['RootFS']['Layers']=['sha256:'+'d'*64]
            with self.assertRaises(ValueError):verify_local(image,local)
    def test_rejects_content_that_does_not_match_registry_digest(self):
        with self.assertRaises(ValueError):checked_json(b'{}','sha256:'+'a'*64)

    def test_copy_provenance_is_ignored_but_filesystem_and_runtime_changes_are_not(self):
        import copy
        cfg={'os':'linux','architecture':'amd64','rootfs':{'diff_ids':['sha256:'+'b'*64]},'config':{'Env':['PORT=3010'],'Labels':{'custom':'keep'}}}
        copied=copy.deepcopy(cfg);copied['config']['Labels']['cloud.lazycat.image.origin_image']='ghcr.io/example/image:1'
        self.assertEqual(content_hash(cfg),content_hash(copied))
        copied['config']['Env']=['PORT=9999']
        self.assertNotEqual(content_hash(cfg),content_hash(copied))
        with self.assertRaises(ValueError):content_hash({'config':{}})
