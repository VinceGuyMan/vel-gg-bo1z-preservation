// Verification accompanies the preserved loader; it never instantiates WASM.
// Byte hashes identify this reviewed ABI, not the trustworthiness of a package.
export const RUNTIME_PINS = Object.freeze({
 baseWasmSha256:'61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98',
 patchedWasmSha256:'29c436447d467e63ae05346bdb5ed53c5f79ce0ab5e7493148200797b7129628',
 bridgeSourceSha256:'10a153a72f020b2927cccf7d9e11e176adcbe7d9be0a78251d4ec0cd6ed1e7c8',
 observerSourceSha256:'4692475b3756ee37ae5ba2d2b90fcc39a7c2ab10448da47d41b5c86c4a93b116',
 nativeAdmissionSourceSha256:'854eb7e429c95b78e6d6b315de79827c9d618d59e191cd7a7d5f2d13461d9d3c'
});
const associations=new WeakMap(),brands=new WeakMap();
const object=v=>v!==null&&(typeof v==='object'||typeof v==='function');
async function digest(bytes) {
 const hash=await globalThis.crypto.subtle.digest('SHA-256',bytes);
 return Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('');
}
function copyBytes(value) {
 if(value instanceof ArrayBuffer)return new Uint8Array(value).slice();
 if(ArrayBuffer.isView(value))return new Uint8Array(value.buffer,value.byteOffset,value.byteLength).slice();
 throw Error('runtime_bytes_unavailable');
}
async function source(name,pin) {
 const url=new URL(name,import.meta.url);
 const response=await fetch(url,{credentials:'same-origin',cache:'no-store',redirect:'error'});
 if(!response.ok)throw Error('runtime_source_unavailable');
 const bytes=new Uint8Array(await response.arrayBuffer());
 if(!bytes.length||bytes.length>131072||await digest(bytes)!==pin)throw Error('runtime_source_identity_mismatch');
 return bytes;
}
export function runtimeEvidenceFor(module) {
 return object(module)?associations.get(module)?.evidence??null:null;
}
export function isRuntimeEvidence(evidence,module) {
 const bound=object(evidence)?brands.get(evidence):null;
 return Boolean(bound&&associations.get(bound.module)?.evidence===evidence
  &&(module===undefined||module===bound.module));
}
export async function prepareVerifiedRuntime() {
 // The imported modules execute the same bytes whose hashes were checked.
 // Only bridge's exact reviewed observer specifier is changed to the verified
 // observer Blob URL. No refetch of a mutable URL occurs during module import.
 const [observerBytes,bridgeBytes,admissionBytes]=await Promise.all([
  source('observer.js',RUNTIME_PINS.observerSourceSha256),
  source('bridge.js',RUNTIME_PINS.bridgeSourceSha256),
  source('native-admission.js',RUNTIME_PINS.nativeAdmissionSourceSha256)
 ]);
 const urls=[];
 const blobURL=bytes=>{const url=URL.createObjectURL(new Blob([bytes],{type:'text/javascript'}));urls.push(url);return url;};
 let bridgeModule,admissionModule;
 try {
  const observerURL=blobURL(observerBytes),bridgeText=new TextDecoder('utf-8',{fatal:true}).decode(bridgeBytes);
  const specifier="import { observeZombies } from './observer.js';";
  if(bridgeText.split(specifier).length!==2)throw Error('runtime_import_graph_mismatch');
  const rewritten=bridgeText.replace(specifier,'import { observeZombies } from '+JSON.stringify(observerURL)+';');
  [bridgeModule,admissionModule]=await Promise.all([
   import(blobURL(rewritten)),import(blobURL(admissionBytes))
  ]);
  if(typeof bridgeModule.installBridge!=='function'||typeof admissionModule.createNativeResumeAdmission!=='function')
   throw Error('runtime_exports_unavailable');
 } finally {for(const url of urls)URL.revokeObjectURL(url);}
 let observed=null,invalid=false,finished=false;
 return Object.freeze({
  async observeWasmBytes(bytes,compiled,module) {
   // Called only after the original loader successfully instantiates these bytes.
   if(finished||invalid||observed||!object(module)||!(compiled instanceof WebAssembly.Module)) {invalid=true;return;}
   try {
    const copied=copyBytes(bytes);
    if(copied.length>33554432||await digest(copied)!==RUNTIME_PINS.patchedWasmSha256){invalid=true;return;}
    observed={module,compiled};
   }catch{invalid=true;}
  },
  activate(module,getConfig) {
   if(finished)return null;
   finished=true;
   if(invalid||!observed||observed.module!==module||!(observed.compiled instanceof WebAssembly.Module))return null;
   const evidence=Object.freeze({...RUNTIME_PINS,association:'instantiated-artifact-and-observers'});
   // Publish no native readers until bridge installation has succeeded.
   const bridge=bridgeModule.installBridge(module);
   const nativeAdmission=admissionModule.createNativeResumeAdmission(module,getConfig);
   associations.set(module,{evidence,compiled:observed.compiled});brands.set(evidence,{module});
   const guarded=(peer,member)=>isRuntimeEvidence(evidence,module)?nativeAdmission(peer,member):null;
   guarded.clear=()=>nativeAdmission.clear?.();
   return Object.freeze({bridge,evidence,nativeResumeAdmission:guarded});
  }
 });
}
