"""Application-specific deployment and acceptance evidence contracts."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'cloud.lazycat.app.affine'
SERVICES = ('affine', 'redis', 'postgres')
CHECKS = ['fresh-install', 'admin-login', 'workspace', 'document-sync', 'blob-upload',
          'oidc-login', 'container-recreation', 'data-persistence', 'config-refresh']

def load(path):
    # Changelog discovery runs before packaging dependencies are installed.
    import yaml
    value = yaml.safe_load(Path(path).read_text())
    if not isinstance(value, dict): raise ValueError(f'Expected YAML object: {path}')
    return value

def identity(tag, revision):
    match = re.fullmatch(r'v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))', tag)
    if not match or not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Expected exact stable AFFiNE tag and immutable Git commit')
    version = match[1]
    return version, 'ghcr.io/toeverything/affine:' + version

def recipe_hash(root=ROOT):
    paths = [root / name for name in ('package.yml','lzc-manifest.yml','lzc-build.yml','lazycat-action.yml','icon.png')]
    if (root/'requirements-test.txt').exists():paths.append(root/'requirements-test.txt')
    for directory in ('content','scripts','tests'):
        paths.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    digest=hashlib.sha256()
    for path in sorted(paths):
        raw=path.read_bytes()
        if path.name in ('package.yml','lzc-manifest.yml'):
            doc=load(path)
            if path.name=='package.yml': doc['version']='<allocated-version>'
            else:
                for service in SERVICES: doc['services'][service]['image']='<delivered-image>'
            raw=json.dumps(doc,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        digest.update(str(path.relative_to(root)).encode()+b'\0'+raw+b'\0')
    return digest.hexdigest()

def verify_proof(proof, images, recipe, version):
    if proof.get('checks') != CHECKS: raise ValueError('Incomplete runtime verification')
    if proof.get('recipe_sha256') != recipe: raise ValueError('Tested deployment recipe changed')
    if proof.get('application_version') != version: raise ValueError('Tested application version differs')
    tested=proof.get('images',{})
    if set(tested)!=set(SERVICES) or set(images)!=set(SERVICES): raise ValueError('Missing tested service image')
    for service in SERVICES:
        if not tested[service].get('content_sha256') or tested[service]['content_sha256']!=images[service].get('content_sha256'):
            raise ValueError(f'Tested image content differs: {service}')

def validate(root=ROOT):
    cfg=load(root/'lazycat-action.yml');manifest=load(root/'lzc-manifest.yml');package=load(root/'package.yml')
    if cfg['version']!=2 or cfg['build']['prepare']!={'mode':'images'} or not cfg['build']['run_buildscript']:
        raise ValueError('Expected supported images mode and mandatory packaging tests')
    if package['package']!=PACKAGE or cfg['project']['target_arch']!='amd64':raise ValueError('Wrong package or platform')
    if tuple(map(int,str(package.get('min_os_version','0.0.0')).split('.'))) < (1,5,0):raise ValueError('LPK v2 requires lzcos 1.5.0+')
    if set(manifest['services'])!=set(SERVICES): raise ValueError('Expected three services')
    images={i['id']:i for i in cfg['images']}
    if set(images)!=set(SERVICES): raise ValueError('Expected three image bindings')
    if images['affine']['source']!='ghcr.io/toeverything/affine:{source_version}':raise ValueError('Must use upstream version, not allocated LPK version')
    for name in SERVICES:
        if images[name]['service']!=name or images[name]['delivery']['mode']!='lazycat':raise ValueError('Incorrect official image binding')
    for name in ('redis','postgres'):
        if not re.search(r'@sha256:[a-f0-9]{64}$',images[name]['source']):raise ValueError('Dependency image must be immutable')
    for service in manifest['services'].values():
        for bind in service.get('binds',[]):
            if bind.startswith('/lzcapp/var/') and not bind.startswith('/lzcapp/var/affine/'):
                raise ValueError('Unexpected legacy data path')
    expected_binds={
        'affine':['/lzcapp/var/affine/storage:/root/.affine/storage','/lzcapp/var/affine/config:/root/.affine/config','/lzcapp/pkg/content:/opt/lazycat:ro'],
        'redis':['/lzcapp/var/affine/redis:/data'],
        'postgres':['/lzcapp/var/affine/postgres:/var/lib/postgresql/data']}
    import shlex
    expected_command=['sh','-ec','node /opt/lazycat/bootstrap.cjs; node ./scripts/self-host-predeploy.js; node /opt/lazycat/refresh-managed.cjs; exec node ./dist/main.js']
    for name,service in manifest['services'].items():
        if sorted(service.get('binds',[]))!=sorted(expected_binds[name]):raise ValueError('Untested persistence/content mount: '+name)
        if set(service)-{'image','binds','command','environment','depends_on','healthcheck'}:raise ValueError('Untested service settings: '+name)
    if shlex.split(manifest['services']['affine']['command'])!=expected_command:raise ValueError('Untested AFFiNE startup command')
    app_env=manifest['services']['affine']['environment']
    expected_env={'REDIS_SERVER_HOST':'redis','DATABASE_URL':'postgresql://affine@postgres:5432/affine','AFFINE_INDEXER_ENABLED':'false',
                  'AFFINE_EXTERNAL_URL':'https://{{ .S.AppDomain }}','AFFINE_OIDC_CLIENT_ID':'${LAZYCAT_AUTH_OIDC_CLIENT_ID}',
                  'AFFINE_OIDC_CLIENT_SECRET':'${LAZYCAT_AUTH_OIDC_CLIENT_SECRET}','AFFINE_OIDC_ISSUER':'${LAZYCAT_AUTH_OIDC_ISSUER_URI}','TZ':'Asia/Shanghai'}
    if app_env!=expected_env:raise ValueError('Untested AFFiNE environment')
    if manifest['services']['postgres']['environment']!={'POSTGRES_USER':'affine','POSTGRES_DB':'affine','POSTGRES_INITDB_ARGS':'--data-checksums','POSTGRES_HOST_AUTH_METHOD':'trust'}:
        raise ValueError('Untested PostgreSQL identity/initialization')
    if manifest['services']['redis']['command']!='redis-server --appendonly yes':raise ValueError('Redis persistence differs from test')
    if manifest['application']['routes']!=['/=http://affine:3010'] or manifest['application']['oidc_redirect_path']!='/oauth/callback':raise ValueError('Untested application routing')
    return cfg,manifest,package
