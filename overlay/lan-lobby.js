import {getPlayerProfile,profileEmblem} from '/bo1z/coop/player-profile.js';
const ROOM_CODE=/^[A-Z0-9]{6}$/;
const DEFAULT_SETTINGS=Object.freeze({mode:'classic',maxPlayers:4,startRound:1,enemyCount:128,counter:false,noPerks:false});
const boundedInteger=(value,min,max,fallback)=>Number.isInteger(Number(value))&&Number(value)>=min&&Number(value)<=max?Number(value):fallback;

export function lobbySettings(value={}){
 const mode=value.mode==='horde'?'horde':'classic';
 return {mode,maxPlayers:boundedInteger(value.maxPlayers,2,4,4),startRound:mode==='horde'?boundedInteger(value.startRound,1,255,1):1,
  enemyCount:mode==='horde'?boundedInteger(value.enemyCount,24,1024,128):128,counter:mode==='horde'&&(value.counter===true||value.counter===1||value.counter==='1'),noPerks:mode==='horde'&&(value.noPerks===true||value.noPerks===1||value.noPerks==='1')};
}
export function lobbyURL({mapSlug,service,roomCode='',settings=DEFAULT_SETTINGS,title='',host=false},origin){
 if(!/^[a-z]+$/.test(mapSlug)||(!host&&!ROOM_CODE.test(roomCode)))throw Error('Invalid lobby selection');
 const url=new URL('/bo1z/'+mapSlug,origin),options=lobbySettings(settings);
 url.searchParams.set('coop','1');url.searchParams.set('renderer','webgl2');url.searchParams.set('signaling',service);
 for(const[key,value]of Object.entries(options))url.searchParams.set(key,typeof value==='boolean'?(value?'1':'0'):String(value));
 if(host){url.searchParams.set('autohost','1');if(title.trim())url.searchParams.set('name',title.trim().slice(0,32));}
 else{url.searchParams.set('room',roomCode);url.searchParams.set('autojoin','1');}
 return url;
}
export function normalizeLANRooms(data,{build,mapDetails,validateService}){
 if(data?.ok!==true||!Array.isArray(data.rooms)||data.rooms.length>32)throw Error('The launcher returned an invalid lobby list.');
 const rooms=[],seen=new Set();
 for(const item of data.rooms){
  try{
   const metadata=item?.metadata??{},mapSlug=item.mapSlug??metadata.mapSlug,code=item.code??item.roomCode,service=validateService(item.service??item.signalingUrl);
   if(!Object.hasOwn(mapDetails,mapSlug)||typeof code!=='string'||!ROOM_CODE.test(code))continue;
   const identity=service+'|'+code;if(seen.has(identity))continue;seen.add(identity);
   const settings=lobbySettings({...metadata,...metadata.settings,...item.settings,mode:item.mode??metadata.mode??item.settings?.mode,maxPlayers:item.maxPlayers??metadata.maxPlayers??item.settings?.maxPlayers});
   const buildId=item.build??metadata.overlayBuildId,transport=item.transport??'webrtc',players=boundedInteger(item.memberCount??item.players,1,4,1);
   const closed=item.closed===true,started=item.started===true,compatible=buildId===build&&transport==='webrtc';
   const title=typeof item.title==='string'?item.title.slice(0,32):typeof item.name==='string'?item.name.slice(0,32):'Zombies lobby';
   rooms.push({service,code,title:title.trim()||'Zombies lobby',mapSlug,settings,players,maxPlayers:settings.maxPlayers,build:buildId,transport,started,closed,compatible,
    reason:closed?'Closed':started?'In progress':buildId!==build?'Different build':transport!=='webrtc'?'Different connection':players>=settings.maxPlayers?'Full':''});
  }catch{/* A malformed advertisement never creates an actionable join route. */}
 }
 return rooms.sort((a,b)=>Number(Boolean(a.reason))-Number(Boolean(b.reason))||a.title.localeCompare(b.title)||a.code.localeCompare(b.code));
}

