// Experimental ABI for original BO1Z packet bytes, not an independent simulation.
import { observeZombies } from './observer.js';
export function installBridge(module) {
  const slots=32, stride=65568, ringBytes=slots*stride, bytes=64+3*ringBytes;
  const pointer=module._malloc(bytes+4096);
  if(!pointer) throw new Error('Cannot allocate experimental packet bridge');
  const memory=module.HEAPF32.buffer, u8=new Uint8Array(memory), u32=new Uint32Array(memory);
  u8.fill(0,pointer,pointer+bytes+4096);
  Atomics.store(u32,184721744/4,pointer);
  const record={build:'bo1z-lan-lobby-v2',pointer,sent:0,received:0,dropped:0,errors:[],events:[]};
  let stopped=false;
  const event=(value)=>{record.events.push({ms:performance.now(),...value});if(record.events.length>256)record.events.shift()};
  function address(ip,port=3074) {
    if(typeof ip!=='string' || !/^\d{1,3}(\.\d{1,3}){3}$/.test(ip) || ip.split('.').some(n=>Number(n)>255) || ip.split('.').map(Number).join('.')!==ip)throw Error('Invalid native peer identity');
    if(!Number.isInteger(port)||port<1||port>65535)throw Error('Invalid native peer port');
    const b=new Uint8Array(16), view=new DataView(b.buffer);
    view.setUint32(0,4,true);b.set(ip.split('.').map(Number),4);view.setUint16(8,port,false);return b;
  }
  function receive(packet) {
    if(stopped)return false;
    if(!packet || ![0,1].includes(packet.sock))throw Error('Invalid native packet socket');
    const self=globalThis.__coopConfig;
    if(packet.to!==undefined && packet.to!==self?.ip)throw Error('Native packet destination differs from membership');
    if(packet.toPort!==undefined && packet.toPort!==(self?.port??3074))throw Error('Native packet destination port differs from membership');
    const source=address(packet.from,packet.fromPort??3074);
    const sock=packet.sock===0?1:0, head=pointer+24+sock*12;
    const read=Atomics.load(u32,(head+4)/4), write=Atomics.load(u32,head/4);
    let data;
    if(packet.data instanceof ArrayBuffer)data=new Uint8Array(packet.data);
    else if(ArrayBuffer.isView(packet.data))data=new Uint8Array(packet.data.buffer,packet.data.byteOffset,packet.data.byteLength);
    else if(Array.isArray(packet.data)&&packet.data.every(n=>Number.isInteger(n)&&n>=0&&n<=255))data=Uint8Array.from(packet.data);
    else throw Error('Native packet payload is not bytes');
    if(data.length===0||data.length>65536 || ((write-read)>>>0)>=slots) {
      Atomics.add(u32,(head+8)/4,1);record.dropped++;return false;
    }
    const slot=pointer+64+(sock+1)*ringBytes+(write&31)*stride;
    u32[slot/4]=sock;u32[(slot+4)/4]=data.length;
    u8.set(source,slot+8);u8.set(data,slot+24);
    Atomics.store(u32,head/4,(write+1)>>>0);
    record.received++;event({kind:'receive',sock,from:packet.from,length:data.length,preview:Array.from(data.slice(0,100))});
    return true;
  }
  const timer=setInterval(()=>{
    let read=Atomics.load(u32,(pointer+12)/4), write=Atomics.load(u32,(pointer+8)/4);
    while(read!==write) {
      const slot=pointer+64+(read&31)*stride, length=u32[(slot+4)/4], sock=u32[slot/4];
      if(length>65536||length===0||![0,1].includes(sock)) {
        read=(read+1)>>>0;Atomics.store(u32,(pointer+12)/4,read);record.dropped++;continue;
      }
      const to=Array.from(u8.slice(slot+12,slot+16)).join('.');
      const toPort=(u8[slot+16]<<8)|u8[slot+17];
      const data=u8.slice(slot+24,slot+24+length);
      const packet={sock,to,toPort,data,from:globalThis.__coopConfig?.ip,fromPort:globalThis.__coopConfig?.port??3074};
      read=(read+1)>>>0;Atomics.store(u32,(pointer+12)/4,read);
      record.sent++;event({kind:'send',sock,to,length,preview:Array.from(data.slice(0,100))});
      Promise.resolve(globalThis.__coopSend?.(packet)).catch(e=>{record.errors.push(String(e));if(record.errors.length>64)record.errors.shift()});
    }
  },2);
  return {
    record,receive,
    command(text) {
      const data=new TextEncoder().encode(text+'\n\0');
      if(data.length>4096 || Atomics.load(u32,(pointer+48)/4))throw Error('Command queue busy or too long');
      u8.set(data,pointer+bytes);Atomics.store(u32,(pointer+48)/4,1);
    },
    snapshot() {
      const native=Array.from(u32.slice(pointer/4,pointer/4+16));
      const gameLimit=u32[87567236/4], clients=u32[142360860/4];
      const f32=new Float32Array(memory),gameClients=u32[87567168/4];
      const connection=u32[43783020/4];
      const cstring=(p)=>{if(!p||p>=u8.length)return null;let e=p;while(e<p+256&&e<u8.length&&u8[e])e++;return new TextDecoder().decode(u8.slice(p,e))};
      const modeDvars=[134904692,134904744,134904752,134904784,134904896,134904904,134861220,142360544,134904788,100067188,13219624].map(global=>{const p=u32[global/4];return{global,pointer:p,name:p?cstring(u32[p/4]):null,current:p?u32[(p+24)/4]:null}});
      const replicated=u32[12123212/4];
      const netfieldLists=[1175536,1175548,1175560,1175572,1432752+6*12,1432752+17*12,1432752+19*12].map(p=>({pointer:p,descriptor:Array.from(u32.slice(p/4,p/4+3))}));
      const cg=u32[12717552/4],cl=u32[13423408/4];
      const frameState={parityAtomic:Atomics.load(u32,149863548/4),nativeLevelTime:u32[87569036/4],cgPointer:cg,cgTime:cg?u32[(cg+263224)/4]:null,cgRenderParameter:cg?u32[(cg+12)/4]:null,cgRenderScreen:cg?u32[(cg+28)/4]:null,cgSkipDraw:cg?u8[cg+386256]:null,serverLoadingMap:u8[43783024],cgNextSnapFlags:cg&&u32[(cg+44)/4]?u32[u32[(cg+44)/4]/4]:null,cgSnap:cg?u32[(cg+40)/4]:null,cgNextSnap:cg?u32[(cg+44)/4]:null,clPointer:cl,snapshotTime:cl?u32[(cl+16)/4]:null,clientServerTime:cl?u32[(cl+9960)/4]:null,oldServerTime:cl?u32[(cl+9964)/4]:null,timeDelta:cl?u32[(cl+9972)/4]:null,currentSnapshotNum:cl?u32[(cl+24)/4]:null,cmdNumber:cl?u32[(cl+279076)/4]:null};
      return {...record,native,gameLimit,modeDvars,netfieldLists,frameState,zombies:observeZombies(module),actorLimit:u32[1316988/4],entityBits:u32[1316976/4],demoState:u32[62386308/4],netfieldEtype:Array.from(u32.slice(1395984/4,1395984/4+7)),serverTime:u32[142360844/4],bandwidthCounter:u32[143240240/4],serverClientPointer:clients,serverStates:clients?Array.from({length:4},(_,i)=>u32[(clients+i*544120)/4]):[],serverPeers:clients?Array.from({length:4},(_,i)=>{const c=clients+i*544120;return{state:u32[c/4],qport:u32[(c+48)/4],address:Array.from(u8.slice(c+32,c+48)),entity:u32[(c+21868)/4],nextSnapshot:u32[(c+22376)/4],lastSnapshot:u32[(c+22380)/4],unsentFragments:u32[(c+68)/4],unsentLength:u32[(c+76)/4],reliableFragments:u32[(c+88)/4],sendCounts:Array.from(u8.slice(c+92,c+100)),acks:Array.from(u32.slice((c+220)/4,(c+236)/4)),lowestSendCount:u32[(c+236)/4],rate:u32[(c+340216)/4]}}):[],gameConnected:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+9920)/4]):[],playerOrigins:gameClients?Array.from({length:4},(_,i)=>Array.from(f32.slice((gameClients+i*10720+36)/4,(gameClients+i*10720+48)/4))):[],playerVehicleEntities:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+10248)/4]):[],playerPmTypes:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+4)/4]):[],playerCommandTimes:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720)/4]):[],playerViewAngles:gameClients?Array.from({length:4},(_,i)=>Array.from(f32.slice((gameClients+i*10720+384)/4,(gameClients+i*10720+396)/4))):[],playerShotCounts:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+352)/4]):[],playerNeedsRevive:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+10256)/4]):[],replicatedNeedsRevive:cg?Array.from({length:4},(_,i)=>u32[(cg+389016+i*1480+64)/4]):[],playerHealth:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+452)/4]):[],nativeScores:gameClients?Array.from({length:4},(_,i)=>u32[(gameClients+i*10720+10276)/4]):[],replicatedPlayers:replicated?Array.from({length:4},(_,i)=>{const e=replicated+i*808;return{valid:Boolean(u32[(e+804)/4]&2),origin:Array.from(f32.slice((e+48)/4,(e+60)/4))}}):[],deferred:Array.from(u8.slice(107308304,107308308)),localConnectionState:u32[13391960/4],assignedPlayer:connection?u32[(connection+4)/4]:null};
    },
    stop(){stopped=true;clearInterval(timer)}
  };
}
