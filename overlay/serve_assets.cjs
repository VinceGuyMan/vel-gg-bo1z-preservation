'use strict';
// Loopback allowlist replay only. Native engine and packets are untouched.
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {pipeline,Transform}=require('node:stream');
const BUILD='bo1z-shipping-preview-v1';
const common={'Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp','Cross-Origin-Resource-Policy':'same-origin','Cache-Control':'no-store'};
function contained(file,root){const rel=path.relative(root,file);return rel==='' || !path.isAbsolute(rel) && rel!=='..' && !rel.startsWith('..'+path.sep);}
function loadManifest(filename){
 const raw=fs.readFileSync(filename);if(raw.length>16*1024*1024)throw Error('manifest_size');
 const m=JSON.parse(raw);if(m.schemaVersion!==1 || m.build!==BUILD || typeof m.launchId!=='string' || !/^[A-Za-z0-9_-]{24,128}$/.test(m.launchId) || !Array.isArray(m.roots)||m.roots.length!==3)throw Error('manifest_schema');
 const roots=m.roots.map(p=>fs.realpathSync(p));let count=0;
 function checkEntry(e){
  if(!e || typeof e.path!=='string' || !path.isAbsolute(e.path) || !Number.isSafeInteger(e.bytes)||e.bytes<0 || !/^[a-f0-9]{64}$/.test(e.sha256) || typeof e.mime!=='string'||/[\r\n]/.test(e.mime)||!['','br','gzip'].includes(e.encoding))throw Error('entry_schema');
  const real=fs.realpathSync(e.path);if(real!==path.resolve(e.path)||!roots.some(r=>contained(real,r)))throw Error('entry_outside');
  const stat=fs.statSync(real);if(!stat.isFile()||stat.size!==e.bytes)throw Error('entry_size');
  e.path=real;if(++count>20000)throw Error('entry_count');
 }
 function table(t){if(!t||typeof t!=='object'||Array.isArray(t))throw Error('route_schema');for(const [route,e]of Object.entries(t)){if(!safePath(route))throw Error('route_path');checkEntry(e);}}
 table(m.files);table(m.overlays);table(m.coopPages);
 if(!m.parts||typeof m.parts!=='object'||Array.isArray(m.parts))throw Error('parts_schema');
 for(const [route,items]of Object.entries(m.parts)){if(!safePath(route)||!items||typeof items!=='object'||Array.isArray(items))throw Error('parts_route');for(const [part,e]of Object.entries(items)){if(!/^\d+$/.test(part))throw Error('parts_number');checkEntry(e);}}
 return m;
}
function safePath(p){return typeof p==='string'&&p.startsWith('/')&&!p.startsWith('//')&&!/[\\\x00-\x1f\x7f]/.test(p)&&!p.split('/').some(s=>s==='.'||s==='..');}
function target(raw){
 if(typeof raw!=='string'||raw.length>8192||!raw.startsWith('/')||raw.includes('#'))return null;
 const q=raw.indexOf('?'),rawPath=q<0?raw:raw.slice(0,q),query=q<0?'':raw.slice(q+1);
 let pathname;try{pathname=decodeURIComponent(rawPath);}catch{return null;}
 if(!safePath(pathname))return null;return {pathname,query,params:new URLSearchParams(query)};
}
function resolve(m,t){
 const p=t.pathname,coop=t.params.getAll('coop').filter(v=>v!==''),coopPath=p.replace(/\/+$/,'');
 if(coop.length===1&&coop[0]==='1'&&m.coopPages[coopPath])return {entry:m.coopPages[coopPath],ranges:false};
 if(m.overlays[p])return {entry:m.overlays[p],ranges:false};
 const part=t.params.getAll('part').filter(v=>v!=='');
 if(part.length){const k=part[0];return /^\d+$/.test(k||'')&&m.parts[p]?.[k]?{entry:m.parts[p][k],ranges:true}:null;}
 const e=m.files[p]||(p.endsWith('/')?m.files[p.slice(0,-1)]:null);return e?{entry:e,ranges:true}:null;
}
function range(size,encoding,allowed,value){
 let start=0,end=size-1,status=200;const match=typeof value==='string'?/^bytes=(\d*)-(\d*)$/.exec(value):null;
 if(match&&allowed&&!encoding){if(match[1]){start=Number(match[1]);if(match[2])end=Math.min(end,Number(match[2]));}else if(match[2])start=Math.max(0,size-Number(match[2]));
  if(start>end||start>=size)return null;status=206;}
 return {start,end,status,length:Math.max(0,end-start+1)};
}
function createHandler(m){return function(req,res){
 res.on('error',()=>{});
 function simple(code,body='',extra={}){const bytes=Buffer.from(body);res.writeHead(code,{...common,...extra,...(code===204?{}:{'Content-Type':'text/plain; charset=utf-8','Content-Length':bytes.length})});res.end(req.method==='HEAD'||code===204?undefined:bytes);}
 const t=target(req.url);if(!t){req.resume();simple(404,'Resource was not captured');return;}
 if(!['GET','HEAD'].includes(req.method)){req.resume();simple(req.method==='POST'&&t.pathname==='/bo1z/telemetry'?204:405);return;}
 if(t.pathname==='/bo1z/telemetry'){simple(204);return;}
 if(t.pathname==='/'){simple(302,'',{'Location':'/bo1z/'});return;}
 if(t.pathname==='/bo1z-coop'){simple(302,'',{'Location':'/bo1z-coop/'+(t.query?'?'+t.query:'')});return;}
 if(t.pathname==='/bo1z/coop/'){simple(302,'',{'Location':'/bo1z/five?coop=1&renderer=webgl2'});return;}
 const found=resolve(m,t);if(!found){simple(404,'Resource was not captured');return;}
 const e=found.entry,r=range(e.bytes,e.encoding,found.ranges,req.headers.range);if(!r){simple(416,'Requested range is unavailable',{'Content-Range':'bytes */'+e.bytes});return;}
 const headers={...common,'Content-Type':e.mime,'Content-Length':r.length,...(found.ranges?{'Accept-Ranges':'bytes'}:{})};
 if(e.encoding)headers['Content-Encoding']=e.encoding;
 if(r.status===206)headers['Content-Range']=`bytes ${r.start}-${r.end}/${e.bytes}`;
 if(req.method==='HEAD'||r.length===0){res.writeHead(r.status,headers);res.end();return;}
 const stream=fs.createReadStream(e.path,{start:r.start,end:r.end,highWaterMark:65536});
 stream.once('open',()=>{if(res.destroyed){stream.destroy();return;}res.writeHead(r.status,headers);let sent=0;const exact=new Transform({transform(chunk,encoding,next){sent+=chunk.length;if(sent>r.length){next(Error('representation_length'));return;}next(null,chunk);},flush(next){next(sent===r.length?undefined:Error('representation_truncated'));}});pipeline(stream,exact,res,error=>{if(error&&!res.destroyed)res.destroy();});});
 stream.once('error',()=>{if(!res.headersSent&&!res.destroyed)simple(500,'Captured resource could not be read');else if(!res.destroyed)res.destroy();});
 res.once('close',()=>{if(!stream.destroyed)stream.destroy();});
 };}
