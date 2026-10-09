// Controller input through the preserved browser key/mouse seam only.
// Standard Gamepad mapping: https://www.w3.org/TR/gamepad/#remapping
const STORAGE_KEY = 'bo1z-preview-controller-v1';
export const DEFAULT_CONTROLLER_SETTINGS = Object.freeze({enabled:true,deadzone:0.18,sensitivity:1,invertY:false});
const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
const finite=v=>typeof v==='number'&&Number.isFinite(v);
let settings={...DEFAULT_CONTROLLER_SETTINGS}, status={connected:false,supported:false,context:'inactive',reason:'connect_controller',family:'Standard'}, session=null;
const subscribers=new Set();
try { const s=JSON.parse(globalThis.localStorage?.getItem(STORAGE_KEY)||'null'); if(s&&typeof s==='object')settings=validateSettings(s,settings); } catch {}
function validateSettings(s,previous){
 const r={...previous};
 if(typeof s.enabled==='boolean')r.enabled=s.enabled;
 if(finite(s.deadzone))r.deadzone=clamp(s.deadzone,0.05,0.4);
 if(finite(s.sensitivity))r.sensitivity=clamp(s.sensitivity,0.25,3);
 if(typeof s.invertY==='boolean')r.invertY=s.invertY;
 return r;
}
export function getControllerSettings(){return Object.freeze({...settings});}
export function controllerStatus(){return Object.freeze({...status,settings:getControllerSettings()});}
function notify(){for(const fn of subscribers){try{fn(controllerStatus());}catch{}}}
export function setControllerSettings(value){
 if(!value||typeof value!=='object'||Array.isArray(value))throw new TypeError('Invalid controller settings');
 settings=validateSettings(value,settings);session?.release();
 try{globalThis.localStorage?.setItem(STORAGE_KEY,JSON.stringify(settings));}catch{}
 notify();return getControllerSettings();
}
export function subscribeController(fn){if(typeof fn!=='function')throw new TypeError('Expected listener');if(subscribers.size>=64)throw new Error('Controller listener limit');subscribers.add(fn);fn(controllerStatus());return()=>subscribers.delete(fn);}
export function radialDeadzone(x,y,deadzone=0.18){
 if(!finite(x)||!finite(y)||!finite(deadzone))return{x:0,y:0};
 x=clamp(x,-1,1);y=clamp(y,-1,1);deadzone=clamp(deadzone,0.05,0.4);
 const magnitude=Math.hypot(x,y);if(magnitude<=deadzone)return{x:0,y:0};
 const scaled=clamp((magnitude-deadzone)/(1-deadzone),0,1);
 return{x:x/magnitude*scaled,y:y/magnitude*scaled};
}
// OR ownership prevents a pad key-up from releasing a physical held key.
export function createInputArbiter(send){
 const sources=new Map();
 function input(source,event){
  if(event.kind!=='key'){send(event);return;}
  if(!Number.isInteger(event.key)||event.key<0||event.key>255)return;
  const before=[...sources.values()].some(keys=>keys.has(event.key));
  let keys=sources.get(source);if(!keys){keys=new Set();sources.set(source,keys);}
  if(event.down)keys.add(event.key);else keys.delete(event.key);
  const after=[...sources.values()].some(held=>held.has(event.key));
  if(before!==after)send({...event,down:after});
 }
 function release(source){const keys=sources.get(source);if(!keys)return;for(const key of [...keys])input(source,{kind:'key',key,down:false});sources.delete(source);}
 return{input,release,dispose(){for(const source of [...sources.keys()])release(source);},held:()=>[...new Set([...sources.values()].flatMap(keys=>[...keys]))]};
}
const BUTTON_KEYS=Object.freeze({0:32,1:99,2:114,3:49,4:52,5:103,6:201,7:200,8:9,9:27,10:160,11:118,12:102,13:159,14:49,15:120});
export const CONTROLLER_BINDINGS=Object.freeze({...BUTTON_KEYS});
const buttonValue=(p,i)=>{const b=p?.buttons?.[i];return b&&finite(b.value)?clamp(b.value,0,1):b?.pressed===true?1:0;};
const axis=(p,i)=>finite(p?.axes?.[i])?clamp(p.axes[i],-1,1):0;
const family=p=>/dualshock|dualsense|playstation|sony/i.test(p?.id||'')?'PlayStation':/xbox|xinput|microsoft/i.test(p?.id||'')?'Xbox':'Standard';
function neutral(p,s){return Math.hypot(axis(p,0),axis(p,1))<=s.deadzone&&Math.hypot(axis(p,2),axis(p,3))<=s.deadzone&&Array.from({length:16},(_,i)=>buttonValue(p,i)).every(v=>v<0.25);}
export function createGamepadDriver({send=()=>{},getMode=()=> 'inactive',menuAction=()=>{},getSettings=getControllerSettings,onStatus=()=>{}}={}){
 let held=new Set(),previousButtons=new Set(),identity=null,previousTime=null,mode='inactive',armed=false,menuDirection='',repeatAt=0,disposed=false;
 function emit(event){send({...event,time:previousTime??0});}
 function release(){for(const key of held)emit({kind:'key',key,down:false});held.clear();previousButtons.clear();armed=false;menuDirection='';repeatAt=0;}
 function sync(keys){for(const key of held)if(!keys.has(key))emit({kind:'key',key,down:false});for(const key of keys)if(!held.has(key))emit({kind:'key',key,down:true});held=keys;}
 function step(pads,time,{focused=true,visible=true}={}){
  if(disposed)return;
  const s=getSettings();const validTime=finite(time)&&time>=0;
  const dt=validTime&&previousTime!==null?clamp(time-previousTime,0,50)/1000:0;previousTime=validTime?time:null;
  const connected=Array.from(pads||[]).filter(p=>p&&p.connected!==false),p=connected.find(p=>p.mapping==='standard'&&p.axes?.length>=4&&p.buttons?.length>=16);
  const nextIdentity=p?String(p.index)+':'+String(p.id):null;
  let nextMode=p&&s.enabled&&focused&&visible&&validTime?getMode():'inactive';if(!['game','native-menu','web-menu','inactive'].includes(nextMode))nextMode='inactive';
  if(nextIdentity!==identity||nextMode!==mode){release();identity=nextIdentity;mode=nextMode;}
  if(!p||!s.enabled||!focused||!visible||!validTime||mode==='inactive'){
   release();onStatus({connected:connected.length>0,supported:!!p,context:mode,family:family(p),reason:!s.enabled?'disabled':!p?(connected.length?'mapping_unsupported':'connect_controller'):!focused||!visible?'focus_required':'play_click_required'});return;
  }
  if(!armed){if(neutral(p,s))armed=true;else{onStatus({connected:true,supported:true,context:mode,family:family(p),reason:'release_controls'});return;}}
  const buttons=new Set(Array.from({length:16},(_,i)=>i).filter(i=>buttonValue(p,i)>=0.5));
  if(mode==='game'){
   const keys=new Set([...buttons].map(i=>BUTTON_KEYS[i]).filter(k=>k!==undefined));
   const move=radialDeadzone(axis(p,0),axis(p,1),s.deadzone);
   if(move.x<-0.20)keys.add(97);if(move.x>0.20)keys.add(100);if(move.y<-0.20)keys.add(119);if(move.y>0.20)keys.add(115);
   sync(keys);
   const look=radialDeadzone(axis(p,2),axis(p,3),s.deadzone),speed=720*s.sensitivity;
   if(dt&&(look.x||look.y))emit({kind:'mouse',dx:look.x*speed*dt,dy:look.y*speed*dt*(s.invertY?-1:1)});
  }else{
   sync(new Set());
   const a=radialDeadzone(axis(p,0),axis(p,1),s.deadzone);
   const direction=buttons.has(12)||a.y<-.45?'up':buttons.has(13)||a.y>.45?'down':buttons.has(14)||a.x<-.45?'left':buttons.has(15)||a.x>.45?'right':'';
   const action=name=>{if(mode==='web-menu')menuAction(name);else{const key={up:154,down:155,left:156,right:157,activate:13,back:27,pause:27}[name];if(key!==undefined){emit({kind:'key',key,down:true});emit({kind:'key',key,down:false});}}};
   if(direction&&(direction!==menuDirection||time>=repeatAt)){action(direction);repeatAt=time+(direction!==menuDirection?350:140);}menuDirection=direction;
   if(mode==='native-menu'&&buttons.has(8)&&!previousButtons.has(8))menuAction('settings');
   for(const [i,name] of [[0,'activate'],[1,'back'],[9,'pause']])if(buttons.has(i)&&!previousButtons.has(i))action(name);
  }
  previousButtons=buttons;onStatus({connected:true,supported:true,context:mode,family:family(p),reason:'ready'});
 }
 return{step,release,dispose(){release();disposed=true;},snapshot:()=>({heldKeys:[...held],armed,context:mode})};
}
export function startControllerPolling({send=()=>{},getMode=()=> 'inactive',menu:localMenu,env=globalThis}={}){
 if(session)session.dispose();
 let frame=null,disposed=false,lastStatus='',focused=env.document?.hasFocus?.()??true;
 const menu=()=>localMenu?.()??env.__bo1zControllerMenu;
 const driver=createGamepadDriver({send,getMode:()=>menu()?.isOpen?.()?'web-menu':getMode(),menuAction:a=>menu()?.action?.(a),onStatus:s=>{const serial=JSON.stringify(s);if(serial!==lastStatus){lastStatus=serial;status=s;notify();}}});
 const listeners=[];const on=(target,key,fn)=>{target?.addEventListener?.(key,fn);listeners.push(()=>target?.removeEventListener?.(key,fn));};
 on(env,'blur',()=>{focused=false;driver.release();});on(env,'focus',()=>{focused=true;});on(env,'gamepaddisconnected',()=>driver.release());on(env.document,'visibilitychange',()=>{if(env.document.hidden)driver.release();});on(env.document,'pointerlockchange',()=>driver.release());
 function tick(t){if(disposed)return;let pads=[];try{pads=env.navigator?.getGamepads?.()??[];}catch{}driver.step(pads,t,{focused,visible:!env.document?.hidden});frame=env.requestAnimationFrame?.(tick)??null;}
 frame=env.requestAnimationFrame?.(tick)??null;
 const api={release:()=>driver.release(),snapshot:driver.snapshot,dispose(){if(disposed)return;disposed=true;if(frame!==null)env.cancelAnimationFrame?.(frame);listeners.forEach(fn=>fn());driver.dispose();if(session===api)session=null;}};session=api;return api;
}
// Wrap only the browser capture seam. The original keyboard/mouse routine is
// retained and owns actual pointer lock/audio activation; controller polling
// never fabricates DOM key/mouse/user-activation events.
export function captureWithController(captureOriginal,canvas,send,hooks={}){
 const arbiter=createInputArbiter(send);let enabled=false;
 const original=captureOriginal(canvas,event=>arbiter.input('physical',event),hooks);
 let pad;
 const panel=installControllerPanel(canvas,globalThis,{releaseInput:()=>{pad?.release();original.release();}});
 pad=startControllerPolling({send:event=>arbiter.input('controller',event),menu:()=>panel.menu, getMode:()=>enabled?(hooks.menuOpen?.()?'native-menu':globalThis.document?.pointerLockElement===canvas?'game':'inactive'):'inactive'});
 return{...original,enable(value){enabled=Boolean(value);if(!enabled)pad.release();original.enable(value);},release(){pad.release();original.release();},unlock(){pad.release();original.unlock();},dispose(){pad.dispose();panel.dispose();original.dispose();arbiter.dispose();}};
}

