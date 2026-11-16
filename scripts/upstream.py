"""Published stable release identity and precise Git-commit changelog."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.parse

from contract import ROOT, identity
from registry import fetch

API='https://api.github.com/repos/toeverything/AFFiNE'
GIT='https://github.com/toeverything/AFFiNE.git'

def release(tag=None):
    data=json.loads(fetch(API+('/releases/tags/'+urllib.parse.quote(tag,safe='') if tag else '/releases/latest')))
    if data.get('draft') or data.get('prerelease') or (tag and data.get('tag_name')!=tag):raise ValueError('Expected a published stable Release')
    ref=json.loads(fetch(API+'/git/ref/tags/'+urllib.parse.quote(data['tag_name'],safe='')))['object']
    for _ in range(5):
        if ref['type']!='tag':break
        ref=json.loads(fetch(ref['url']))['object']
    if ref['type']!='commit':raise ValueError('Release tag does not resolve to a commit')
    version,image=identity(data['tag_name'],ref['sha'])
    return {'tag':data['tag_name'],'revision':ref['sha'],'version':version,'image':image}

def git_changes(directory,previous,current):
    if not all(re.fullmatch(r'[a-f0-9]{40}',v) for v in (previous,current)):raise ValueError('Expected immutable changelog bounds')
    def git(*args):return subprocess.check_output(['git','-C',str(directory),*args],text=True,timeout=180).strip()
    git('merge-base','--is-ancestor',previous,current)
    return git('log','--no-merges','--format=- %s (%h)','-60',previous+'..'+current)

def changelog():
    tag=os.environ['LAZYCAT_SOURCE_TAG'];sha=os.environ['LAZYCAT_SOURCE_REVISION']
    version,_=identity(tag,sha)
    if version!=os.environ['LAZYCAT_SOURCE_VERSION']:raise ValueError('Inconsistent selected source version')
    previous=os.environ.get('LAZYCAT_PREVIOUS_SOURCE_REVISION')
    if not previous:previous=release('v0.25.7')['revision']
    with tempfile.TemporaryDirectory(prefix='affine-changelog-') as directory:
        def git(*args):return subprocess.run(['git','-C',directory,*args],check=True,timeout=180,stdout=subprocess.DEVNULL)
        git('init','--quiet');git('remote','add','origin',GIT)
        git('fetch','--quiet','--filter=blob:none','--no-tags','origin',previous,sha)
        changes=git_changes(Path(directory),previous,sha)
    print(f'AFFiNE {version}\n\nUpstream commits since {previous[:7]} (up to 60 recent non-merge commits):\n{changes}\n\nhttps://github.com/toeverything/AFFiNE/compare/{previous}...{sha}')

if __name__=='__main__':
    if sys.argv[1:]!=['changelog']:raise SystemExit('Use: upstream.py changelog')
    changelog()