function main(argv){
 if(argv.length!==4||argv[0]!=='--manifest'||argv[2]!=='--port'||!/^\d+$/.test(argv[3]))throw Error('arguments');
 const port=Number(argv[3]);if(port<1||port>65535)throw Error('port');const m=loadManifest(argv[1]);
 const server=http.createServer({maxHeaderSize:16384},createHandler(m));server.requestTimeout=30000;server.headersTimeout=30000;
 const sockets=new Set();server.on('connection',s=>{sockets.add(s);s.once('close',()=>sockets.delete(s));s.on('error',()=>{});});
 server.on('clientError',(error,s)=>s.destroy());server.on('error',()=>{console.error('Asset server failed');process.exitCode=1;shutdown(1);});
 let stopping=false;
 function shutdown(code=0){if(stopping)return;stopping=true;server.close(()=>{process.exitCode=code;});for(const s of sockets)s.destroy();setTimeout(()=>process.exit(code),2000).unref();}
 for(const sig of ['SIGINT','SIGTERM','SIGBREAK'])process.on(sig,()=>shutdown(0));
 server.listen(port,'127.0.0.1',()=>console.log(JSON.stringify({service:'bo1z-coop-assets',build:BUILD,port,ready:true})));
}
module.exports={loadManifest,target,resolve,range,createHandler,main};
if(require.main===module){try{main(process.argv.slice(2));}catch{console.error('Asset server initialization failed');process.exitCode=1;}}
