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
from github_api import github_json

API='https://api.github.com/repos/toeverything/AFFiNE'
GIT='https://github.com/toeverything/AFFiNE.git'

def release(tag=None):
    data=github_json(API+('/releases/tags/'+urllib.parse.quote(tag,safe='') if tag else '/releases/latest'))
    if data.get('draft') or data.get('prerelease') or (tag and data.get('tag_name')!=tag):raise ValueError('Expected a published stable Release')
    sha=tag_revision(data['tag_name'])
    version,image=identity(data['tag_name'],sha)
    return {'tag':data['tag_name'],'revision':sha,'version':version,'image':image}

def tag_revision(tag,repository=None):
    identity(tag,'0'*40)
    ref='refs/tags/'+tag
    raw=subprocess.check_output(['git','ls-remote','--tags',str(repository or GIT),ref,ref+'^{}'],text=True,timeout=90)
    refs={name:sha for line in raw.splitlines() if len(parts:=line.split())==2 for sha,name in [parts]}
    sha=refs.get(ref+'^{}') or refs.get(ref)
    if not sha or not re.fullmatch('[a-f0-9]{40}',sha):raise ValueError('Stable Git tag is missing or invalid: '+tag)
    return sha

def git_changes(directory,previous,current):
    if not all(re.fullmatch(r'[a-f0-9]{40}',v) for v in (previous,current)):raise ValueError('Expected immutable changelog bounds')
    def git(*args):return subprocess.check_output(['git','-C',str(directory),*args],text=True,timeout=180).strip()
    git('merge-base','--is-ancestor',previous,current)
    return git('log','--no-merges','--format=- %s (%h)','-60',previous+'..'+current)

def changelog():
    tag=os.environ['LAZYCAT_SOURCE_TAG'];sha=os.environ['LAZYCAT_SOURCE_REVISION']
    version,_=identity(tag,sha)
    if version!=os.environ['LAZYCAT_SOURCE_VERSION']:raise ValueError('Inconsistent selected source version')
    selected=release(tag)
    if selected['revision']!=sha:raise ValueError('Selected stable tag moved before changelog generation')
    previous=os.environ.get('LAZYCAT_PREVIOUS_SOURCE_REVISION')
    if not previous:previous=tag_revision('v0.25.7')
    with tempfile.TemporaryDirectory(prefix='affine-changelog-') as directory:
        def git(*args):return subprocess.run(['git','-C',directory,*args],check=True,timeout=180,stdout=subprocess.DEVNULL)
        git('init','--quiet');git('remote','add','origin',GIT)
        git('fetch','--quiet','--filter=blob:none','--no-tags','origin',previous,sha)
        changes=git_changes(Path(directory),previous,sha)
    print(f'AFFiNE {version}\n\nUpstream commits since {previous[:7]} (up to 60 recent non-merge commits):\n{changes}\n\nhttps://github.com/toeverything/AFFiNE/compare/{previous}...{sha}')

if __name__=='__main__':
    if sys.argv[1:]!=['changelog']:raise SystemExit('Use: upstream.py changelog')
    changelog()
