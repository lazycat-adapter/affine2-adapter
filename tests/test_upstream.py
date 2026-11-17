from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import contextlib
import io
import os
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import upstream
from upstream import git_changes

class ChangelogTests(unittest.TestCase):
    def test_git_resolves_lightweight_and_annotated_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):return subprocess.check_output(['git','-C',directory,*args],text=True).strip()
            git('init','--quiet');git('config','user.email','test@example.com');git('config','user.name','Test')
            git('commit','--quiet','--allow-empty','-m','baseline');commit=git('rev-parse','HEAD')
            git('tag','v0.25.7');git('tag','-a','v0.27.4','-m','Release')
            self.assertEqual(upstream.tag_revision('v0.25.7',directory),commit)
            self.assertEqual(upstream.tag_revision('v0.27.4',directory),commit)
            with self.assertRaises(ValueError):upstream.tag_revision('v0.99.0',directory)

    def test_first_changelog_uses_git_for_baseline_and_managed_reader_for_current_release(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):return subprocess.check_output(['git','-C',directory,*args],text=True).strip()
            git('init','--quiet');git('config','user.email','test@example.com');git('config','user.name','Test')
            git('commit','--quiet','--allow-empty','-m','old history');git('tag','v0.25.7')
            git('commit','--quiet','--allow-empty','-m','current change');current=git('rev-parse','HEAD');git('tag','-a','v0.27.4','-m','Release')
            def metadata(url):
                if not url.endswith('/releases/tags/v0.27.4'):raise AssertionError('Baseline must not require GitHub REST API')
                return {'tag_name':'v0.27.4','draft':False,'prerelease':False}
            out=io.StringIO()
            with patch.object(upstream,'GIT',directory),patch.object(upstream,'github_json',metadata),patch.dict(os.environ,{'LAZYCAT_SOURCE_TAG':'v0.27.4','LAZYCAT_SOURCE_REVISION':current,'LAZYCAT_SOURCE_VERSION':'0.27.4','LAZYCAT_PREVIOUS_SOURCE_REVISION':''}),contextlib.redirect_stdout(out):upstream.changelog()
            self.assertIn('current change',out.getvalue());self.assertNotIn('old history',out.getvalue())
    def test_changelog_import_works_before_packaging_dependencies_are_installed(self):
        code="import sys;sys.path.insert(0,'scripts');import upstream"
        subprocess.run([sys.executable,'-S','-c',code],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True)
    def test_collects_only_commits_after_previous_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def git(*args):return subprocess.check_output(['git','-C',directory,*args],text=True).strip()
            git('init','--quiet');git('config','user.email','test@example.com');git('config','user.name','Test')
            git('commit','--quiet','--allow-empty','-m','old history that must be excluded');previous=git('rev-parse','HEAD')
            git('commit','--quiet','--allow-empty','-m','new Chinese document fix');current=git('rev-parse','HEAD')
            result=git_changes(root,previous,current)
            self.assertIn('new Chinese document fix',result)
            self.assertNotIn('old history that must be excluded',result)
            with self.assertRaises(ValueError):git_changes(root,'not-a-commit',current)
