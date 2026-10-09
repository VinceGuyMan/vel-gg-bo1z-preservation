import {validatePeerMetadata} from './peer-schema.js';
import {isRuntimeEvidence} from './runtime-attestation.js';
// Local, bounded observation only. This module never calls engine control APIs.
export const STATUS_SCHEMA_VERSION = 3;
export const LIMITS = Object.freeze({samples: 12, durationMs: 10000, intervalMs: 1000, reportBytes: 131072});
export const KNOWN_LAYOUT = Object.freeze({
  baseWasmSha256: '61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98',
  patchedWasmSha256: '29c436447d467e63ae05346bdb5ed53c5f79ce0ab5e7493148200797b7129628',
  bridgeSourceSha256:'a756498b3c351a771fd1e3c77b08eebe0c32da48e034d3278e3f4c7c5918ba98',
  observerSourceSha256: '4692475b3756ee37ae5ba2d2b90fcc39a7c2ab10448da47d41b5c86c4a93b116',
  bridgeBuild: 'bo1z-shipping-preview-v1'
});
const META_FIELDS = ['overlayBuildId', 'protocolVersion', 'bridgeAbiVersion', 'patchSchemaRevision', 'baseWasmSha256',
 'patchedWasmSha256', 'patchManifestSha256', 'shellManifestSha256', 'mapManifestSha256',
 'mapContentSha256', 'mapSlug', 'mode', 'maxPlayers'];
