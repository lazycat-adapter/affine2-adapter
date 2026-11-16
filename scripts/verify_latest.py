"""Read-only manual runtime verification; never copies images or submits review."""
import argparse
import json
from contract import ROOT,validate
from registry import inspect_image
from upstream import release
from verify_runtime import verify

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tag');args=parser.parse_args()
    cfg,_,_=validate();selected=release(args.tag)
    images={image['id']:inspect_image(image['source'].replace('{source_version}',selected['version'])) for image in cfg['images']}
    result=verify(images,selected['version'],selected)
    print(json.dumps({'source':selected,'checks':result['checks']},indent=2))

if __name__=='__main__':main()
