import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from contract import ROOT, identity, recipe_hash, verify_proof, validate, CHECKS


class ContractTests(unittest.TestCase):
    def test_startup_reads_scripts_from_the_runtime_content_directory(self):
        _, manifest, _ = validate()
        service = manifest['services']['affine']
        self.assertFalse(any(bind.startswith('/lzcapp/pkg/content:') for bind in service['binds']))
        for script in ('bootstrap.cjs', 'refresh-managed.cjs'):
            self.assertIn(f'node /lzcapp/pkg/content/{script}', service['command'])

    def test_installed_manifest_cannot_diverge_from_tested_runtime(self):
        import shutil,yaml
        for mutation in ('missing-storage','wrong-command','wrong-database','old-os'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                for name in ('lazycat-action.yml','lzc-manifest.yml','package.yml'):shutil.copyfile(ROOT/name,root/name)
                manifest=yaml.safe_load((root/'lzc-manifest.yml').read_text())
                if mutation=='missing-storage':manifest['services']['affine']['binds'].pop(0)
                if mutation=='wrong-command':manifest['services']['affine']['command']='node other.js'
                if mutation=='wrong-database':manifest['services']['affine']['environment']['DATABASE_URL']='postgresql://wrong@postgres/wrong'
                if mutation=='old-os':
                    p=yaml.safe_load((root/'package.yml').read_text());p['min_os_version']='1.3.5';(root/'package.yml').write_text(yaml.safe_dump(p))
                (root/'lzc-manifest.yml').write_text(yaml.safe_dump(manifest))
                with self.assertRaises(ValueError):validate(root)
    def test_exact_stable_source_version_controls_image_tag(self):
        self.assertEqual(identity('v0.27.4', 'a'*40), ('0.27.4', 'ghcr.io/toeverything/affine:0.27.4'))
        for tag in ('stable', 'v0.27.5-beta.2', 'v2026.11.13-canary.905', 'v01.27.4', 'v0.27.4-junk'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                identity(tag, 'a'*40)
        with self.assertRaises(ValueError):
            identity('v0.27.4', 'not-a-commit')

    def test_recipe_hash_ignores_only_allocated_version_and_delivered_images(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'scripts').mkdir();(root/'content').mkdir()
            (root/'package.yml').write_text('package: cloud.lazycat.app.affine2\nversion: 0.25.7\n')
            (root/'lzc-manifest.yml').write_text('services:\n  affine: {image: old, command: start}\n  redis: {image: old}\n  postgres: {image: old}\n')
            (root/'lzc-build.yml').write_text('manifest: lzc-manifest.yml\n')
            (root/'lazycat-action.yml').write_text('version: 2\n')
            (root/'icon.png').write_bytes(b'icon');(root/'content/bootstrap.cjs').write_text('bootstrap')
            first=recipe_hash(root)
            (root/'package.yml').write_text('package: cloud.lazycat.app.affine2\nversion: 0.27.4\n')
            manifest=yaml.safe_load((root/'lzc-manifest.yml').read_text());manifest['services']['affine']['image']='registry.lazycat.cloud/peter/new:abc'
            (root/'lzc-manifest.yml').write_text(yaml.safe_dump(manifest))
            self.assertEqual(first,recipe_hash(root))
            (root/'content/bootstrap.cjs').write_text('changed bootstrap')
            self.assertNotEqual(first,recipe_hash(root))

    def test_partial_or_different_runtime_evidence_is_rejected(self):
        images={name:{'content_sha256':'sha256:'+'a'*64} for name in ('affine','redis','postgres')}
        proof={'checks':CHECKS, 'recipe_sha256':'recipe', 'application_version':'0.27.4','images':images}
        verify_proof(proof,images,'recipe','0.27.4')
        for changes in ({'checks':CHECKS[:-1]}, {'recipe_sha256':'other'}, {'application_version':'0.27.5'}, {'images':{'affine':images['affine']}}):
            broken=copy.deepcopy(proof);broken.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                verify_proof(broken,images,'recipe','0.27.4')
        changed=copy.deepcopy(images);changed['postgres']['content_sha256']='sha256:'+'b'*64
        with self.assertRaises(ValueError):verify_proof(proof,changed,'recipe','0.27.4')

if __name__ == '__main__':unittest.main()
