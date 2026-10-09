// Local profile; only the normalized thumbnail is sent to a joined room.
const KEY='bo1z-player-profile-v1',PREFIX='data:image/png;base64,';
export const DEFAULT_PLAYER_PROFILE=Object.freeze({name:'Player',icon:''});
export function normalizePlayerName(value){
 if(typeof value!=='string')throw Error('Enter a player name.');
 const name=value.trim().replace(/ +/g,' ');
 if(!/^[A-Za-z0-9 _.-]{1,24}$/.test(name))throw Error('Use 1–24 letters, numbers, spaces, underscores, dots or hyphens.');
 return name;
}
export function validatePlayerProfile(value){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join()!=='icon,name')throw Error('Invalid player profile.');
 const name=normalizePlayerName(value.name),icon=value.icon;
 if(typeof icon!=='string'||icon.length>24576||icon&&!/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(icon))throw Error('Invalid PNG thumbnail.');
 if(icon){const bytes=Uint8Array.from(atob(icon.slice(PREFIX.length)),c=>c.charCodeAt(0));
  if(bytes.length<33||[137,80,78,71,13,10,26,10].some((v,i)=>bytes[i]!==v))throw Error('Invalid PNG thumbnail.');
  const view=new DataView(bytes.buffer);if(view.getUint32(8)!==13||view.getUint32(12)!==0x49484452||view.getUint32(16)!==64||view.getUint32(20)!==64||bytes[24]!==8||![2,6].includes(bytes[25])||bytes[26]||bytes[27]||bytes[28])throw Error('Invalid PNG thumbnail.');
 }return Object.freeze({name,icon});
}
let profile=DEFAULT_PLAYER_PROFILE;
try{profile=validatePlayerProfile(JSON.parse(globalThis.localStorage?.getItem(KEY)||'null'));}catch{}
export function getPlayerProfile(){return profile;}
export function setPlayerProfile(value){const next=validatePlayerProfile(value);globalThis.localStorage.setItem(KEY,JSON.stringify(next));profile=next;return profile;}
export async function importPlayerIcon(file){
 if(!file||!file.size||file.size>2*1024*1024)throw Error('Choose a PNG smaller than 2 MB.');
 const bytes=new Uint8Array(await file.arrayBuffer());
 if(bytes.length<33||[137,80,78,71,13,10,26,10].some((v,i)=>bytes[i]!==v))throw Error('Choose a PNG image.');
 const view=new DataView(bytes.buffer),width=view.getUint32(16),height=view.getUint32(20);
 if(view.getUint32(8)!==13||view.getUint32(12)!==0x49484452||!width||!height||width>4096||height>4096)throw Error('PNG dimensions must be between 1 and 4096 pixels.');
 const bitmap=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
 try{const canvas=document.createElement('canvas');canvas.width=canvas.height=64;const context=canvas.getContext('2d');if(!context)throw Error('Image conversion is unavailable.');
  const size=Math.min(bitmap.width,bitmap.height);context.drawImage(bitmap,(bitmap.width-size)/2,(bitmap.height-size)/2,size,size,0,0,64,64);
  return validatePlayerProfile({name:'Player',icon:canvas.toDataURL('image/png')}).icon;
 }finally{bitmap.close();}
}
export function profileEmblem(profile,doc=document){
 const badge=doc.createElement('span');badge.className='player-emblem';badge.setAttribute('aria-hidden','true');
 try{const value=validatePlayerProfile(profile);if(value.icon){const img=doc.createElement('img');img.src=value.icon;img.alt='';badge.append(img);}else badge.textContent=value.name[0].toUpperCase();}
 catch{badge.textContent='?';}return badge;
}
