// Exact room/RTC peer identity. No engine or network calls.
export const PEER_FIELDS=Object.freeze(["overlayBuildId", "protocolVersion", "bridgeAbiVersion", "patchSchemaRevision", "baseWasmSha256", "patchedWasmSha256", "patchManifestSha256", "shellManifestSha256", "mapManifestSha256", "mapContentSha256", "mapSlug", "mode", "maxPlayers"]);
export function validatePeerMetadata(value) {
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==PEER_FIELDS.length||PEER_FIELDS.some(k=>!Object.hasOwn(value,k)))throw Error('metadata_schema_mismatch');
 for(const key of PEER_FIELDS){const v=value[key];
  if(key.endsWith('Sha256')?typeof v!=='string'||!(/^[a-f0-9]{64}$/).test(v):key==='overlayBuildId'?v!=='bo1z-shipping-preview-v1':key==='mapSlug'?v!=='five':key==='mode'?v!=='classic':key==='maxPlayers'?v!==4:v!==1)throw Error('metadata_schema_mismatch');
 }
 return Object.fromEntries(PEER_FIELDS.map(key=>[key,value[key]]));
}
