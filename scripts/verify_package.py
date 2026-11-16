"""Mandatory delivered-image acceptance, called by lzc-build.yml."""
import json
import re

from contract import ROOT,SERVICES,load,validate,recipe_hash,verify_proof
from registry import DIGEST,inspect_image
from upstream import release
from verify_runtime import verify

def source_bindings(text):
    result={}
    for service in SERVICES:
        match=re.search(r'(?m)^  '+service+r':\s*\n((?:^ {4,}.*\n|^\s*\n)*)',text)
        refs=re.findall(r'(?m)^\s*# upstream: (\S+)\s*$',match[1] if match else '')
        if len(refs)!=1 or '@' not in refs[0] or not DIGEST.fullmatch(refs[0].rsplit('@',1)[1]):
            raise ValueError('Missing immutable source annotation for '+service)
        result[service]=refs[0]
    return result

def require_official(manifest):
    for service in SERVICES:
        if not manifest['services'][service]['image'].startswith('registry.lazycat.cloud/'):
            raise ValueError('Official image delivery has not completed: '+service)

def verify_source_snapshot(selected,images,read_release=release,read_image=inspect_image):
    current=read_release(selected['tag'])
    if any(current.get(key)!=selected.get(key) for key in ('tag','revision','version')):
        raise ValueError('Selected Git release changed during acceptance')
    for service,image in images.items():
        if read_image(image['ref'])['digest']!=image['digest']:
            raise ValueError('Selected upstream image tag changed during acceptance: '+service)

def main(root=ROOT):
    cfg,manifest,package=validate(root);require_official(manifest)
    refs=source_bindings((root/'lzc-manifest.yml').read_text())
    match=re.fullmatch(r'ghcr.io/toeverything/affine:([0-9]+\.[0-9]+\.[0-9]+)@sha256:[a-f0-9]{64}',refs['affine'])
    if not match:raise ValueError('Unexpected AFFiNE source image')
    selected=release('v'+match[1])
    expected={image['id']:image['source'].replace('{source_version}',selected['version']) for image in cfg['images']}
    delivered={};sources={}
    for service in SERVICES:
        source=inspect_image(expected[service])
        if source['pinned_ref']!=refs[service]:raise ValueError('Delivered source differs from selected upstream: '+service)
        image=inspect_image(manifest['services'][service]['image'])
        if image['content_sha256']!=source['content_sha256']:raise ValueError('Official copy changed image content: '+service)
        delivered[service]=image;sources[service]=source
    proof=verify(delivered,package['version'],selected,root)
    verify_proof(proof,delivered,recipe_hash(root),package['version'])
    # Re-resolve after testing: even a tag being replaced during acceptance
    # must not let the final manifest name an image different from the test.
    try:
        verify_source_snapshot(selected,sources)
        for service,image in delivered.items():
            if inspect_image(manifest['services'][service]['image'])['digest']!=image['digest']:
                raise ValueError('Official image reference changed during testing')
    except BaseException:
        (root/'.lazycat-action/runtime-proof.json').unlink(missing_ok=True)
        raise
    print('PASS: selected upstream, all official image contents, deployment and runtime acceptance verified.')

if __name__=='__main__':main()
