from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from upstream import git_changes

class ChangelogTests(unittest.TestCase):
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