export function createLANLobby({build,mapDetails,validateService,query,origin=location.origin}){
 const el=id=>document.getElementById(id),state={active:false,tab:'find',catalog:[],rooms:[],selected:null,controller:null,timer:null,scanId:0,disposed:false};
 const list=el('lan-rooms'),empty=el('lan-state'),message=el('lobby-message');
 const getMap=slug=>state.catalog.find(map=>map.slug===slug);
 const mapName=slug=>getMap(slug)?.label??({'five':'Five','kino':'Kino der Toten','riese':'Der Riese','nacht':'Nacht der Untoten','verruckt':'Verrückt','shinonuma':'Shi No Numa','ascension':'Ascension','cotd':'Call of the Dead','shangrila':'Shangri-La','moon':'Moon'})[slug]??slug;
 const picture=slug=>'/bo1z/art/loadscreen_'+mapDetails[slug].zone+'.webp';
 function uiNode(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
 function setEmpty(kind,title,description){empty.dataset.state=kind;empty.hidden=false;empty.querySelector('strong').textContent=title;empty.querySelector('p').textContent=description;empty.querySelector('.scan-symbol').textContent=kind==='scanning'?'◌':kind==='error'?'!':'+';}
 function hostOptions(){return lobbySettings({mode:el('host-mode').value,maxPlayers:el('host-players').value,startRound:el('host-round').value,enemyCount:el('host-enemies').value,counter:el('host-counter').checked,noPerks:el('host-no-perks').checked});}
 function preview(room=null,hosting=false){
  el('host-name').placeholder=getPlayerProfile().name+"'s lobby";
  const slug=hosting?el('host-map').value:room?.mapSlug??'five',settings=hosting?hostOptions():room?.settings??DEFAULT_SETTINGS;
  const players=hosting?1:room?.players??0,maxPlayers=settings.maxPlayers;
  el('lobby-map-art').src=picture(Object.hasOwn(mapDetails,slug)?slug:'five');el('preview-map').textContent=mapName(slug);
  el('preview-mode').textContent=settings.mode==='horde'?'Horde survival':'Classic survival';
  el('preview-title').textContent=hosting?(el('host-name').value.trim()||el('host-name').placeholder):room?.title??'Your squad';el('preview-occupancy').textContent=players+' / '+maxPlayers;
  const roster=document.createDocumentFragment();for(let index=0;index<maxPlayers;index++){
   const occupied=index<players,row=uiNode('li',undefined,occupied?'':'open-slot');
   row.append(hosting&&index===0?profileEmblem(getPlayerProfile()):uiNode('span',occupied?(index===0?'Ⅰ':String(index+1)):'+','player-emblem'),uiNode('span',occupied?(index===0?(hosting?getPlayerProfile().name:'Host'):'Player '+(index+1)):'Open slot'));
   if(occupied&&index===0)row.append(uiNode('small','Host'));roster.append(row);
  }el('lobby-roster').replaceChildren(roster);
  el('preview-detail').textContent=hosting?(settings.mode==='horde'?'Starting round '+settings.startRound+' · '+settings.enemyCount+' maximum active zombies.':'Original Classic rules. The host starts after players are ready.'):
   room?(room.reason?room.reason+'. ':room.players+' player'+(room.players===1?'':'s')+' waiting. ')+room.service+' · Room '+room.code:'Select a lobby, or create one for your friends.';
 }
 function choose(room){state.selected=room;for(const row of list.children){const selected=row.dataset.roomIdentity===room.service+'|'+room.code;row.classList.toggle('selected',selected);row.setAttribute('aria-pressed',String(selected));}
  el('join-lan').disabled=Boolean(room.reason);preview(room);
 }
 function renderRooms(){
  const focusedIdentity=document.activeElement?.dataset?.roomIdentity,fragment=document.createDocumentFragment();
  for(const room of state.rooms){
   const row=uiNode('button',undefined,'session-row'+(room.reason?' unavailable':''));row.type='button';row.setAttribute('data-menu-control','');row.dataset.roomIdentity=room.service+'|'+room.code;row.setAttribute('aria-pressed','false');
   const art=uiNode('img',undefined,'session-row-art');art.src=picture(room.mapSlug);art.alt='';
   const labels=uiNode('span',undefined,'session-row-label');labels.append(uiNode('strong',room.title),uiNode('small',mapName(room.mapSlug)+' · '+(room.settings.mode==='horde'?'Horde':'Classic')));
   row.append(art,labels,uiNode('span',room.reason||room.players+' / '+room.maxPlayers,'session-row-players'));
   row.addEventListener('click',()=>choose(room));row.addEventListener('focus',()=>choose(room));row.addEventListener('dblclick',()=>{choose(room);joinSelected();});fragment.append(row);
  }list.replaceChildren(fragment);el('lan-count').textContent=state.rooms.length+' available '+(state.rooms.length===1?'lobby':'lobbies');
  empty.hidden=state.rooms.length>0;const old=state.selected&&state.rooms.find(room=>room.service===state.selected.service&&room.code===state.selected.code);
  if(state.rooms.length)choose(old??state.rooms[0]);else{state.selected=null;el('join-lan').disabled=true;preview();}
  if(focusedIdentity){const focused=[...list.children].find(row=>row.dataset.roomIdentity===focusedIdentity);(focused??el('refresh-lan')).focus({preventScroll:true});}
 }
 function scheduleScan(){clearTimeout(state.timer);if(state.active&&state.tab==='find'&&!state.disposed)state.timer=setTimeout(()=>void scan(),5000);}
 async function scan(force=false){
  if(!state.active||state.tab!=='find'||state.disposed||state.controller)return;
  const controller=new AbortController(),scanId=++state.scanId;state.controller=controller;const timeout=setTimeout(()=>controller.abort(),4000);
  el('refresh-lan').disabled=true;el('refresh-lan').textContent='Scanning…';
  if(!state.rooms.length&&(force||!empty.dataset.state))setEmpty('scanning','Scanning your local network…','Keep both launchers open on the same network.');
  try{
   const response=await fetch('/coop/lan/rooms',{signal:controller.signal,cache:'no-store',redirect:'error'});if(!response.ok)throw Error('LAN discovery is unavailable on this launcher.');
   const result=await response.json();if(state.disposed||!state.active||state.tab!=='find'||scanId!==state.scanId)return;
   state.rooms=normalizeLANRooms(result,{build,mapDetails,validateService});renderRooms();
   const warnings=Array.isArray(result.warnings)?result.warnings.filter(value=>typeof value==='string').map(value=>value.slice(0,180)).slice(0,3):[];
   el('lan-warning').hidden=!warnings.length;el('lan-warning').textContent=warnings.join(' ');
   if(!state.rooms.length)setEmpty(warnings.length?'error':'empty',warnings.length?'LAN discovery needs attention':'No LAN lobbies found',warnings.length?'Check the launcher and firewall. Refresh after creating a host lobby.':'Choose Create lobby on one computer. Keep both launchers open and allow local network access through the firewall.');
  }catch(error){if(state.disposed||!state.active||state.tab!=='find'||scanId!==state.scanId)return;
   state.rooms=[];renderRooms();setEmpty('error','Could not scan for lobbies',error?.name==='AbortError'?'The launcher did not answer in time. Check its terminal, then refresh.':String(error?.message??'Check the launcher and refresh.').slice(0,200));
  }finally{clearTimeout(timeout);if(state.controller===controller){state.controller=null;el('refresh-lan').disabled=false;el('refresh-lan').textContent='Refresh';scheduleScan();}}
 }
 function stopScan(){clearTimeout(state.timer);state.scanId++;state.controller?.abort();state.controller=null;el('refresh-lan').disabled=false;el('refresh-lan').textContent='Refresh';}
 function chooseTab(tab){state.tab=tab;message.textContent='';el('lan-browser').hidden=tab!=='find';el('host-lan').hidden=tab!=='create';
  for(const[id,name]of[['find-lan','find'],['create-lan','create']]){el(id).classList.toggle('selected',name===tab);el(id).setAttribute('aria-pressed',String(name===tab));}
  stopScan();if(tab==='find'){preview(state.selected);void scan(true);}else preview(null,true);
 }
 function updateHostMap(){const map=getMap(el('host-map').value),previous=el('host-mode').value,modes=map?.hostModes??['classic'];
  const options=document.createDocumentFragment();for(const mode of modes){const option=uiNode('option',mode==='horde'?'Horde':'Classic');option.value=mode;options.append(option);}el('host-mode').replaceChildren(options);
  el('host-mode').value=modes.includes(previous)?previous:modes[0]??'classic';updateHostSettings();
 }
 function updateHostSettings(){el('host-horde').hidden=el('host-mode').value!=='horde';el('host-count-warning').hidden=Number(el('host-enemies').value)<=300;preview(null,true);}
 function launch(options){const url=lobbyURL(options,origin);
  // Carry the invitation once within this tab; never put a secret in URL history.
  if(options.roomCode){try{if(typeof options.invite==='string'&&options.invite)sessionStorage.setItem('bo1z-lobby-invite-v1',JSON.stringify({service:options.service,roomCode:options.roomCode,invite:options.invite}));else sessionStorage.removeItem('bo1z-lobby-invite-v1');}
   catch{if(options.invite)throw Error('Invitation storage is unavailable for this tab. Enable browser session storage and retry.');}}
 if(query.get('freehost')==='1')url.searchParams.set('freehost','1');location.assign(url.href);}
 function joinSelected(){if(!state.selected||state.selected.reason)return;message.textContent='Opening '+mapName(state.selected.mapSlug)+' and joining the selected lobby…';
  launch({mapSlug:state.selected.mapSlug,service:state.selected.service,roomCode:state.selected.code,settings:state.selected.settings});}
 el('find-lan').addEventListener('click',()=>chooseTab('find'));el('create-lan').addEventListener('click',()=>chooseTab('create'));
 el('refresh-lan').addEventListener('click',()=>void scan(true));el('join-lan').addEventListener('click',joinSelected);
 el('host-map').addEventListener('change',updateHostMap);for(const id of ['host-name','host-mode','host-players','host-round','host-enemies','host-counter','host-no-perks'])el(id).addEventListener('input',updateHostSettings);
 el('host-lan').addEventListener('submit',event=>{event.preventDefault();try{
  const map=getMap(el('host-map').value);if(!map)throw Error('Map collection is still loading.');
  const service=validateService(query.get('signaling')??'http://127.0.0.1:8768'),settings=hostOptions();
  if(!(map.hostModes??['classic']).includes(settings.mode))throw Error('This map does not include that mode.');
  message.textContent='Opening '+map.label+' and creating your lobby…';launch({mapSlug:map.slug,service,settings,title:el('host-name').value.trim()||el('host-name').placeholder,host:true});
 }catch(error){message.textContent=String(error?.message??error).slice(0,200);}});
 el('manual-join-form').addEventListener('submit',async event=>{event.preventDefault();const submit=event.currentTarget.querySelector('button');submit.disabled=true;try{
  const service=validateService(el('manual-service').value.trim()),roomCode=el('manual-code').value.trim().toUpperCase();
  if(!ROOM_CODE.test(roomCode))throw Error('Enter the host’s six-character room code.');
  message.textContent='Looking up the host’s map and settings…';
  const response=await fetch(service+'/coop/api/rooms/'+roomCode+'/configuration',{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(4000)});
  if(!response.ok)throw Error('Room not found. Check the host’s address and room code.');
  const summary=await response.json(),rooms=normalizeLANRooms({ok:true,rooms:[{...summary,signalingUrl:service}]},{build,mapDetails,validateService});
  const room=rooms.find(value=>value.code===roomCode);if(!room)throw Error('The host returned an invalid room configuration.');
  if(room.reason)throw Error('Cannot join this lobby: '+room.reason+'.');
  launch({mapSlug:room.mapSlug,service:room.service,roomCode:room.code,settings:room.settings,invite:el('manual-invite').value});
 }catch(error){message.textContent=error?.name==='TimeoutError'?'The host did not answer. Check its launcher and firewall.':String(error?.message??error).slice(0,200);}finally{submit.disabled=false;}});
 try{el('manual-service').value=query.has('signaling')?validateService(query.get('signaling')):'';}catch{message.textContent='Launcher address unavailable. Open the game again from its launcher.';}
 if(query.has('room'))el('manual-code').value=query.get('room').slice(0,6).toUpperCase();
 return Object.freeze({setCatalog(catalog){state.catalog=catalog;const options=document.createDocumentFragment();for(const map of catalog){const option=uiNode('option',map.label);option.value=map.slug;options.append(option);}el('host-map').replaceChildren(options);el('host-map').value='five';el('host-submit').disabled=!catalog.length;updateHostMap();},
  activate(active){state.active=active;if(active){if(state.tab==='find')void scan(true);else preview(null,true);}else stopScan();},
  dispose(){state.disposed=true;state.active=false;stopScan();}});
}