// Local settings remain accessible while loading or after the original page
// releases its pointer. Opening this panel never unlocks or pauses the engine.
export function installControllerPanel(canvas,env=globalThis,{releaseInput=()=>{}}={}){
 const doc=env.document;if(!doc?.createElement)return{menu:null,dispose(){}};
 const panel=doc.createElement('details');panel.id='bo1z-controller-panel';
 panel.style.cssText='position:fixed;left:16px;bottom:16px;z-index:10000;max-width:min(340px,calc(100vw - 32px));background:#111a20;color:#edf4ed;border:1px solid #586968;border-radius:7px;padding:9px 12px;font:13px system-ui;';
 const summary=doc.createElement('summary');summary.textContent='Controller';summary.style.cursor='pointer';panel.append(summary);
 const message=doc.createElement('p');message.setAttribute('role','status');panel.append(message);
 const controls=[];
 const field=(label,type,key,min,max,step)=>{const row=doc.createElement('label');row.style.cssText='display:flex;align-items:center;justify-content:space-between;gap:15px;margin:12px 0;';row.append(doc.createTextNode(label));const input=doc.createElement('input');input.type=type;input.dataset.controllerSetting=key;if(min!==undefined){input.min=min;input.max=max;input.step=step;}input.setAttribute('aria-label',label);input.addEventListener('input',()=>setControllerSettings({[key]:type==='checkbox'?input.checked:Number(input.value)}));row.append(input);panel.append(row);controls.push(input);return input;};
 field('Enable controller','checkbox','enabled');field('Stick deadzone','range','deadzone',0.05,0.4,0.01);field('Look sensitivity','range','sensitivity',0.25,3,0.05);field('Invert vertical look','checkbox','invertY');
 const help=doc.createElement('p');help.textContent='Standard Xbox / PlayStation: left stick move, right stick aim. Triggers aim / fire. A / Cross jump, B / Circle crouch, X / Square reload, Y / Triangle switch. D-pad Up interact. View / Share in the pause menu opens these settings. Click Play with mouse once to enable audio and capture.';help.style.cssText='color:#b8c6c4;font-size:12px;line-height:1.5;';panel.append(help);
 const unsubscribe=subscribeController(s=>{message.textContent={connect_controller:'Connect a controller and press a button.',mapping_unsupported:'This controller has no standard browser mapping.',disabled:'Controller disabled.',focus_required:'Return to this tab to use the controller.',play_click_required:'Click Play to enter the game.',release_controls:'Release sticks and buttons to resume.',ready:s.family+' controller connected.'}[s.reason]||'Controller available.';const settings=s.settings;for(const input of controls){const v=settings[input.dataset.controllerSetting];if(input.type==='checkbox')input.checked=v;else input.value=String(v);}});
 const listeners=[],on=(target,type,fn,options)=>{target.addEventListener(type,fn,options);listeners.push(()=>target.removeEventListener(type,fn,options));};
 const keyboardGuard=e=>{if(panel.contains(e.target))e.stopPropagation();};on(panel,'focusin',releaseInput);on(panel,'toggle',()=>{if(panel.open)releaseInput();});on(env,'keydown',keyboardGuard,true);on(env,'keyup',keyboardGuard,true);
 for(const type of ['click','mousedown','mouseup'])on(panel,type,e=>e.stopPropagation());
 const visibility=()=>{const locked=doc.pointerLockElement===canvas;panel.hidden=locked;if(locked)panel.open=false;};on(doc,'pointerlockchange',visibility);visibility();(doc.body||doc.documentElement).append(panel);
 const focusable=()=>[summary,...controls];
 const menu={isOpen:()=>!panel.hidden&&panel.open,action(name){const list=focusable();let i=list.indexOf(doc.activeElement);if(name==='settings'){if(!panel.hidden){panel.open=true;summary.focus();}return;}if(name==='back'||name==='pause'){panel.open=false;summary.focus();return;}if(name==='up'||name==='down'){i=(i+(name==='down'?1:-1)+list.length)%list.length;list[i].focus();return;}const target=list[Math.max(0,i)];if((name==='left'||name==='right')&&target.type==='range'){target.value=String(clamp(Number(target.value)+(name==='right'?1:-1)*Number(target.step),Number(target.min),Number(target.max)));target.dispatchEvent(new Event('input',{bubbles:true}));}else if(name==='activate'&&target.type==='checkbox'){target.checked=!target.checked;target.dispatchEvent(new Event('input',{bubbles:true}));}else if(name==='activate'&&target===summary){panel.open=!panel.open;}}};
 return{menu,dispose(){unsubscribe();listeners.forEach(fn=>fn());panel.remove();}};
}
