import {getPlayerProfile,setPlayerProfile,importPlayerIcon,profileEmblem} from '/bo1z/coop/player-profile.js';
import {createLANLobby} from './lan-lobby.js';
import {getControllerSettings,setControllerSettings,subscribeController,controllerStatus,startControllerPolling,DEFAULT_CONTROLLER_SETTINGS,CONTROLLER_FIELDS,formatControllerValue} from '/bo1z/coop/gamepad-input.js';

export const MENU_BUILD='bo1z-lan-lobby-v2';
export const MAP_DETAILS=Object.freeze({
 five:{zone:'zombie_pentagon',place:'The Pentagon'},kino:{zone:'zombie_theater',place:'Berlin'},riese:{zone:'zombie_cod5_factory',place:'The factory'},
 nacht:{zone:'zombie_cod5_prototype',place:'The airfield'},verruckt:{zone:'zombie_cod5_asylum',place:'The asylum'},shinonuma:{zone:'zombie_cod5_sumpf',place:'The swamp'},
 ascension:{zone:'zombie_cosmodrome',place:'The cosmodrome'},cotd:{zone:'zombie_coast',place:'The frozen coast'},shangrila:{zone:'zombie_temple',place:'The lost temple'},moon:{zone:'zombie_moon',place:'Beyond Earth'}
});
export function validateMapCatalog(data){
 if(data?.build!==MENU_BUILD||!Array.isArray(data.soloMaps)||data.soloMaps.length!==10)throw Error('Invalid map collection');
 const seen=new Set();for(const m of data.soloMaps){
  if(!m||!Object.hasOwn(MAP_DETAILS,m.slug)||seen.has(m.slug)||m.url!=='/bo1z/'+m.slug||typeof m.label!=='string'||!m.label.trim()||m.label.length>80)throw Error('Invalid map');
  seen.add(m.slug);
  if(m.hostModes!==undefined&&(!Array.isArray(m.hostModes)||!m.hostModes.length||m.hostModes.some(mode=>!['classic','horde'].includes(mode))||new Set(m.hostModes).size!==m.hostModes.length))throw Error('Invalid map modes');
 }return data.soloMaps.map(m=>({slug:m.slug,label:m.label,url:m.url,hostModes:m.hostModes??['classic']}));
}
export function signalingOrigin(value){
 const url=new URL(value),host=url.hostname,parts=host.split('.').map(Number),ipv4=/^(?:0|[1-9]\d{0,2})(?:\.(?:0|[1-9]\d{0,2})){3}$/.test(host)&&parts.every(part=>part<=255);
 const local=['localhost','[::1]'].includes(host)||(ipv4&&(parts[0]===127||parts[0]===10||parts[0]===192&&parts[1]===168||parts[0]===172&&parts[1]>=16&&parts[1]<=31||parts[0]===169&&parts[1]===254));
 if(!['http:','https:'].includes(url.protocol)||(url.protocol==='http:'&&!local)||url.username||url.password||!['','/'].includes(url.pathname)||url.search||url.hash||/[?#\s]/.test(value))throw Error('Invalid room address');
 return url.origin;
}
export function mergeGamePreference(saved,key,value){
 if(!['sensitivity','volume','fullscreen'].includes(key))throw Error('Invalid preference');
 if(key==='fullscreen'?typeof value!=='boolean':!Number.isFinite(value)||value<(key==='volume'?0:0.5)||value>(key==='volume'?1:15))throw Error('Invalid preference value');
 return {...(saved&&typeof saved==='object'&&!Array.isArray(saved)?saved:{}),[key]:value,...(key==='volume'?{volumeChosen:true}:{})};
}
export function gameSettingsKeys(slug){
 if(!Object.hasOwn(MAP_DETAILS,slug))throw Error('Invalid map');
 return [slug+'-settings',MENU_BUILD+'-'+slug+'-settings'];
}

const el=id=>document.getElementById(id),home=el('home-view'),soloView=el('solo-view'),settingsView=el('settings-view'),multiplayerView=el('multiplayer-view');
const status=el('menu-status'),maps=el('map-list'),multiplayer=el('multiplayer');
let view='home',returnFocus=el('solo'),catalog=[];
const prefsKey='bo1z-title-preferences-v1';
const query=new URLSearchParams(location.search),freeHost=query.get('freehost')==='1';el('free-test-note').hidden=!freeHost;
const lanLobby=createLANLobby({build:MENU_BUILD,mapDetails:MAP_DETAILS,validateService:signalingOrigin,query});

function controls(){const root=view==='home'?home:view==='solo'?soloView:view==='multiplayer'?multiplayerView:settingsView;
 return [...root.querySelectorAll('[data-menu-control]')].filter(n=>!n.disabled&&n.getAttribute('aria-disabled')!=='true'&&!n.closest('[hidden]')&&n.getClientRects().length>0&&getComputedStyle(n).visibility!=='hidden');
}
function showView(next,origin){
 if(!['home','solo','settings','multiplayer'].includes(next))return;
 if(origin)returnFocus=origin;view=next;document.body.dataset.menuView=next;
 home.hidden=next!=='home';soloView.hidden=next!=='solo';settingsView.hidden=next!=='settings';multiplayerView.hidden=next!=='multiplayer';lanLobby.activate(next==='multiplayer');
 el('solo').setAttribute('aria-expanded',String(next==='solo'));el('settings').setAttribute('aria-expanded',String(next==='settings'));multiplayer.setAttribute('aria-expanded',String(next==='multiplayer'));
 if(next==='home')returnFocus?.focus();else (next==='solo'?maps.querySelector('a'):next==='multiplayer'?el('find-lan'):el('mouse-sensitivity'))?.focus();
 window.scrollTo({top:0,behavior:'instant'});
}
function adjustFocused(direction){const n=document.activeElement;if(n?.tagName==='SELECT'){
 n.selectedIndex=Math.max(0,Math.min(n.options.length-1,n.selectedIndex+direction));n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}));return true;
 }if(n?.type==='range'||n?.type==='number'){
 const step=Number(n.step)||1,min=Number(n.min),max=Number(n.max),value=Math.max(min,Math.min(max,Number(n.value)+step*direction));
 n.value=String(Math.round(value*1000)/1000);n.dispatchEvent(new Event('input',{bubbles:true}));return true;
 }if(n?.type==='checkbox'){n.click();return true;}return false;
}
function menuAction(action){
 if(document.visibilityState!=='visible')return false;
 if(action==='back'||action==='pause'){if(view!=='home')showView('home');return true;}
 const list=controls();if(!list.length)return false;const index=list.indexOf(document.activeElement);
 if(action==='activate'){const n=index>=0?list[index]:list[0];if(index<0)n.focus();if(n.type!=='range')n.click();return true;}
 if(['left','right'].includes(action)&&adjustFocused(action==='left'?-1:1))return true;
 if(!['up','down','left','right'].includes(action))return false;
 let delta=['up','left'].includes(action)?-1:1;
 if(view==='solo'&&document.activeElement?.classList.contains('map-card')&&['up','down'].includes(action)){
  const cards=list.filter(n=>n.classList.contains('map-card')),columns=Math.max(1,getComputedStyle(maps).gridTemplateColumns.split(' ').filter(Boolean).length);
  const target=cards.indexOf(document.activeElement)+delta*columns;
  (target<0||target>=cards.length?el('back'):cards[target]).focus();return true;
 }
 list[(index<0?0:(index+delta+list.length)%list.length)].focus();return true;
}
globalThis.__bo1zControllerMenu=Object.freeze({isOpen:()=>document.visibilityState==='visible',action:menuAction});
multiplayer.addEventListener('click',()=>showView('multiplayer',multiplayer));
el('solo').addEventListener('click',()=>showView('solo',el('solo')));el('settings').addEventListener('click',()=>showView('settings',el('settings')));
for(const n of document.querySelectorAll('[data-back]'))n.addEventListener('click',()=>showView('home'));
el('home-link').addEventListener('click',e=>{e.preventDefault();showView('home');});
document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey)return;
 if(e.key!=='Escape'&&(e.target?.tagName==='SELECT'||e.target?.tagName==='INPUT'&&!['checkbox','range'].includes(e.target.type)))return;
 if(e.key==='Escape'){e.preventDefault();menuAction('back');}
 else if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();menuAction(e.key==='ArrowUp'?'up':'down');}
 else if(['ArrowLeft','ArrowRight'].includes(e.key)&&!['range','checkbox'].includes(e.target?.type)){e.preventDefault();menuAction(e.key==='ArrowLeft'?'left':'right');}
});

