// Read-only admission for the preserved BO1 Zombies WASM ABI, proof8.
// No native commands, gameplay writes, packet injection, or timeout extension.
// Poll each established peer during healthy transport, at least every250ms.
// The first observation is inactive. A second fresh observation must advance
// both relevant native clocks before ACTIVE can be admitted.
export const NATIVE_ADMISSION_ANCHORS = Object.freeze({
  clientTimeout: 'Original BrowserFrame11391 6eed55..6eed94',
  serverTimeout: 'Original SV_ServerThread8447 5f8743..5f888d',
  hostEpisode: 'SV_DirectConnect3844 challenge+20784 25f7f0; lastConnectTime+22372 25f938',
  guestEpisode: 'CL_CheckForResend6557 connectTime+32 4fe05b; CL_DispatchConnectionlessPacket4362 challenge+296 2c1722',
  guestChannel: '4362 2c15b1..2c15d2 Netchan_Setup at connection+649732;5812 resets out+0/in+12',
  dvarABI: 'Dvar_SetBoolFromSource344 type+16 0148d9; current+24',
});

const OFF = Object.freeze({active:false, stamp:'', budgetMs:0});
const MIN_OBSERVATION_MS=100, MAX_OBSERVATION_AGE_MS=1000, MAX_CLOCK_STALL_MS=750;
const SAFETY_MS=2000, MAX_BUDGET_MS=5000;
let readerInstances=0;
const now=()=>globalThis.performance.now();
const privateIdentity=value=>{
  if(!value||typeof value.ip!=='string'||value.port!==3074)return null;
  const a=value.ip.split('.').map(Number);
  if(a.length!==4||a.some(v=>!Number.isInteger(v)||v<0||v>255)||a.join('.')!==value.ip)return null;
  if(!(a[0]===10||a[0]===172&&a[1]>=16&&a[1]<=31||a[0]===192&&a[1]===168))return null;
  return value.ip;
};
const memberId=value=>{
  if(!value||typeof value.id!=='string'||!value.id.length||value.id.length>128)return null;
  const epoch=String(value.epoch??'');
  if(!epoch.length||epoch.length>128)return null;
  return value.id+'@'+epoch;
};

