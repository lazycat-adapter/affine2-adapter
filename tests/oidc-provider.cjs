// Test-only OIDC provider: exercises signature, issuer, audience, nonce and PKCE.
// Never packaged or used by the installed application.
const http=require('node:http');
const crypto=require('node:crypto');
const {privateKey,publicKey}=crypto.generateKeyPairSync('rsa',{modulusLength:2048});
const issuer='http://oidc:9080';
const jwk={...publicKey.export({format:'jwk'}),kid:'adapter-test',use:'sig',alg:'RS256'};
const grants=new Map();
function token(claims){
  const encoded=Buffer.from(JSON.stringify({alg:'RS256',kid:jwk.kid})).toString('base64url')+'.'+Buffer.from(JSON.stringify(claims)).toString('base64url');
  return encoded+'.'+crypto.sign('RSA-SHA256',Buffer.from(encoded),privateKey).toString('base64url');
}
http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,issuer);
    const send=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
    if(url.pathname==='/.well-known/openid-configuration')return send({issuer,authorization_endpoint:issuer+'/auth',token_endpoint:issuer+'/token',userinfo_endpoint:issuer+'/userinfo',jwks_uri:issuer+'/keys',response_types_supported:['code'],subject_types_supported:['public'],id_token_signing_alg_values_supported:['RS256'],code_challenge_methods_supported:['S256']});
    if(url.pathname==='/keys')return send({keys:[jwk]});
    if(url.pathname==='/auth'){
      if(url.searchParams.get('client_id')!=='adapter-test'||url.searchParams.get('code_challenge_method')!=='S256')return send({error:'invalid_request'},400);
      const code=crypto.randomBytes(24).toString('hex');grants.set(code,Object.fromEntries(url.searchParams));
      const redirect=new URL(url.searchParams.get('redirect_uri'));redirect.searchParams.set('code',code);redirect.searchParams.set('state',url.searchParams.get('state'));
      res.writeHead(302,{Location:redirect.href});return res.end();
    }
    if(url.pathname==='/token'){
      let body='';for await(const chunk of req)body+=chunk;
      const form=new URLSearchParams(body),grant=grants.get(form.get('code'));grants.delete(form.get('code'));
      if(!grant||crypto.createHash('sha256').update(form.get('code_verifier')||'').digest('base64url')!==grant.code_challenge)return send({error:'invalid_grant'},400);
      const basic='Basic '+Buffer.from('adapter-test:adapter-test-secret').toString('base64');
      if(req.headers.authorization!==basic&&form.get('client_secret')!=='adapter-test-secret')return send({error:'invalid_client'},401);
      const now=Math.floor(Date.now()/1000);
      return send({access_token:'adapter-test-access',token_type:'Bearer',expires_in:300,id_token:token({iss:issuer,aud:'adapter-test',sub:'lazycat-test-user',iat:now,exp:now+300,nonce:grant.nonce,email:'oidc@example.com',email_verified:true,name:'LazyCat OIDC Test'})});
    }
    if(url.pathname==='/userinfo'){
      if(req.headers.authorization!=='Bearer adapter-test-access')return send({error:'unauthorized'},401);
      return send({sub:'lazycat-test-user',email:'oidc@example.com',email_verified:true,name:'LazyCat OIDC Test'});
    }
    send({error:'not_found'},404);
  }catch(error){res.writeHead(500);res.end(error.message);}
}).listen(9080,'0.0.0.0');