let gamePrefs={sensitivity:5,volume:.5,fullscreen:false};
try{const saved=JSON.parse(localStorage.getItem(prefsKey)??localStorage.getItem(MENU_BUILD+'-five-settings')??localStorage.getItem('five-settings'));if(saved){
 if(Number.isFinite(saved.sensitivity)&&saved.sensitivity>=.5&&saved.sensitivity<=15)gamePrefs.sensitivity=saved.sensitivity;
 if(Number.isFinite(saved.volume)&&saved.volume>=0&&saved.volume<=1)gamePrefs.volume=saved.volume;
 gamePrefs.fullscreen=saved.fullscreen===true;
}}catch{}
function showGamePreferences(){el('mouse-sensitivity').value=String(gamePrefs.sensitivity);el('master-volume').value=String(gamePrefs.volume);el('fullscreen').checked=gamePrefs.fullscreen;
 el('mouse-sensitivity-value').value=gamePrefs.sensitivity.toFixed(1);el('master-volume-value').value=Math.round(gamePrefs.volume*100)+'%';
}
function saveGamePreference(key,value){gamePrefs=mergeGamePreference(gamePrefs,key,value);showGamePreferences();let saved=true;
 try{localStorage.setItem(prefsKey,JSON.stringify(gamePrefs));for(const slug of Object.keys(MAP_DETAILS))for(const settingsKey of gameSettingsKeys(slug)){
  let prior={};try{prior=JSON.parse(localStorage.getItem(settingsKey))??{};}catch{}
  localStorage.setItem(settingsKey,JSON.stringify(mergeGamePreference(prior,key,value)));
 }}catch{saved=false;}
 el('settings-status').textContent=saved?'Saved on this browser.':'Browser storage is unavailable. Map options remain available in game.';
}
showGamePreferences();
el('mouse-sensitivity').addEventListener('input',e=>saveGamePreference('sensitivity',Number(e.target.value)));
el('master-volume').addEventListener('input',e=>saveGamePreference('volume',Number(e.target.value)));
el('fullscreen').addEventListener('input',e=>saveGamePreference('fullscreen',e.target.checked));
for(const field of CONTROLLER_FIELDS){const input=document.createElement('input'),label=document.createElement('label');input.id='controller-'+field.key;input.type=field.type;input.setAttribute('data-menu-control','');input.setAttribute('aria-label',field.label);label.htmlFor=input.id;const parent=el(['verticalScale','responseCurve','adsScale','smoothing'].includes(field.key)?'controller-advanced-fields':'controller-fields');
 if(field.type==='checkbox'){label.className='check-row';label.append(document.createTextNode(field.label),input);parent.append(label);}
 else{label.className='range-label';label.textContent=field.label;const output=document.createElement('output');output.id=input.id+'-value';output.htmlFor=input.id;label.append(output);Object.assign(input,{min:String(field.min),max:String(field.max),step:String(field.step)});parent.append(label,input);}
 input.addEventListener('input',()=>{setControllerSettings({[field.key]:field.type==='checkbox'?input.checked:Number(input.value)});showControllerPreferences();});
}
function showControllerPreferences(){const s=getControllerSettings();for(const field of CONTROLLER_FIELDS){const input=el('controller-'+field.key);if(field.type==='checkbox')input.checked=s[field.key];else{input.value=String(s[field.key]);el(input.id+'-value').value=formatControllerValue(field,s[field.key]);}}}
function showProfile(){const p=getPlayerProfile();el('player-name').value=p.name;el('profile-preview').replaceChildren(profileEmblem(p));el('remove-player-icon').disabled=!p.icon;}
function saveProfile(value){try{setPlayerProfile(value);showProfile();el('profile-status').textContent='Saved. Your profile will appear in the next lobby you join and your name is passed to the next game.';}catch(error){el('profile-status').textContent=String(error.message);}}
el('save-player-name').addEventListener('click',()=>saveProfile({...getPlayerProfile(),name:el('player-name').value}));
el('player-name').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();el('save-player-name').click();}});
let iconRequest=0;
el('player-icon').addEventListener('change',async e=>{const file=e.target.files?.[0],request=++iconRequest;e.target.value='';if(!file)return;el('profile-status').textContent='Preparing your PNG…';try{const icon=await importPlayerIcon(file);if(request===iconRequest)saveProfile({...getPlayerProfile(),icon});}catch(error){if(request===iconRequest)el('profile-status').textContent=String(error.message);}});
el('remove-player-icon').addEventListener('click',()=>{iconRequest++;saveProfile({...getPlayerProfile(),icon:''});});
showProfile();
el('reset-controller').addEventListener('click',()=>{setControllerSettings(DEFAULT_CONTROLLER_SETTINGS);showControllerPreferences();});
function showControllerStatus(s=controllerStatus()){
 el('controller-status').textContent=s?.reason==='disabled'?'Controller is disabled.':s?.reason==='focus_required'?'Return to this tab to use the controller.':s?.reason==='release_controls'?'Release sticks and buttons to continue.':s?.connected?(s?.supported===false?'This controller uses an unsupported layout.':'Controller connected. D-pad to navigate, A to select, B to go back.'):'Connect a standard controller to navigate.';
}
el('reset-settings').addEventListener('click',()=>{for(const [k,v]of Object.entries({sensitivity:5,volume:.5,fullscreen:false}))saveGamePreference(k,v);
 setControllerSettings(DEFAULT_CONTROLLER_SETTINGS);showControllerPreferences();});
