'use strict';
// LazyCat rotates OIDC credentials on restart. Refresh only deployment-owned
// fields in config.json; preserve SMTP, quotas and other administrator settings.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');

function deploymentUrl(value, name) {
  if (!value || /[{}$]/.test(value)) throw new Error(`Missing/unrendered ${name}`);
  const url = new URL(value);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error(`Invalid ${name}`);
  return url.href.replace(/\/$/, '');
}
function mergeConfig(previous, env) {
  if (!previous || typeof previous !== 'object' || Array.isArray(previous)) throw new Error('Expected a config object');
  const value = structuredClone(previous);
  const externalUrl = deploymentUrl(env.AFFINE_EXTERNAL_URL, 'external URL');
  let issuer = env.AFFINE_OIDC_ISSUER;
  if (!issuer) {
    const auth = deploymentUrl(env.AFFINE_OIDC_AUTH_URI, 'OIDC authorization URL');
    if (!auth.endsWith('/auth')) throw new Error('Unexpected OIDC authorization path');
    issuer = auth.slice(0, -5);
  }
  issuer = deploymentUrl(issuer, 'OIDC issuer');
  for (const key of ['AFFINE_OIDC_CLIENT_ID','AFFINE_OIDC_CLIENT_SECRET']) {
    if (!env[key] || /[{}$]/.test(env[key])) throw new Error(`Missing/unrendered ${key}`);
  }
  value.server = {...value.server, name:value.server?.name || 'AFFiNE', externalUrl};
  value.indexer = {...value.indexer, enabled:false};
  value.oauth = {...value.oauth, providers:{...value.oauth?.providers,
    oidc:{...value.oauth?.providers?.oidc, issuer, clientId:env.AFFINE_OIDC_CLIENT_ID,
      clientSecret:env.AFFINE_OIDC_CLIENT_SECRET, allowPrivateNetwork:true,
      args:{...value.oauth?.providers?.oidc?.args, scope:'openid profile email'}}}};
  return value;
}
function writeConfig(file, env, previousOverride) {
  fs.mkdirSync(path.dirname(file), {recursive:true,mode:0o700});
  const previous = previousOverride===undefined ? (fs.existsSync(file) ? JSON.parse(fs.readFileSync(file,'utf8')) : {}) : previousOverride;
  const value = mergeConfig(previous, env);
  const temporary = `${file}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(temporary, JSON.stringify(value,null,2)+'\n', {mode:0o600});
    fs.renameSync(temporary, file);
  } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
  return value;
}
async function waitFor(host, port, timeoutMs=120000) {
  const deadline=Date.now()+timeoutMs;
  while (Date.now()<deadline) {
    const ready = await new Promise(resolve => {
      const socket=net.connect({host,port});
      const done=value=>{socket.destroy();resolve(value);};
      socket.setTimeout(2000);socket.once('connect',()=>done(true));socket.once('error',()=>done(false));socket.once('timeout',()=>done(false));
    });
    if (ready) return;
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  throw new Error(`Dependency did not become ready: ${host}:${port}`);
}
async function main() {
  writeConfig('/root/.affine/config/config.json', process.env);
  const db=new URL(process.env.DATABASE_URL);
  await waitFor(db.hostname,Number(db.port || 5432));
  await waitFor(process.env.REDIS_SERVER_HOST || 'redis',Number(process.env.REDIS_SERVER_PORT || 6379));
  console.log('LazyCat deployment configuration and dependencies ready.');
}
module.exports={mergeConfig,writeConfig,waitFor};
if (require.main===module) main().catch(error=>{console.error(error.message);process.exitCode=1;});