export function createNativeResumeAdmission(module,getConfig) {
  const instance=++readerInstances,records=new Map(); let generation=0;
  function observe(peer,member) {
    const config=getConfig?.(),local=member??config?.member;
    const localId=memberId(local),peerId=memberId(peer);
    const role=config?.role==='client'?'guest':config?.role;
    const ownIP=privateIdentity(local?.identity),remoteIP=privateIdentity(peer?.identity);
    if(!['host','guest'].includes(role)||local?.role!==role||peer?.role!==(role==='host'?'guest':'host')||
      !localId||!peerId||localId===peerId||!ownIP||!remoteIP||ownIP===remoteIP||
      config?.ip!==ownIP||config?.port!==3074)return null;
    const buffer=module?.HEAPU8?.buffer??module?.HEAPF32?.buffer;
    if(!buffer||buffer.byteLength<143240244)return null;
    const d=new DataView(buffer),range=(p,n)=>Number.isSafeInteger(p)&&p>0&&p<=d.byteLength-n;
    const i=p=>{if(!range(p,4))throw Error('ABI range');return d.getInt32(p,true);};
    const u=p=>{if(!range(p,4))throw Error('ABI range');return d.getUint32(p,true);};
    const ptr=(global,size)=>{const p=u(global);if(p%4||!range(p,size))throw Error('ABI pointer');return p;};
    function name(p){if(!range(p,1))throw Error('Dvar name');let s='';for(let j=0;j<128;j++){if(!range(p+j,1))throw Error('Dvar name');const b=d.getUint8(p+j);if(!b)return s;s+=String.fromCharCode(b);}throw Error('Dvar name');}
    function dv(global,expected,type){const p=ptr(global,28);if(name(u(p))!==expected||i(p+16)!==type)throw Error('Dvar ABI');const v=type===1?d.getFloat32(p+24,true):type===0?d.getUint8(p+24):i(p+24);if(!Number.isFinite(v))throw Error('Dvar value');return v;}
    function adr(p){if(!range(p,16)||i(p)!==4)throw Error('Native NA_IP');const ip=[4,5,6,7].map(v=>d.getUint8(p+v)).join('.');const port=d.getUint16(p+8,false);if(ip!==remoteIP||port!==3074)throw Error('Native route');return ip+':'+port;}
    function qport(p){const v=i(p),short=v&65535;if(!short||v!==short&&v!==(short<<16>>16))throw Error('Native qport');return short;}
    if(u(62386308)!==0||dv(134904784,'zombiemode',0)!==1||dv(134904788,'kisak_zombies',0)!==1)return null;
    const clPause=dv(134904896,'cl_paused',5),svPause=dv(134904892,'sv_paused',5);
    if(![0,1].includes(clPause)||![0,1].includes(svPause)||clPause&&svPause)return null;
    // Even the host requires the current browser engine to remain ACTIVE.
    if(i(13391960)!==10)return null;
    const realtime=i(13429904);
    if(realtime<=0)return null;
    let pointer,slot,route,q,challenge,connectTime,outgoing,incoming,lastPacket,timeout,clock2,gamePointer;
    if(role==='host') {
      if(dv(134904904,'sv_running',0)!==1)return null;
      timeout=dv(142360560,'sv_timeout',5)*1000;
      const count=dv(142360544,'sv_maxclients',5);
      if(!Number.isInteger(count)||count<2||count>4)return null;
      const clients=ptr(142360860,count*544120),gameClients=ptr(87567168,count*10720);
      const candidates=[];
      for(let s=1;s<count;s++) {const p=clients+s*544120;try {if(adr(p+32))candidates.push({s,p});}catch{/* another native slot */}}
      if(candidates.length!==1)return null;
      ({s:slot,p:pointer}=candidates[0]);gamePointer=gameClients+slot*10720;
      if(i(pointer)!==5||i(gamePointer+9920)!==2||i(pointer+22384)!==0||i(pointer+407824)!==0||i(pointer+407828)!==0)return null;
      route=adr(pointer+32);q=qport(pointer+48);challenge=i(pointer+20784);connectTime=i(pointer+22372);
      outgoing=i(pointer+16);incoming=i(pointer+28);lastPacket=i(pointer+22368);clock2=i(142360844);
    } else {
      timeout=Math.fround(dv(13423152,'cl_timeout',1)*1000);
      pointer=ptr(43783020,649780);const active=ptr(13423408,8),cg=ptr(12717552,273136);
      slot=i(pointer+4);
      if(slot<1||slot>3||d.getUint8(cg+263244+304)!==slot||i(active+4)!==0||i(43783024)!==0)return null;
      route=adr(pointer+16);adr(pointer+649748);q=qport(pointer+649764);
      challenge=i(pointer+296);connectTime=i(pointer+32);outgoing=i(pointer+649732);incoming=i(pointer+649744);
      lastPacket=i(pointer+12);clock2=i(cg+263224);gamePointer=active;
    }
    const primary=role==='host'?clock2:realtime,elapsed=primary-lastPacket;
    if(!Number.isFinite(timeout)||timeout<=0||timeout>3600000||primary<=0||clock2<=0||lastPacket<=0||elapsed<0||
      connectTime<=0||challenge===0||outgoing<1||incoming<1)return null;
    const headroom=timeout-(role==='guest'?Math.fround(elapsed):elapsed);
    if(headroom<=SAFETY_MS)return null;
    // Worker-side native slots can change during a read. Recheck identity and
    // admission fields before accepting this observation; no lock/write needed.
    if(role==='host') {
      if(i(pointer)!==5||i(gamePointer+9920)!==2||i(pointer+20784)!==challenge||i(pointer+22372)!==connectTime||
        qport(pointer+48)!==q||adr(pointer+32)!==route)return null;
    } else if(i(13391960)!==10||u(43783020)!==pointer||i(pointer+4)!==slot||i(pointer+296)!==challenge||
      i(pointer+32)!==connectTime||qport(pointer+649764)!==q||adr(pointer+16)!==route)return null;
    const identity=JSON.stringify([role,localId,peerId,ownIP,route,pointer,gamePointer,slot,q,challenge,connectTime]);
    return {identity,wall:now(),realtime,clock2,outgoing,incoming,headroom,role,slot,q,challenge,connectTime};
  }
  const admission=(peer,member)=>{
    const key=memberId(peer);
    if(!key)return OFF;
    let sample;
    try{sample=observe(peer,member);}catch{return records.delete(key),OFF;}
    if(!sample){records.delete(key);return OFF;}
    let r=records.get(key);
    if(!r||r.latest.identity!==sample.identity||sample.wall-r.latest.wall>MAX_OBSERVATION_AGE_MS||
      sample.wall<r.latest.wall||sample.realtime<r.latest.realtime||sample.clock2<r.latest.clock2||
      sample.outgoing<r.latest.outgoing||sample.incoming<r.latest.incoming) {
      r={base:sample,latest:sample,proven:false,lastAdvance:sample.wall,generation:++generation};records.set(key,r);return OFF;
    }
    if(sample.realtime>r.latest.realtime&&sample.clock2>r.latest.clock2)r.lastAdvance=sample.wall;
    if(sample.wall-r.base.wall>=MIN_OBSERVATION_MS&&sample.realtime>r.base.realtime&&sample.clock2>r.base.clock2)r.proven=true;
    r.latest=sample;
    if(!r.proven||sample.wall-r.lastAdvance>MAX_CLOCK_STALL_MS)return OFF;
    const wallAge=Math.max(0,now()-sample.wall),budgetMs=Math.floor(Math.min(MAX_BUDGET_MS,sample.headroom-wallAge-SAFETY_MS));
    if(budgetMs<250)return OFF;
    return {active:true,stamp:['bo1z-native-v1',instance,r.generation,sample.role,sample.slot,sample.q,sample.challenge,sample.connectTime].join(':'),budgetMs};
  };
  admission.clear=()=>records.clear();
  return admission;
}
