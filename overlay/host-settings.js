export const MAP_SLUGS=Object.freeze(['five','kino','riese','nacht','verruckt','shinonuma','ascension','cotd','shangrila','moon']);
export const HORDE_MAPS=Object.freeze(['five','kino','riese','nacht','verruckt','shinonuma']);
const FIELDS=['mode','maxPlayers','startRound','enemyCount','counter','noPerks'];
export function normalizeHostSettings(value,mapSlug){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==FIELDS.length||FIELDS.some(k=>!Object.hasOwn(value,k)))throw Error('Invalid host settings schema');
 if(!['classic','horde'].includes(value.mode))throw Error('Invalid game mode');
 for(const[key,min,max]of[['maxPlayers',2,4],['startRound',1,255],['enemyCount',24,1024]])if(!Number.isInteger(value[key])||value[key]<min||value[key]>max)throw Error('Invalid host setting: '+key);
 if(typeof value.counter!=='boolean'||typeof value.noPerks!=='boolean')throw Error('Host toggles must be booleans');
 if(mapSlug!==undefined&&(!MAP_SLUGS.includes(mapSlug)||value.mode==='horde'&&!HORDE_MAPS.includes(mapSlug)))throw Error('Map does not include the selected mode');
 return {...value,...(value.mode==='classic'?{startRound:1,enemyCount:128,counter:false,noPerks:false}:{})};
}
export function settingsFromQuery(query,mapSlug){
 const integer=(key,fallback)=>{const raw=query.get(key);if(raw===null)return fallback;if(!/^\d{1,4}$/.test(raw))throw Error('Invalid host setting: '+key);return Number(raw);};
 const toggle=key=>{const raw=query.get(key);if(raw===null||raw==='0')return false;if(raw==='1')return true;throw Error('Invalid host toggle: '+key);};
 return normalizeHostSettings({mode:query.get('mode')??'classic',maxPlayers:integer('maxPlayers',4),startRound:integer('startRound',1),enemyCount:integer('enemyCount',128),counter:toggle('counter'),noPerks:toggle('noPerks')},mapSlug);
}
export async function hostSettingsHash(settings){
 const value=normalizeHostSettings(settings),ordered=Object.fromEntries(Object.keys(value).sort().map(k=>[k,value[k]]));
 return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(ordered)))),n=>n.toString(16).padStart(2,'0')).join('');
}
export async function contextMetadata(catalog,mapSlug,settings){
 const normalized=normalizeHostSettings(settings,mapSlug),identity=catalog.maps?.find(m=>m.slug===mapSlug)?.modes?.[normalized.mode];
 if(!identity)throw Error('The selected map/mode is not in this package');
 return {...catalog.peer,mapSlug,mode:normalized.mode,maxPlayers:normalized.maxPlayers,mapManifestSha256:identity.mapManifestSha256,mapContentSha256:identity.mapContentSha256,hostSettingsSha256:await hostSettingsHash(normalized)};
}
