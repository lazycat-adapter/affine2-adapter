"""Disposable real-image acceptance; resource-bounded and no production data."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.request
import urllib.parse

from contract import ROOT, CHECKS, recipe_hash, validate
from registry import pull

def docker(*args, timeout=180):
    return subprocess.check_output(['docker',*args],text=True,timeout=timeout).strip()

class Scope:
    def __init__(self,timeout=20):
        self.name='affine-ci-'+secrets.token_hex(6)
        self.containers=[];self.volumes=[];self.network=False;self.timeout=timeout
    def command(self,*args,timeout=None):
        return subprocess.run(['docker',*args],check=True,capture_output=True,text=True,timeout=timeout or self.timeout)
    def owned(self,kind,name):
        result=subprocess.run(['docker','inspect','--type',kind,name],capture_output=True,text=True,timeout=self.timeout)
        if result.returncode:
            if any(text in result.stderr.lower() for text in ('no such ','not found')):return False
            raise RuntimeError('Unable to verify resource ownership: '+kind+' '+name+': '+result.stderr)
        info=json.loads(result.stdout)[0]
        labels=info.get('Config',{}).get('Labels',{}) if kind=='container' else info.get('Labels',{})
        if not labels or labels.get('affine-adapter-test')!=self.name:
            raise RuntimeError('Refusing to use/remove foreign '+kind+' '+name)
        return True
    def create(self):
        # Register before the request: timeout does not prove the daemon did
        # not create the resource. Ownership is verified before use/removal.
        self.network=True;self.owned('network',self.name)
        self.command('network','create','--label','affine-adapter-test='+self.name,self.name)
        self.owned('network',self.name)
        for part in ('storage','config','postgres','redis'):
            name=self.name+'-'+part
            self.volumes.append(name)
            self.owned('volume',name)
            self.command('volume','create','--label','affine-adapter-test='+self.name,name)
            self.owned('volume',name)
    def run(self,part,image,extra=(),command=()):
        name=self.name+'-'+part
        if name not in self.containers:self.containers.append(name)
        self.owned('container',name)
        self.command('run','--detach','--label','affine-adapter-test='+self.name,'--name',name,'--network',self.name,
                     '--network-alias',part,*extra,image,*command,timeout=180)
        self.owned('container',name)
        return name
    def remove(self,part):
        name=self.name+'-'+part
        if not self.owned('container',name):return
        try:self.command('stop','--time','10',name)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):pass
        if self.owned('container',name):self.command('rm','--force','--volumes',name)
    def close(self):
        errors=[]
        for name in reversed(self.containers):
            try:self.remove(name.removeprefix(self.name+'-'))
            except Exception as error:errors.append(str(error))
        for name in reversed(self.volumes):
            try:
                if self.owned('volume',name):self.command('volume','rm',name)
            except Exception as error:errors.append(str(error))
        if self.network:
            try:
                if self.owned('network',self.name):self.command('network','rm',self.name)
            except Exception as error:errors.append(str(error))
        if errors:raise RuntimeError('Test resource cleanup failed: '+'; '.join(errors))

def wait(check, description, timeout=180):
    deadline=time.monotonic()+timeout;last=None
    while time.monotonic()<deadline:
        try:
            result=check()
            if result:return result
        except (OSError,urllib.error.URLError,subprocess.CalledProcessError,ValueError) as error:last=error
        time.sleep(2)
    raise RuntimeError(f'Timed out waiting for {description}: {last}')

class Client:
    def __init__(self,base):
        self.base=base;self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def request(self,path,data=None,headers=None):
        raw=json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request(self.base+path,data=raw,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with self.opener.open(request,timeout=30) as response:
                body=response.read();return json.loads(body) if 'json' in response.headers.get('Content-Type','') else body
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{path}: HTTP {error.code}: '+error.read(3000).decode(errors='replace')) from error
    def graphql(self,query,variables=None):
        value=self.request('/graphql',{'query':query,'variables':variables or {}})
        if value.get('errors'):raise RuntimeError('GraphQL failed: '+json.dumps(value['errors']))
        return value['data']
    def cookie(self):return '; '.join(c.name+'='+c.value for c in self.jar)

def verify(images,application_version,source,root=ROOT):
    _,manifest,_=validate(root)
    proof=root/'.lazycat-action/runtime-proof.json';proof.parent.mkdir(exist_ok=True)
    proof.unlink(missing_ok=True)
    recipe=recipe_hash(root);ids={name:pull(image) for name,image in images.items()}
    scope=Scope();report={};app=None
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env={**manifest['services']['affine']['environment'],
         'AFFINE_EXTERNAL_URL':base,'AFFINE_OIDC_CLIENT_ID':'adapter-test','AFFINE_OIDC_CLIENT_SECRET':'adapter-test-secret',
         'AFFINE_OIDC_ISSUER':'http://oidc:9080','NODE_OPTIONS':'--max-old-space-size=768'}
    def mounts(service):
        options=[]
        for bind in manifest['services'][service]['binds']:
            host,target=bind.split(':')
            volume=scope.name+'-'+host.rsplit('/',1)[1]
            options.extend(('-v',volume+':'+target))
        return options
    def start_dependencies():
        pg_options=['--memory','256m','--memory-swap','256m','--cpus','0.5',*mounts('postgres')]
        for key,value in manifest['services']['postgres']['environment'].items():pg_options.extend(('-e',key+'='+value))
        pg=scope.run('postgres',ids['postgres'],pg_options)
        redis=scope.run('redis',ids['redis'],('--memory','96m','--memory-swap','96m','--cpus','0.5',*mounts('redis')),
                        shlex.split(manifest['services']['redis']['command']))
        wait(lambda:docker('exec',pg,'pg_isready','-U','affine','-d','affine'),'PostgreSQL')
        wait(lambda:docker('exec',redis,'redis-cli','ping')=='PONG','Redis')
    def start_app():
        nonlocal app
        options=['--memory','1200m','--memory-swap','1200m','--cpus','1.5','--publish',f'127.0.0.1:{port}:3010',
                 *mounts('affine'),
                 '-v',str(root/'content')+':/lzcapp/pkg/content:ro',
                 '-v',str(root/'tests')+':/fixtures:ro']
        for key,value in env.items():options.extend(('-e',key+'='+value))
        app=scope.run('affine',ids['affine'],options,shlex.split(manifest['services']['affine']['command']))
        def ready():
            state=json.loads(docker('inspect','--format','{{json .State}}',app))
            if not state['Running']:raise RuntimeError('AFFiNE exited before readiness: '+json.dumps(state))
            try:return Client(base).request('/info')
            except RuntimeError:return None
        return wait(ready,'AFFiNE HTTP readiness',360)
    try:
        scope.create()
        start_dependencies()
        scope.run('oidc',ids['affine'],('--memory','96m','--memory-swap','96m','--cpus','0.5','--entrypoint','node','-v',str(root/'tests')+':/fixtures:ro'),('/fixtures/oidc-provider.cjs',))
        report['server']=start_app();client=Client(base)
        if report['server']['compatibility']!=source['version']:raise ValueError('Server version differs from selected stable source')
        password=secrets.token_urlsafe(18)
        admin=client.request('/api/setup/create-admin-user',{'name':'Adapter test','email':'admin@example.com','password':password})
        client=Client(base);user=client.request('/api/auth/sign-in',{'email':'admin@example.com','password':password})
        if not client.cookie():raise ValueError('Administrator login did not establish a session')
        report['administrator_id']=admin['id']
        workspace=client.graphql('mutation {createWorkspace {id}}')['createWorkspace']['id'];report['workspace_id']=workspace
        # The fixture exercises AFFiNE's real synchronization protocol and
        # filesystem blob API rather than inserting synthetic rows into SQL.
        fixture={'base':base,'cookie':client.cookie(),'workspace':workspace,'client_version':source['version']}
        output=docker('exec','-e','AFFINE_TEST='+json.dumps(fixture),app,'node','/fixtures/runtime-client.cjs',timeout=120)
        report['data']=json.loads(output)
        oidc_client=Client(base);nonce=secrets.token_urlsafe(24)
        oidc=oidc_client.request('/api/oauth/preflight',{'provider':'OIDC','client':'web','client_nonce':nonce,'redirect_uri':base+'/'})
        # Follow authorization from the app network, then exchange the signed
        # code through AFFiNE's real callback. No test credentials enter the LPK.
        redirect=docker('exec','-e','AUTH_URL='+oidc['url'],app,'node','-e',"fetch(process.env.AUTH_URL,{redirect:'manual'}).then(r=>console.log(r.headers.get('location')))")
        query=urllib.parse.parse_qs(urllib.parse.urlsplit(redirect).query)
        logged=oidc_client.request('/api/oauth/callback',{'code':query['code'][0],'state':query['state'][0],'client_nonce':nonce})
        if not logged.get('id') or not oidc_client.cookie():raise ValueError('OIDC callback did not establish an authenticated user')
        report['oidc']={'user_id':logged['id'],'issuer':'http://oidc:9080','pkce':'S256'}
        client.graphql('mutation($updates:[UpdateAppConfigInput!]!){updateAppConfig(updates:$updates)}',{'updates':[
            {'module':'server','key':'name','value':'Persistent administrator settings'},
            {'module':'server','key':'externalUrl','value':'http://obsolete.example'},
            {'module':'oauth','key':'providers.oidc','value':{'clientId':'obsolete','clientSecret':'obsolete','issuer':'http://oidc:9080','allowPrivateNetwork':True,'args':{'claim_name':'preferred_username'}}}]})
        scope.remove('affine');scope.remove('redis');scope.remove('postgres')
        # Recreate all three containers with the same named volumes. Both
        # configuration and the actual application data must still be present.
        start_dependencies()
        start_app();client=Client(base);client.request('/api/auth/sign-in',{'email':'admin@example.com','password':password})
        config=client.graphql('query {appConfig}')['appConfig']
        if config['server']['name']!='Persistent administrator settings':raise ValueError('Administrator settings were overwritten')
        if config['server']['externalUrl']!=base or config['oauth']['providers']['oidc']['clientId']!='adapter-test':
            raise ValueError('Stale database config overrode dynamic domain/OIDC identity')
        if config['oauth']['providers']['oidc']['args'].get('claim_name')!='preferred_username':
            raise ValueError('Administrator OIDC claim mapping lost after refresh')
        found=client.graphql('query {workspaces {id}}')['workspaces']
        if workspace not in [item['id'] for item in found]:raise ValueError('Workspace lost after recreation')
        fixture.update({'cookie':client.cookie(),'expected':report['data']})
        output=docker('exec','-e','AFFINE_TEST='+json.dumps(fixture),app,'node','/fixtures/runtime-client.cjs',timeout=120)
        if json.loads(output)!=report['data']:raise ValueError('Document/blob changed after recreation')
        if recipe_hash(root)!=recipe:raise ValueError('Deployment recipe changed during testing')
        value={'application_version':application_version,'source':source,'recipe_sha256':recipe,'checks':CHECKS,
               'images':{name:{k:image[k] for k in ('pinned_ref','content_sha256','config_digest')} for name,image in images.items()},'report':report}
    except BaseException:
        reports=root/'.lazycat-action/reports';reports.mkdir(exist_ok=True)
        for name in scope.containers:
            try:
                output=subprocess.run(['docker','logs','--tail','100',name],capture_output=True,text=True,timeout=15)
                (reports/(name+'.log')).write_text(output.stdout+output.stderr)
            except Exception as error:(reports/(name+'.log')).write_text('Unable to collect bounded diagnostic: '+str(error))
        raise
    finally:scope.close()
    proof.write_text(json.dumps(value,indent=2)+'\n')
    print('PASS: real AFFiNE setup, login, workspace, synchronization, blob, OIDC, persistence and config refresh.')
    return value