showControllerPreferences();showControllerStatus();const unsubscribeController=subscribeController(s=>{showControllerStatus(s);showControllerPreferences();}),controllerLease=startControllerPolling();
window.addEventListener('pagehide',()=>{controllerLease?.dispose();unsubscribeController?.();lanLobby.dispose();delete globalThis.__bo1zControllerMenu;},{once:true});

(async()=>{try{const response=await fetch('menu.json',{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('Collection unavailable');catalog=validateMapCatalog(await response.json());
 const fragment=document.createDocumentFragment();for(const [index,map]of catalog.entries()){
  const link=document.createElement('a');link.href=map.url;link.className='map-card';link.setAttribute('data-menu-control','');
  const art=document.createElement('img');art.className='map-art';art.alt='';art.loading='lazy';art.src='/bo1z/art/loadscreen_'+MAP_DETAILS[map.slug].zone+'.webp';
  const number=document.createElement('span');number.className='map-number';number.textContent=String(index+1).padStart(2,'0');
  const title=document.createElement('strong');title.textContent=map.label;const place=document.createElement('small');place.textContent=MAP_DETAILS[map.slug].place;
  link.append(art,number,title,place);fragment.append(link);
 }maps.replaceChildren(fragment);lanLobby.setCatalog(catalog);status.textContent='';if(view==='solo')maps.querySelector('a')?.focus();
}catch{status.textContent='Collection unavailable. Open the game again from your launcher.';el('solo').disabled=true;}})();
