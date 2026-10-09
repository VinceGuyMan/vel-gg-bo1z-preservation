import {getControllerSettings,setControllerSettings,subscribeController,controllerStatus,startControllerPolling} from '/bo1z/coop/gamepad-input.js';

export const MENU_BUILD='bo1z-shipping-preview-v1';
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
 }return data.soloMaps.map(m=>({slug:m.slug,label:m.label,url:m.url}));
}
export function signalingOrigin(value){
 const url=new URL(value),loopback=['localhost','[::1]'].includes(url.hostname)||/^127\./.test(url.hostname);
 if(!['http:','https:'].includes(url.protocol)||(url.protocol==='http:'&&!loopback)||url.username||url.password||!['','/'].includes(url.pathname)||url.search||url.hash||/[?#\s]/.test(value))throw Error('Invalid room address');
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

const el=id=>document.getElementById(id),home=el('home-view'),soloView=el('solo-view'),settingsView=el('settings-view');
const status=el('menu-status'),maps=el('map-list'),multiplayer=el('multiplayer');
let view='home',returnFocus=el('solo'),catalog=[];
const prefsKey='bo1z-title-preferences-v1';
const query=new URLSearchParams(location.search),freeHost=query.get('freehost')==='1';el('free-test-note').hidden=!freeHost;
try{const target=new URL(multiplayer.getAttribute('href'),location.origin);if(query.has('signaling'))target.searchParams.set('signaling',signalingOrigin(query.get('signaling')));if(freeHost)target.searchParams.set('freehost','1');multiplayer.href=target.href;}
catch{multiplayer.removeAttribute('href');multiplayer.setAttribute('aria-disabled','true');status.textContent='Room address unavailable. Open the game again from your launcher.';}

function controls(){const root=view==='home'?home:view==='solo'?soloView:settingsView;
 return [...root.querySelectorAll('[data-menu-control]')].filter(n=>!n.disabled&&n.getAttribute('aria-disabled')!=='true'&&!n.closest('[hidden]')&&n.getClientRects().length>0&&getComputedStyle(n).visibility!=='hidden');
}
function showView(next,origin){
 if(!['home','solo','settings'].includes(next))return;
 if(origin)returnFocus=origin;view=next;document.body.dataset.menuView=next;
 home.hidden=next!=='home';soloView.hidden=next!=='solo';settingsView.hidden=next!=='settings';
 el('solo').setAttribute('aria-expanded',String(next==='solo'));el('settings').setAttribute('aria-expanded',String(next==='settings'));
 if(next==='home')returnFocus?.focus();else (next==='solo'?maps.querySelector('a'):el('mouse-sensitivity'))?.focus();
 window.scrollTo({top:0,behavior:'instant'});
}
function adjustFocused(direction){const n=document.activeElement;if(n?.type==='range'){
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
el('solo').addEventListener('click',()=>showView('solo',el('solo')));el('settings').addEventListener('click',()=>showView('settings',el('settings')));
for(const n of document.querySelectorAll('[data-back]'))n.addEventListener('click',()=>showView('home'));
el('home-link').addEventListener('click',e=>{e.preventDefault();showView('home');});
document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey)return;
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
function showControllerPreferences(){const s=getControllerSettings();el('controller-enabled').checked=s.enabled;el('controller-invert').checked=s.invertY;
 el('controller-sensitivity').value=String(s.sensitivity);el('controller-deadzone').value=String(s.deadzone);
 el('controller-sensitivity-value').value=Number(s.sensitivity).toFixed(2);el('controller-deadzone-value').value=Math.round(s.deadzone*100)+'%';
}
function showControllerStatus(s=controllerStatus()){
 el('controller-status').textContent=s?.reason==='disabled'?'Controller is disabled.':s?.reason==='focus_required'?'Return to this tab to use the controller.':s?.reason==='release_controls'?'Release sticks and buttons to continue.':s?.connected?(s?.supported===false?'This controller uses an unsupported layout.':'Controller connected. D-pad to navigate, A to select, B to go back.'):'Connect a standard controller to navigate.';
}
for(const [id,key,type]of [['controller-enabled','enabled','check'],['controller-invert','invertY','check'],['controller-sensitivity','sensitivity','number'],['controller-deadzone','deadzone','number']]){
 el(id).addEventListener('input',e=>{setControllerSettings({[key]:type==='check'?e.target.checked:Number(e.target.value)});showControllerPreferences();});
}
el('reset-settings').addEventListener('click',()=>{for(const [k,v]of Object.entries({sensitivity:5,volume:.5,fullscreen:false}))saveGamePreference(k,v);
 setControllerSettings({enabled:true,deadzone:.18,sensitivity:1,invertY:false});showControllerPreferences();});
showControllerPreferences();showControllerStatus();const unsubscribeController=subscribeController(showControllerStatus),controllerLease=startControllerPolling();
window.addEventListener('pagehide',()=>{controllerLease?.dispose();unsubscribeController?.();delete globalThis.__bo1zControllerMenu;},{once:true});

(async()=>{try{const response=await fetch('menu.json',{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('Collection unavailable');catalog=validateMapCatalog(await response.json());
 const fragment=document.createDocumentFragment();for(const [index,map]of catalog.entries()){
  const link=document.createElement('a');link.href=map.url;link.className='map-card';link.setAttribute('data-menu-control','');
  const art=document.createElement('img');art.className='map-art';art.alt='';art.loading='lazy';art.src='/bo1z/art/loadscreen_'+MAP_DETAILS[map.slug].zone+'.webp';
  const number=document.createElement('span');number.className='map-number';number.textContent=String(index+1).padStart(2,'0');
  const title=document.createElement('strong');title.textContent=map.label;const place=document.createElement('small');place.textContent=MAP_DETAILS[map.slug].place;
  link.append(art,number,title,place);fragment.append(link);
 }maps.replaceChildren(fragment);if(multiplayer.hasAttribute('href'))status.textContent='';if(view==='solo')maps.querySelector('a')?.focus();
}catch{status.textContent='Collection unavailable. Open the game again from your launcher.';el('solo').disabled=true;}})();
