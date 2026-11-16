// Real Socket.IO polling transport using only Node built-ins and the image's
// Yjs implementation. No npm install, external site or direct database writes.
const Y=require('/app/node_modules/yjs');
const crypto=require('node:crypto');
const input=JSON.parse(process.env.AFFINE_TEST);
const base='http://127.0.0.1:3010';
const headers={Cookie:input.cookie};
class Socket {
  constructor(){this.id=0;this.events=[];}
  async request(method,data){
    const url=base+'/socket.io/?EIO=4&transport=polling'+(this.sid?'&sid='+this.sid:'')+'&t='+Date.now();
    const res=await fetch(url,{method,headers:{...headers,'Content-Type':'text/plain'},body:data,signal:AbortSignal.timeout(30000)});
    if(!res.ok)throw Error('Socket.IO HTTP '+res.status+': '+await res.text());
    return res.text();
  }
  async poll(){
    const packets=(await this.request('GET')).split('\x1e');
    for(const p of packets){if(p==='2')await this.request('POST','3');else if(p.startsWith('42'))this.events.push(JSON.parse(p.slice(2)));}
    return packets;
  }
  async open(){
    const raw=await this.request('GET');if(!raw.startsWith('0'))throw Error('Bad Engine.IO handshake: '+raw);
    this.sid=JSON.parse(raw.slice(1)).sid;await this.request('POST','40');await this.poll();
    const joined=await this.call('space:join',{spaceType:'workspace',spaceId:input.workspace,clientVersion:input.client_version});
    if(!joined.success)throw Error('Workspace synchronization join rejected');
  }
  async call(event,payload){
    const id=++this.id;await this.request('POST','42'+id+JSON.stringify([event,payload]));
    for(let count=0;count<10;count++)for(const packet of await this.poll()){
      if(packet.startsWith('43'+id+'[')){
        const result=JSON.parse(packet.slice(2+String(id).length))[0];
        if(result.error)throw Error(JSON.stringify(result.error));
        if(!('data' in result))throw Error('Missing synchronization result: '+JSON.stringify(result));
        return result.data;
      }
    }
    throw Error('Missing Socket.IO acknowledgment: '+event);
  }
  async close(){if(this.sid)await this.request('POST','41');}
}
function block(id,flavour,children=[]){const value=new Y.Map();value.set('sys:id',id);value.set('sys:flavour',flavour);value.set('sys:version',1);const array=new Y.Array();array.push(children);value.set('sys:children',array);return value;}
function document(title,whiteboard=false){
  const doc=new Y.Doc();const blocks=doc.getMap('blocks');
  const page=block('page','affine:page',['surface','note']);page.set('prop:title',new Y.Text(title));blocks.set('page',page);
  const note=block('note','affine:note',['paragraph']);note.set('prop:xywh','[0,0,448,200]');blocks.set('note',note);
  const paragraph=block('paragraph','affine:paragraph');paragraph.set('prop:text',new Y.Text('AFFiNE adapter persistence 中文验证'));paragraph.set('prop:type','text');blocks.set('paragraph',paragraph);
  const surface=block('surface','affine:surface');const elements=new Y.Map();
  if(whiteboard){const shape=new Y.Map(Object.entries({id:'shape',type:'shape',shapeType:'rect',xywh:'[0,0,120,80]',index:'a0',rotate:0,filled:true}));elements.set('shape',shape);}
  surface.set('prop:elements',elements);
  blocks.set('surface',surface);return doc;
}
async function graphql(query,variables){
  const res=await fetch(base+'/graphql',{method:'POST',headers:{...headers,'Content-Type':'application/json','Apollo-Require-Preflight':'true'},body:JSON.stringify({query,variables}),signal:AbortSignal.timeout(30000)});
  const result=await res.json();if(result.errors)throw Error(JSON.stringify(result.errors));return result.data;
}
async function main(){
  const socket=new Socket();await socket.open();
  let peer;
  try{
    let records=input.expected;
    if(!records){
      peer=new Socket();await peer.open();
      const ids={document:crypto.randomUUID(),whiteboard:crypto.randomUUID()};
      const root=new Y.Doc();root.getMap('meta').set('name','Adapter acceptance');
      const pages=root.getArray('pages');pages.push(Object.entries(ids).map(([kind,id])=>new Y.Map(Object.entries({id,title:kind==='document'?'中文文档验证':'白板验证',createDate:Date.now()}))));
      await socket.call('space:push-doc-update',{spaceType:'workspace',spaceId:input.workspace,docId:input.workspace,update:Buffer.from(Y.encodeStateAsUpdate(root)).toString('base64')});
      for(const [kind,id] of Object.entries(ids)){
        const doc=document(kind==='document'?'中文文档验证':'白板验证',kind==='whiteboard');
        await socket.call('space:push-doc-update',{spaceType:'workspace',spaceId:input.workspace,docId:id,update:Buffer.from(Y.encodeStateAsUpdate(doc)).toString('base64')});
      }
      await peer.poll();
      if(!peer.events.some(([event,payload])=>event==='space:broadcast-doc-updates'&&payload.docId===ids.document))throw Error('A second synchronization client did not receive the document update');
      const file=new Blob(['AFFiNE attachment 中文验证'],{type:'text/plain'}),form=new FormData();
      form.append('operations',JSON.stringify({query:'mutation($workspaceId:String!,$blob:Upload!){setBlob(workspaceId:$workspaceId,blob:$blob)}',variables:{workspaceId:input.workspace,blob:null}}));
      form.append('map',JSON.stringify({'0':['variables.blob']}));form.append('0',file,'adapter-test.txt');
      const response=await fetch(base+'/graphql',{method:'POST',headers:{...headers,'Apollo-Require-Preflight':'true'},body:form});const value=await response.json();
      if(value.errors)throw Error(JSON.stringify(value.errors));
      records={...ids,blob:value.data.setBlob};
    }
    const result={...records};
    for(const kind of ['document','whiteboard']){
      const loaded=await socket.call('space:load-doc',{spaceType:'workspace',spaceId:input.workspace,docId:records[kind]});
      const doc=new Y.Doc();Y.applyUpdate(doc,Buffer.from(loaded.missing,'base64'));
      const title=doc.getMap('blocks').get('page').get('prop:title').toString();
      if(title!==(kind==='document'?'中文文档验证':'白板验证'))throw Error('Document title did not survive synchronization');
      if(kind==='whiteboard'&&!doc.getMap('blocks').get('surface').get('prop:elements').has('shape'))throw Error('Whiteboard shape missing');
    }
    const blob=await fetch(base+'/api/workspaces/'+input.workspace+'/blobs/'+encodeURIComponent(records.blob),{headers});
    if(!blob.ok||await blob.text()!=='AFFiNE attachment 中文验证')throw Error('Uploaded attachment differs');
    console.log(JSON.stringify(result));
  }finally{await socket.close();if(peer)await peer.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
