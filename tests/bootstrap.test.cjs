const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {mergeConfig, writeConfig} = require('../content/bootstrap.cjs');
const env = {AFFINE_EXTERNAL_URL:'https://affine.box.example', AFFINE_OIDC_CLIENT_ID:'test-client', AFFINE_OIDC_CLIENT_SECRET:'test-secret', AFFINE_OIDC_AUTH_URI:'https://box.example/sys/oauth/auth'};

test('refreshes deployment identity while preserving administrator settings', () => {
  const old = {server:{name:'My notes',externalUrl:'https://old.example'},mailer:{host:'smtp.example'},auth:{allowSignup:false},oauth:{providers:{github:{clientId:'custom'}}}};
  const next = mergeConfig(old, env);
  assert.equal(next.server.externalUrl, env.AFFINE_EXTERNAL_URL);
  assert.equal(next.server.name, 'My notes');
  assert.deepEqual(next.mailer, old.mailer);
  assert.deepEqual(next.auth, old.auth);
  assert.deepEqual(next.oauth.providers.github, old.oauth.providers.github);
  assert.equal(next.oauth.providers.oidc.issuer,'https://box.example/sys/oauth');
  assert.equal(next.oauth.providers.oidc.clientSecret,'test-secret');
  assert.equal(old.server.externalUrl,'https://old.example');
});
test('rejects unresolved, missing or malformed deployment values', () => {
  for (const overrides of [{AFFINE_EXTERNAL_URL:'https://{{ .S.AppDomain }}'}, {AFFINE_OIDC_CLIENT_SECRET:''}, {AFFINE_OIDC_AUTH_URI:'javascript:alert(1)'}, {AFFINE_OIDC_AUTH_URI:'https://box.example/not-auth'}]) {
    assert.throws(() => mergeConfig({}, {...env,...overrides}));
  }
});
test('writes private valid JSON atomically and refuses malformed user configuration', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'affine-config-test-'));
  try {
    const file = path.join(dir,'config.json');
    writeConfig(file, env);
    assert.equal(fs.statSync(file).mode & 0o777, 0o600);
    const value = JSON.parse(fs.readFileSync(file));
    value.mailer={host:'keep.example'};fs.writeFileSync(file,JSON.stringify(value));
    writeConfig(file, {...env,AFFINE_OIDC_CLIENT_SECRET:'rotated'});
    assert.equal(JSON.parse(fs.readFileSync(file)).mailer.host,'keep.example');
    fs.writeFileSync(file,'{broken');
    assert.throws(() => writeConfig(file,env));
    assert.equal(fs.readFileSync(file,'utf8'),'{broken');
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
