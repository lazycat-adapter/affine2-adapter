"""Anonymous, digest-verified OCI metadata and official CDN image loading."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

DIGEST=re.compile(r'sha256:[a-f0-9]{64}')
ACCEPT=', '.join(('application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json','application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json'))
CDN='https://registry-static.lazycat.cloud/docker/registry/v2/'

def fetch(url,headers=None):
    request=urllib.request.Request(url,headers={'User-Agent':'affine-lazycat-adapter/1',**(headers or {})})
    with urllib.request.urlopen(request,timeout=60) as response:data=response.read(16*1024*1024+1)
    if len(data)>16*1024*1024:raise ValueError('Oversized image metadata')
    return data

def checked_json(raw,digest):
    if not DIGEST.fullmatch(digest) or 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError('Registry content does not match digest')
    return json.loads(raw)

def blob_url(digest):
    if not DIGEST.fullmatch(digest):raise ValueError('Invalid blob digest')
    value=digest[7:]
    return CDN+'blobs/sha256/'+value[:2]+'/'+value+'/data'

def content_hash(config):
    value=json.loads(json.dumps(config))
    if not value.get('rootfs',{}).get('diff_ids'):raise ValueError('Image filesystem identity missing')
    labels=value.get('config',{}).get('Labels',{}) or {}
    for key in ('cloud.lazycat.image.maintainer','cloud.lazycat.image.origin_hash','cloud.lazycat.image.origin_image'):labels.pop(key,None)
    # Official copy can introduce Labels where the source omitted it. An
    # absent/null/empty label map has identical effective runtime behavior.
    if labels:value['config']['Labels']=labels
    else:value.get('config',{}).pop('Labels',None)
    # Creation time/history can change on copy. All effective runtime settings
    # and every uncompressed layer must remain exactly the same.
    return 'sha256:'+hashlib.sha256(json.dumps({key:value.get(key) for key in ('os','architecture','rootfs','config')},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def inspect_image(reference):
    host,path=reference.split('/',1)
    if '@' in path:repo,selector=path.rsplit('@',1);repo=repo.split(':',1)[0]
    else:repo,selector=path.rsplit(':',1)
    if not re.fullmatch(r'[a-z0-9_./-]+',repo):raise ValueError('Invalid image repository')
    official=host=='registry.lazycat.cloud'
    if official:
        digest=selector if DIGEST.fullmatch(selector) else fetch(CDN+'repositories/'+repo+'/_manifests/tags/'+urllib.parse.quote(selector,safe='')+'/current/link').decode().strip()
        raw=fetch(blob_url(digest));manifest=checked_json(raw,digest)
        def read_blob(value):return fetch(blob_url(value))
    else:
        if host not in ('ghcr.io','docker.io'):raise ValueError('Unexpected source registry')
        endpoint='registry-1.docker.io' if host=='docker.io' else host
        headers={'Accept':ACCEPT}
        def request(suffix):
            url='https://'+endpoint+'/v2/'+repo+'/'+suffix
            try:return fetch(url,headers)
            except urllib.error.HTTPError as error:
                if error.code!=401:raise
                fields=dict(re.findall(r'(\w+)="([^"]*)"',error.headers.get('WWW-Authenticate','')))
                if not fields.get('realm','').startswith('https://'):raise ValueError('Invalid registry authentication realm')
                token=json.loads(fetch(fields['realm']+'?'+urllib.parse.urlencode({'service':fields.get('service',''),'scope':fields.get('scope','repository:'+repo+':pull')})))
                headers['Authorization']='Bearer '+(token.get('token') or token['access_token'])
                return fetch(url,headers)
        raw=request('manifests/'+selector);digest='sha256:'+hashlib.sha256(raw).hexdigest()
        if DIGEST.fullmatch(selector):checked_json(raw,selector)
        manifest=json.loads(raw)
        def read_blob(value):return request('blobs/'+value)
    if 'manifests' in manifest:
        matches=[m for m in manifest['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64']
        if len(matches)!=1:raise ValueError('Expected one linux/amd64 image')
        digest=matches[0]['digest'];raw=read_blob(digest) if official else request('manifests/'+digest)
        manifest=checked_json(raw,digest)
    config=checked_json(read_blob(manifest['config']['digest']),manifest['config']['digest'])
    if config.get('os')!='linux' or config.get('architecture')!='amd64':raise ValueError('Unexpected image platform')
    return {'ref':reference,'pinned_ref':reference.split('@')[0]+'@'+digest,'digest':digest,
            'config_digest':manifest['config']['digest'],'content_sha256':content_hash(config),
            'config':config,'manifest':manifest,'manifest_raw':raw}

@contextmanager
def official_registry(image):
    """Allowlisted loopback view of the public CDN; no daemon config/login changes."""
    raw=image['manifest_raw'];digest=image['digest'];manifest=checked_json(raw,digest)
    allowed={entry['digest'] for entry in manifest['layers']}|{manifest['config']['digest']}
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):self.do_GET()
        def do_GET(self):
            path=urllib.parse.urlsplit(self.path).path.rstrip('/')
            if path=='/v2':body,kind=b'{}','application/json'
            elif path=='/v2/image/manifests/'+digest:body,kind=raw,manifest.get('mediaType','application/vnd.oci.image.manifest.v1+json')
            elif path.startswith('/v2/image/blobs/') and path.rsplit('/',1)[1] in allowed:
                self.send_response(307);self.send_header('Location',blob_url(path.rsplit('/',1)[1]));self.send_header('Content-Length','0');self.end_headers();return
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Docker-Distribution-Api-Version','registry/2.0');self.send_header('Docker-Content-Digest',digest);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers()
            if self.command!='HEAD':self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True);thread.start()
    try:yield f'127.0.0.1:{server.server_port}/image@{digest}'
    finally:server.shutdown();server.server_close();thread.join(timeout=5)

def pull(image):
    # Docker's classic store uses config IDs; the containerd store uses
    # manifest IDs. Both must match the selected manifest and actual layers.
    for reference in (image['pinned_ref'],image['digest'],image['config_digest']):
        found=subprocess.run(['docker','image','inspect',reference],capture_output=True,text=True)
        if not found.returncode:return verify_local(image,json.loads(found.stdout)[0])
    return pull_missing(image)

def verify_local(image,local):
    if local.get('Id') not in (image['digest'],image['config_digest']) or local.get('Os')!='linux' or local.get('Architecture')!='amd64':
        raise ValueError('Pulled image identity/platform differs')
    if local.get('RootFS',{}).get('Layers')!=image['config']['rootfs']['diff_ids']:
        raise ValueError('Pulled filesystem differs')
    for key in ('Env','Cmd','Entrypoint','WorkingDir','User'):
        actual=local.get('Config',{}).get(key)
        expected=image['config'].get('config',{}).get(key)
        # Docker API 1.48 emits empty scalar defaults; newer APIs may omit
        # them. Normalize only these two optional strings, never real users,
        # paths, commands, environment values or non-string values such as 0.
        if key in ('User','WorkingDir'):
            if actual is None:actual=''
            if expected is None:expected=''
        if actual!=expected:
            raise ValueError('Pulled runtime configuration differs: '+key)
    return local['Id']

def pull_missing(image):
    if image['ref'].startswith('registry.lazycat.cloud/'):
        with official_registry(image) as reference:
            subprocess.run(['docker','pull','--platform','linux/amd64',reference],check=True,timeout=900)
            result=json.loads(subprocess.check_output(['docker','image','inspect',reference]))[0]
    else:
        # Do not inherit a stale/incorrect registry login from the workstation.
        with tempfile.TemporaryDirectory(prefix='affine-docker-auth-') as config_dir:
            subprocess.run(['docker','--config',config_dir,'pull','--platform','linux/amd64',image['pinned_ref']],check=True,timeout=900)
        result=json.loads(subprocess.check_output(['docker','image','inspect',image['pinned_ref']]))[0]
    return verify_local(image,result)
