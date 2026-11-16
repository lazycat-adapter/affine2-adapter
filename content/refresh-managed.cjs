'use strict';
// Run AFTER the official migrations. AFFiNE's saved Admin Panel settings have
// higher priority than config.json. Remove only deployment-owned overrides so
// a previous UI edit cannot retain a stale domain or rotated OIDC credential.
// Other administrator settings and all user/workspace data are untouched.
const {PrismaClient}=require('/app/node_modules/@prisma/client');
const fs=require('node:fs');
const {writeConfig}=require('./bootstrap.cjs');
async function main(){
  const db=new PrismaClient();
  try{
    const saved=await db.appConfig.findUnique({where:{id:'oauth.providers.oidc'}});
    if(saved){
      if(!saved.value||typeof saved.value!=='object'||Array.isArray(saved.value))throw Error('Invalid saved OIDC configuration');
      const file='/root/.affine/config/config.json';
      const config=JSON.parse(fs.readFileSync(file,'utf8'));
      const previous=config.oauth?.providers?.oidc || {};
      config.oauth={...config.oauth,providers:{...config.oauth?.providers,
        oidc:{...previous,...saved.value,args:{...previous.args,...saved.value.args}}}};
      // Move custom mappings to the persistent file, while writeConfig refreshes
      // only deployment-owned issuer/client credentials. No stale credential
      // is ever written, and no administrator claim mapping is discarded.
      writeConfig(file,process.env,config);
    }
    await db.appConfig.deleteMany({where:{id:{in:['server.externalUrl','oauth.providers.oidc','indexer.enabled']}}});
  }finally{await db.$disconnect();}
}
main().catch(error=>{console.error('Unable to refresh deployment-owned settings:',error.message);process.exitCode=1;});
