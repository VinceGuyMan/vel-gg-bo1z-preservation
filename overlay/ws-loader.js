// Import the same local adapter bytes whose exact reviewed hash is checked.
export const WS_ADAPTER=Object.freeze({protocol:'bo1z-original-packet-ws-v1',build:'bo1z-lan-lobby-v2',adapterSha256:'9a24f7e4cd9598d06a3c649401652c233eb7f5ad835b23f57e7f9590ec6e902d',wireVersion:1});
export async function createVerifiedWSManager(options){
 const response=await fetch(new URL('ws-transport.js',import.meta.url),{cache:'no-store',credentials:'same-origin',redirect:'error'});if(!response.ok)throw Error('Relay adapter unavailable');
 const bytes=new Uint8Array(await response.arrayBuffer());const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');if(!bytes.length||bytes.length>131072||digest!==WS_ADAPTER.adapterSha256)throw Error('Relay adapter identity mismatch');
 const url=URL.createObjectURL(new Blob([bytes],{type:'text/javascript'}));try{const module=await import(url);if(module.PROTOCOL!==WS_ADAPTER.protocol||module.BUILD!==WS_ADAPTER.build||typeof module.createWSRoomManager!=='function')throw Error('Relay adapter exports mismatch');return module.createWSRoomManager({...options,adapter:WS_ADAPTER});}finally{URL.revokeObjectURL(url);}
}
