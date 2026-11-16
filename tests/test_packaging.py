from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_package import source_bindings, require_official, verify_source_snapshot

class PackagingTests(unittest.TestCase):
    def test_retargeted_git_or_image_tags_block_packaging(self):
        selected={'tag':'v0.27.4','revision':'a'*40,'version':'0.27.4'}
        images={'affine':{'ref':'ghcr.io/toeverything/affine:0.27.4','digest':'sha256:'+'b'*64}}
        verify_source_snapshot(selected,images,lambda tag:dict(selected),lambda ref:dict(images['affine']))
        with self.assertRaises(ValueError):verify_source_snapshot(selected,images,lambda tag:{**selected,'revision':'c'*40},lambda ref:dict(images['affine']))
        with self.assertRaises(ValueError):verify_source_snapshot(selected,images,lambda tag:dict(selected),lambda ref:{'digest':'sha256:'+'d'*64})
    def test_sources_are_scoped_to_services_and_must_be_pinned(self):
        digest='sha256:'+'a'*64
        text='services:\n  affine:\n    # upstream: ghcr.io/toeverything/affine:0.27.4@'+digest+'\n    image: registry.lazycat.cloud/peter/affine:abc\n  redis:\n    # upstream: docker.io/library/redis:7.4@'+digest+'\n    image: registry.lazycat.cloud/peter/redis:abc\n  postgres:\n    # upstream: docker.io/pgvector/pgvector:pg16@'+digest+'\n    image: registry.lazycat.cloud/peter/postgres:abc\n'
        result=source_bindings(text)
        self.assertEqual(result['affine'],'ghcr.io/toeverything/affine:0.27.4@'+digest)
        with self.assertRaises(ValueError):source_bindings(text.replace('@'+digest,''))
        with self.assertRaises(ValueError):source_bindings(text.replace('    # upstream: docker.io/library/redis:7.4@'+digest+'\n',''))

    def test_upstream_placeholder_images_never_pass_official_packaging(self):
        manifest={'services':{name:{'image':'registry.lazycat.cloud/peter/'+name+':123'} for name in ('affine','redis','postgres')}}
        require_official(manifest)
        manifest['services']['affine']['image']='ghcr.io/toeverything/affine:stable'
        with self.assertRaises(ValueError):require_official(manifest)
