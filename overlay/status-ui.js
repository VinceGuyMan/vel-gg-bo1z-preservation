import {serializeReport} from './status.js';
// Optional integration seam; no install side effect on module import.
export function installStatusDownload({collector, panel, documentObject=document, testLabel='lan-test'}={}) {
 if(!collector?.report||!panel?.append)throw Error('status_ui_configuration_unavailable');
 const single=documentObject.createElement('button'),windowButton=documentObject.createElement('button'),notice=documentObject.createElement('p');
 single.type=windowButton.type='button';single.textContent='Save local status';windowButton.textContent='Save 10-second status';
 notice.textContent='Downloads a local report. Nothing uploads automatically.';
 let busy=false,closed=false,controller=null;
 const save=async durationMs=>{
  if(busy||closed)return;
  busy=true;single.disabled=windowButton.disabled=true;controller=new AbortController();
  try {
   const report=await collector.report({testLabel,durationMs,signal:controller.signal});
   if(closed)return;
   const blob=new Blob([serializeReport(report)],{type:'application/json'}),url=URL.createObjectURL(blob);
   const link=documentObject.createElement('a');link.href=url;link.download='bo1z-'+testLabel+'-status.json';
   link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
   const paths=report.samples?.at(-1)?.connections?.map(c=>c.networkPath?.route)??[];
   const route=paths.length&&paths.every(v=>v==='relay')?' Relay path recorded.':paths.length&&paths.every(v=>v==='direct')?' Direct path recorded.':' Connection path unavailable or mixed.';
   notice.textContent='Local report downloaded.'+route;
  }catch {notice.textContent='Status unavailable; save the visible error and both launcher messages separately.';}
  finally{busy=false;if(!closed)single.disabled=windowButton.disabled=false;}
 };
 single.addEventListener('click',()=>void save(0));windowButton.addEventListener('click',()=>void save(10000));
 const stop=()=>controller?.abort();documentObject.defaultView?.addEventListener('pagehide',stop);
 const visibility=()=>{if(documentObject.visibilityState!=='visible')stop();};
 documentObject.addEventListener('visibilitychange',visibility);
 panel.append(single,windowButton,notice);
 return Object.freeze({close(){closed=true;stop();documentObject.defaultView?.removeEventListener('pagehide',stop);documentObject.removeEventListener('visibilitychange',visibility);single.remove();windowButton.remove();notice.remove();}});
}
