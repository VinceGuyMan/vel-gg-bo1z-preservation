// Pure inspection of already copied, host-authoritative native snapshots.
// No native commands, timing substitutions, or game state writes.
export function observeSettledStart(native, members, baseline, previous=null) {
  if (!native || !baseline || !Array.isArray(members) || members.length<2 || members.length>4) return null;
  if(!Number.isInteger(baseline.snapshotNum)||baseline.snapshotNum<0||!Number.isInteger(baseline.serverTime)||baseline.serverTime<=0)return null;
  const num=native.frameState?.currentSnapshotNum, time=native.serverTime;
  if (!Number.isInteger(num)||num<=0||!Number.isInteger(time)||time<=0||
      num===baseline.snapshotNum||time===baseline.serverTime) return null;
  const slots=[], origins=[], commands=[];
  for (const member of members) {
    let slot=0;
    if(member.role==='guest') {
      const matches=(native.serverPeers??[]).map((peer,index)=>({peer,index})).filter(({peer,index})=>index>0&&
        Array.isArray(peer.address)&&peer.address.length===16&&peer.address[0]===4&&
        peer.address.slice(4,8).join('.')===member.identity?.ip&&peer.address[8]*256+peer.address[9]===3074);
      if(matches.length!==1)return null;
      slot=matches[0].index;
    } else if(member.role!=='host')return null;
    const origin=native.playerOrigins?.[slot],command=native.playerCommandTimes?.[slot];
    if(slot>3||slots.includes(slot)||native.serverStates?.[slot]!==5||native.gameConnected?.[slot]!==2||
      native.nativeScores?.[slot]!==500||native.playerHealth?.[slot]!==100||native.playerPmTypes?.[slot]!==0||
      !Array.isArray(origin)||origin.length!==3||origin.some(v=>!Number.isFinite(v)||Math.abs(v)>100000)||
      origin.every(v=>v===0)||!Number.isInteger(command)||command<=0)return null;
    slots.push(slot);origins.push([...origin]);commands.push(command);
  }
  if(!slots.includes(0))return null;
  for(let i=0;i<origins.length;i++)for(let j=i+1;j<origins.length;j++)
    if(origins[i].reduce((sum,value,k)=>sum+(value-origins[j][k])**2,0)<=1)return null;
  const identity=JSON.stringify(members.map((member,index)=>[member.id,member.epoch,member.identity?.ip,slots[index]]));
  const sample={identity,snapshotNum:num,serverTime:time,commands,slots,origins};
  const settled=Boolean(previous&&previous.identity===identity&&num>previous.snapshotNum&&time>previous.serverTime&&
    commands.every((value,index)=>value>previous.commands[index]));
  return {sample,settled};
}