const SHA = /^[0-9a-f]{64}$/;
const PHASES = ['idle','connecting','preparing','joining','match','failed','left'];
const SCREENS = ['landing','download','loading','ready','playing','error'];
const enumValue = (v, list) => list.includes(v) ? v : null;
const uint = (v, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(v) && v >= 0 && v <= max ? v : null;
const bool = v => typeof v === 'boolean' ? v : null;
const count = (v, max) => Array.isArray(v) ? Math.min(v.length, max) : null;
const scalar = v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= 2147483648 ? v : null;
const xyz = v => Array.isArray(v) && v.length === 3 && v.every(n => scalar(n) !== null) ? [...v] : null;
const read = fn => {try {return typeof fn === 'function' ? fn() : null;} catch {return null;}};
const canonical = object => JSON.stringify(Object.fromEntries(Object.keys(object).sort().map(k => [k, object[k]])));
export async function sha256(text) {
 const bytes = new TextEncoder().encode(text);
 const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
 return Array.from(new Uint8Array(digest), v => v.toString(16).padStart(2, '0')).join('');
}
export function validateMetadata(value) {return validatePeerMetadata(value);}

export function runtimeVerified(metadata, evidence) {
 // This evidence must come from the loader's actual instantiated artifact/source
 // verification. Fetching matching metadata alone is deliberately insufficient.
 return Boolean(metadata && isRuntimeEvidence(evidence) && evidence.association === 'instantiated-artifact-and-observers'
  && ['baseWasmSha256','patchedWasmSha256','bridgeSourceSha256','observerSourceSha256']
   .every(key => evidence[key] === KNOWN_LAYOUT[key])
  && metadata.baseWasmSha256 === KNOWN_LAYOUT.baseWasmSha256
  && metadata.patchedWasmSha256 === KNOWN_LAYOUT.patchedWasmSha256);
}
function virtualSlot(identity) {
 if (!identity || identity.port !== 3074 || !/^10\.0\.0\.[1-4]$/.test(identity.ip)) return null;
 return Number(identity.ip.slice(-1)) - 1;
}
async function epochHash(value) {
 return typeof value === 'string' && /^[A-Za-z0-9_-]{16,64}$/.test(value) ? sha256(value) : null;
}
export function sanitizeNetworkPath(value) {
 const types=['host','srflx','prflx','relay'];
 const okay=value?.available===true&&types.includes(value.localCandidateType)&&types.includes(value.remoteCandidateType)
  &&value.route===(value.localCandidateType==='relay'||value.remoteCandidateType==='relay'?'relay':'direct');
 return {available:okay,route:okay?value.route:'unavailable',
  localCandidateType:okay?value.localCandidateType:null,remoteCandidateType:okay?value.remoteCandidateType:null,
  protocol:okay?enumValue(value.protocol,['udp','tcp']):null,relayProtocol:okay?enumValue(value.relayProtocol,['udp','tcp','tls']):null,
  roundTripTimeMs:okay&&Number.isFinite(value.roundTripTimeMs)&&value.roundTripTimeMs>=0&&value.roundTripTimeMs<=60000?value.roundTripTimeMs:null,
  bytesSent:okay?uint(value.bytesSent,Number.MAX_SAFE_INTEGER):null,bytesReceived:okay?uint(value.bytesReceived,Number.MAX_SAFE_INTEGER):null,
  sampledAtMs:okay&&Number.isFinite(value.sampledAtMs)&&value.sampledAtMs>=0?value.sampledAtMs:null};
}
function connection(edge) {
 const states = ['new','connecting','connected','disconnected','failed','closed'];
 const ice = ['new','checking','connected','completed','disconnected','failed','closed'];
 const signaling = ['stable','have-local-offer','have-remote-offer','have-local-pranswer','have-remote-pranswer','closed'];
 const result = {peerSlot: virtualSlot(edge?.remote), role: enumValue(edge?.role, ['host','guest']),
  ready: bool(edge?.ready), verified: bool(edge?.verified), closed: bool(edge?.closed),
  connectionState: enumValue(edge?.connectionState, states), iceConnectionState: enumValue(edge?.iceConnectionState, ice),
  signalingState: enumValue(edge?.signalingState, signaling),networkPath:sanitizeNetworkPath(edge?.networkPath), counters: {}};
 for (const field of ['sentDatagrams','receivedDatagrams','sentBytes','receivedBytes','bufferedAmount',
  'queuedDatagrams','queuedBytes','assemblies','assemblyBytes','droppedOutgoing','droppedIncoming',
  'expiredAssemblies','malformedFrames','sendErrors','callbackErrors']) result.counters[field] = uint(edge?.[field]);
 return result;
}
function frame(value) {
 const result = {};
 for (const key of ['cgTime','snapshotTime','clientServerTime','oldServerTime','timeDelta','currentSnapshotNum','cmdNumber'])
  result[key] = uint(value?.[key], 0xffffffff);
 result.serverLoadingMap = uint(value?.serverLoadingMap, 1);
 return result;
}
function replicas(value) {
 if (!Array.isArray(value)) return null;
 return value.slice(0,4).map((v, slot) => ({slot, valid: bool(v?.valid), origin: xyz(v?.origin)}));
}
function authority(value) {
 if (!Array.isArray(value?.serverStates)) return {available:false, reason:'authority_unavailable', players:[]};
 return {available:true, reason:null, serverTime:uint(value.serverTime,0xffffffff), players:Array.from({length:4},(_,slot)=>({slot,
  clientState:uint(value.serverStates[slot],16), gameConnected:uint(value.gameConnected?.[slot],4),
  origin:xyz(value.playerOrigins?.[slot]), health:scalar(value.playerHealth?.[slot]), points:scalar(value.nativeScores?.[slot]),
  movementType:uint(value.playerPmTypes?.[slot],32), commandTime:uint(value.playerCommandTimes?.[slot],0xffffffff)}))};
}
export function readPrediction(module, evidence, metadata) {
 if (!runtimeVerified(metadata,evidence)||!isRuntimeEvidence(evidence,module)) return {available:false, reason:'layout_unverified'};
 const buffer=module?.HEAPU8?.buffer??module?.HEAPF32?.buffer;
 if (!buffer || typeof buffer.byteLength !== 'number') return {available:false,reason:'heap_unavailable'};
 try {
  const d=new DataView(buffer), within=(p,n)=>Number.isSafeInteger(p)&&p>0&&p<=d.byteLength-n;
  const u=p=>{if(!within(p,4)||p%4)throw Error();return d.getUint32(p,true);};
  const cg=u(12717552), p=cg+263244;
  if(!cg||!within(p,9892))return {available:false,reason:'prediction_unavailable'};
  const clientNum=d.getUint8(p+304);
  if(clientNum>3)return {available:false,reason:'prediction_invalid'};
  const origin=[36,40,44].map(offset=>d.getFloat32(p+offset,true));
  const angles=[384,388,392].map(offset=>d.getFloat32(p+offset,true));
  if(!xyz(origin)||!xyz(angles))return {available:false,reason:'prediction_invalid'};
  const ammo=(offset)=>Array.from({length:15},(_,i)=>({index:d.getInt32(p+offset+i*8,true),count:d.getInt32(p+offset+i*8+4,true)}))
   .filter(v=>v.index>=0&&v.index<65536&&v.count>=0&&v.count<=65535);
  return {available:true,reason:null,slot:clientNum,commandTime:u(p),movementType:u(p+4),origin,viewAngles:angles,
   health:d.getInt32(p+452,true),weapon:d.getUint16(p+324,true),ammoInClip:ammo(952),ammoReserve:ammo(832)};
 }catch{return {available:false,reason:'prediction_unavailable'};}
}
function environment(value) {
 const result = {platform:enumValue(value?.platform,['macOS','Windows','Linux','unknown']),
  browser:enumValue(value?.browser,['Chrome','Edge','Brave','Chromium','unknown']),
  browserVersion:typeof value?.browserVersion==='string'&&/^\d{1,3}(?:\.\d{1,6}){0,3}$/.test(value.browserVersion)?value.browserVersion:null,
  secureContext:bool(value?.secureContext), isolated:bool(value?.isolated), pointerLocked:bool(value?.pointerLocked),
  screen:enumValue(value?.screen,SCREENS),visible:bool(value?.visible),errorPresent:bool(value?.errorPresent),
  viewport:{width:uint(value?.viewport?.width,32768),height:uint(value?.viewport?.height,32768)}};
 return result;
}
const safePrediction = p => {
 if(!p?.available)return {available:false,reason:enumValue(p?.reason,['layout_unverified','heap_unavailable','prediction_unavailable','prediction_invalid'])??'prediction_unavailable'};
 const result={available:true,reason:null,slot:uint(p.slot,3),commandTime:uint(p.commandTime,0xffffffff),movementType:uint(p.movementType,32),
  origin:xyz(p.origin),viewAngles:xyz(p.viewAngles),health:scalar(p.health),weapon:uint(p.weapon,65535)};
 for(const k of ['ammoInClip','ammoReserve'])result[k]=Array.isArray(p[k])?p[k].slice(0,15).map(v=>({index:uint(v?.index,65535),count:uint(v?.count,65535)})):null;
 return result;
};
export function createStatusCollector({metadata, verifiedRuntime=null, readLobby, readBridge, readPrediction:predictionReader,
 readEnvironment, utcNow=()=>new Date().toISOString(), monotonicNow=()=>performance.now(), wait=ms=>new Promise(r=>setTimeout(r,ms))}={}) {
 const meta=validateMetadata(metadata), admitted=runtimeVerified(meta,verifiedRuntime);
 let sequence=0;
 async function sample() {
  const lobby=read(readLobby), env=read(readEnvironment), role=enumValue(lobby?.role,['host','guest']);
  const bridge=admitted&&role?read(readBridge):null;
  const nativeOkay=Boolean(admitted&&bridge?.build===KNOWN_LAYOUT.bridgeBuild);
  const members=Array.isArray(lobby?.members)?lobby.members.slice(0,4):[];
  const roster=[];
  for(const member of members) roster.push({slot:virtualSlot(member?.identity),role:enumValue(member?.role,['host','guest']),
   ready:bool(member?.engineReady),membershipEpochSha256:await epochHash(member?.epoch)});
  const host=members.find(member=>member?.role==='host');
  const native={available:nativeOkay,reason:nativeOkay?null:admitted?'native_snapshot_unavailable':'layout_unverified',
   localConnectionState:nativeOkay?uint(bridge.localConnectionState,16):null,assignedSlot:nativeOkay?uint(bridge.assignedPlayer,3):null,
   frame:nativeOkay?frame(bridge.frameState):null,
   hostAuthority:nativeOkay&&role==='host'?authority(bridge):{available:false,reason:role==='guest'?'guest_warm_storage_excluded':'authority_unavailable',players:[]},
   replicatedPlayers:nativeOkay?replicas(bridge.replicatedPlayers):null,
   replicatedRevive:nativeOkay&&Array.isArray(bridge.replicatedNeedsRevive)?bridge.replicatedNeedsRevive.slice(0,4).map(n=>uint(n,0xffffffff)):null,
   prediction:nativeOkay?safePrediction(read(predictionReader)):{available:false,reason:'layout_unverified'}};
  const stamp=utcNow();
  const sample={index:++sequence,utc:typeof stamp==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(stamp)?stamp:null,
   monotonicMs:scalar(monotonicNow()),environment:environment(env),
   lobby:{available:Boolean(lobby),transport:enumValue(lobby?.transport,['webrtc','websocket-relay']),role,phase:enumValue(lobby?.phase,PHASES),roomEpochSha256:await epochHash(host?.epoch),
    startEpoch:uint(lobby?.startEpoch),slot:virtualSlot(lobby?.identity),prepared:bool(lobby?.prepared),ready:bool(lobby?.engineReady),
    started:bool(lobby?.started),restartIssued:bool(lobby?.restartIssued),stopped:bool(lobby?.stopped),errorCount:count(lobby?.errors,20),members:roster},
   connections:Array.isArray(lobby?.connections)?lobby.connections.slice(0,3).map(connection):[],native,
   packets:{available:nativeOkay,sent:nativeOkay?uint(bridge.sent):null,received:nativeOkay?uint(bridge.received):null,
    dropped:nativeOkay?uint(bridge.dropped):null,errorCount:nativeOkay?count(bridge.errors,64):null}};
  return sample;
 }
 async function report({testLabel='lan-test',durationMs=0,signal}={}) {
  if(typeof testLabel!=='string'||! /^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(testLabel))throw Error('invalid_test_label');
  if(!Number.isInteger(durationMs)||durationMs<0||durationMs>LIMITS.durationMs)throw Error('invalid_duration');
  const samples=[],start=monotonicNow();let stopped='completed',scheduledMs=0;
  if(!Number.isFinite(start))throw Error('clock_unavailable');
  do {
   if(signal?.aborted){stopped='aborted';break;}
   const s=await sample();samples.push(s);
   if(s.environment.visible===false||s.lobby.stopped===true){stopped='inactive';break;}
   if(samples.length>=LIMITS.samples||durationMs===0||Math.max(monotonicNow()-start,scheduledMs)>=durationMs
    ||scheduledMs+LIMITS.intervalMs>durationMs)break;
   await wait(LIMITS.intervalMs);scheduledMs+=LIMITS.intervalMs;
  }while(samples.length<LIMITS.samples);
  const result={schemaVersion:STATUS_SCHEMA_VERSION,testLabel,build:{metadata:{...meta},compatibilitySha256:await sha256(canonical(meta)),
   nativeLayoutVerified:admitted,verification:admitted?'loader_attested_instantiated_artifact_and_observers':'metadata_only_native_unavailable'},
   sampling:{intervalMs:LIMITS.intervalMs,requestedDurationMs:durationMs,stopped,maxSamples:LIMITS.samples},samples,
   limitations:['Asynchronous local observations; no one-way latency or causal desync inference.',
    'Guest warm local server/script/actor state excluded from authority.',
    'Packet counters are cumulative and are not measured network loss/latency.',
    'Status export does not establish movement, damage, kill, round or reconnect admission.']};
  serializeReport(result);return result;
 }
 return Object.freeze({sample,report});
}
export function serializeReport(report) {
 validateReport(report);
 const plain=structuredClone(report);validateReport(plain);
 const json=JSON.stringify(plain,null,2);
 if(new TextEncoder().encode(json).byteLength>LIMITS.reportBytes)throw Error('report_size_exceeded');
 return json;
}
export function browserEnvironment(windowObject=globalThis) {
 const nav=windowObject.navigator??{},ua=String(nav.userAgent??'');
 const version=ua.match(/(?:Edg|Chrome|Chromium)\/(\d+(?:\.\d+){0,3})/)?.[1]??null;
 return {platform:/Win/.test(nav.platform)?'Windows':/Mac/.test(nav.platform)?'macOS':/Linux/.test(nav.platform)?'Linux':'unknown',
  browser:/Edg\//.test(ua)?'Edge':/Chromium\//.test(ua)?'Chromium':/Chrome\//.test(ua)?'Chrome':'unknown',browserVersion:version,
  secureContext:windowObject.isSecureContext,isolated:windowObject.crossOriginIsolated,
  pointerLocked:Boolean(windowObject.document?.pointerLockElement),visible:windowObject.document?.visibilityState==='visible',
  screen:windowObject.document?.body?.dataset?.screen,errorPresent:Boolean(windowObject.document?.querySelector('#error-message')?.textContent),
  viewport:{width:windowObject.innerWidth,height:windowObject.innerHeight}};
}

// Strict allowlist validator protects the download boundary against accidental
// future export of entire native/RTC objects or arbitrary caller-added fields.
export function validateReport(report) {
 const fail=()=>{throw Error('status_schema_invalid');};
 const object=(v,keys)=>{if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).length!==keys.length||keys.some(k=>!Object.hasOwn(v,k)))fail();};
 const choice=(v,list)=>{if(v!==null&&!list.includes(v))fail();};
 const number=(v,max=Number.MAX_SAFE_INTEGER)=>{if(v!==null&&uint(v,max)===null)fail();};
 const logical=v=>{if(v!==null&&typeof v!=='boolean')fail();};
 const hash=v=>{if(v!==null&&(typeof v!=='string'||!SHA.test(v)))fail();};
 const vector=v=>{if(v!==null&&!xyz(v))fail();};
 const array=(v,max,fn)=>{if(!Array.isArray(v)||v.length>max)fail();for(const row of v)fn(row);};
 const numericScalar=v=>{if(v!==null&&scalar(v)===null)fail();};
 const prediction=v=>{
  if(v?.available===false){object(v,['available','reason']);choice(v.reason,['layout_unverified','heap_unavailable','prediction_unavailable','prediction_invalid']);return;}
  object(v,['available','reason','slot','commandTime','movementType','origin','viewAngles','health','weapon','ammoInClip','ammoReserve']);
  if(v.available!==true||v.reason!==null)fail();number(v.slot,3);number(v.commandTime,0xffffffff);number(v.movementType,32);
  vector(v.origin);vector(v.viewAngles);numericScalar(v.health);number(v.weapon,65535);
  for(const key of ['ammoInClip','ammoReserve'])if(v[key]!==null)array(v[key],15,row=>{object(row,['index','count']);number(row.index,65535);number(row.count,65535);});
 };
 object(report,['schemaVersion','testLabel','build','sampling','samples','limitations']);
 if(report.schemaVersion!==STATUS_SCHEMA_VERSION||typeof report.testLabel!=='string'||! /^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(report.testLabel))fail();
 object(report.build,['metadata','compatibilitySha256','nativeLayoutVerified','verification']);
 object(report.build.metadata,META_FIELDS);validateMetadata(report.build.metadata);hash(report.build.compatibilitySha256);if(typeof report.build.nativeLayoutVerified!=='boolean')fail();
 choice(report.build.verification,['loader_attested_instantiated_artifact_and_observers','metadata_only_native_unavailable']);
 if(report.build.verification!==(report.build.nativeLayoutVerified?'loader_attested_instantiated_artifact_and_observers':'metadata_only_native_unavailable'))fail();
 object(report.sampling,['intervalMs','requestedDurationMs','stopped','maxSamples']);
 if(report.sampling.intervalMs!==LIMITS.intervalMs||report.sampling.maxSamples!==LIMITS.samples)fail();
 number(report.sampling.requestedDurationMs,LIMITS.durationMs);choice(report.sampling.stopped,['completed','aborted','inactive']);
 array(report.samples,LIMITS.samples,s=>{
  object(s,['index','utc','monotonicMs','environment','lobby','connections','native','packets']);number(s.index);numericScalar(s.monotonicMs);
  if(s.utc!==null&&(typeof s.utc!=='string'||! /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(s.utc)))fail();
  const e=s.environment;object(e,['platform','browser','browserVersion','secureContext','isolated','pointerLocked','screen','visible','errorPresent','viewport']);
  choice(e.platform,['macOS','Windows','Linux','unknown']);choice(e.browser,['Chrome','Edge','Brave','Chromium','unknown']);
  if(e.browserVersion!==null&&(typeof e.browserVersion!=='string'||! /^\d{1,3}(?:\.\d{1,6}){0,3}$/.test(e.browserVersion)))fail();
  for(const key of ['secureContext','isolated','pointerLocked','visible','errorPresent'])logical(e[key]);choice(e.screen,SCREENS);
  object(e.viewport,['width','height']);number(e.viewport.width,32768);number(e.viewport.height,32768);
  const l=s.lobby;object(l,['available','transport','role','phase','roomEpochSha256','startEpoch','slot','prepared','ready','started','restartIssued','stopped','errorCount','members']);
  logical(l.available);choice(l.transport,['webrtc','websocket-relay']);choice(l.role,['host','guest']);choice(l.phase,PHASES);hash(l.roomEpochSha256);number(l.startEpoch);number(l.slot,3);number(l.errorCount,20);
  for(const key of ['prepared','ready','started','restartIssued','stopped'])logical(l[key]);
  array(l.members,4,m=>{object(m,['slot','role','ready','membershipEpochSha256']);number(m.slot,3);choice(m.role,['host','guest']);logical(m.ready);hash(m.membershipEpochSha256);});
  array(s.connections,3,c=>{
   object(c,['peerSlot','role','ready','verified','closed','connectionState','iceConnectionState','signalingState','networkPath','counters']);number(c.peerSlot,3);choice(c.role,['host','guest']);
   for(const key of ['ready','verified','closed'])logical(c[key]);
   choice(c.connectionState,['new','connecting','connected','disconnected','failed','closed']);choice(c.iceConnectionState,['new','checking','connected','completed','disconnected','failed','closed']);
   choice(c.signalingState,['stable','have-local-offer','have-remote-offer','have-local-pranswer','have-remote-pranswer','closed']);
   object(c.networkPath,['available','route','localCandidateType','remoteCandidateType','protocol','relayProtocol','roundTripTimeMs','bytesSent','bytesReceived','sampledAtMs']);
   if(canonical(c.networkPath)!==canonical(sanitizeNetworkPath(c.networkPath)))fail();
   const keys=['sentDatagrams','receivedDatagrams','sentBytes','receivedBytes','bufferedAmount','queuedDatagrams','queuedBytes','assemblies','assemblyBytes','droppedOutgoing','droppedIncoming','expiredAssemblies','malformedFrames','sendErrors','callbackErrors'];
   object(c.counters,keys);for(const key of keys)number(c.counters[key]);
  });
  const n=s.native;object(n,['available','reason','localConnectionState','assignedSlot','frame','hostAuthority','replicatedPlayers','replicatedRevive','prediction']);logical(n.available);choice(n.reason,['native_snapshot_unavailable','layout_unverified']);number(n.localConnectionState,16);number(n.assignedSlot,3);
  if(n.frame!==null){const keys=['cgTime','snapshotTime','clientServerTime','oldServerTime','timeDelta','currentSnapshotNum','cmdNumber','serverLoadingMap'];object(n.frame,keys);for(const key of keys)number(n.frame[key],key==='serverLoadingMap'?1:0xffffffff);}
  const a=n.hostAuthority;
  if(a?.available===false){object(a,['available','reason','players']);choice(a.reason,['guest_warm_storage_excluded','authority_unavailable']);if(!Array.isArray(a.players)||a.players.length)fail();}
  else {object(a,['available','reason','serverTime','players']);if(a.available!==true||a.reason!==null)fail();number(a.serverTime,0xffffffff);
   array(a.players,4,p=>{object(p,['slot','clientState','gameConnected','origin','health','points','movementType','commandTime']);number(p.slot,3);number(p.clientState,16);number(p.gameConnected,4);vector(p.origin);numericScalar(p.health);numericScalar(p.points);number(p.movementType,32);number(p.commandTime,0xffffffff);});}
  if(l.role==='guest'&&a.available!==false)fail();
  if(n.replicatedPlayers!==null)array(n.replicatedPlayers,4,p=>{object(p,['slot','valid','origin']);number(p.slot,3);logical(p.valid);vector(p.origin);});
  if(n.replicatedRevive!==null)array(n.replicatedRevive,4,p=>number(p,0xffffffff));prediction(n.prediction);
  object(s.packets,['available','sent','received','dropped','errorCount']);logical(s.packets.available);for(const key of ['sent','received','dropped'])number(s.packets[key]);number(s.packets.errorCount,64);
  if(!report.build.nativeLayoutVerified&&(n.available||s.packets.available||n.frame!==null||n.replicatedPlayers!==null||n.prediction.available))fail();
 });
 const allowed=['Asynchronous local observations; no one-way latency or causal desync inference.',
  'Guest warm local server/script/actor state excluded from authority.',
  'Packet counters are cumulative and are not measured network loss/latency.',
  'Status export does not establish movement, damage, kill, round or reconnect admission.'];
 array(report.limitations,4,value=>{if(!allowed.includes(value))fail();});
 return true;
}
