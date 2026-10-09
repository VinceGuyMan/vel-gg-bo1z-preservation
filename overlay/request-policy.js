// Network policy only; never retries an allocation or SDP/recovery negotiation.
const IDEMPOTENT=new Set(['ready','start','native-started']);
export const isIdempotentAction=action=>IDEMPOTENT.has(action);
export const isTransientRequestError=error=>[429,502,503,504].includes(error?.status)||
  ['AbortError','TimeoutError','TypeError'].includes(error?.name);
export async function readJSONResponse(response) {
  try {
    const value=await response.json();
    if(value===null||typeof value!=='object'||Array.isArray(value))throw Error('Invalid JSON response shape');
    return value;
  }
  catch(error) {
    // Aborting after response headers still rejects the body read. Preserve the
    // transport failure for the bounded policy instead of calling it bad JSON.
    if(['AbortError','TimeoutError','TypeError'].includes(error?.name))throw error;
    const failure=Error('Server did not return JSON');
    // Preserve an explicit error status even if a proxy returned HTML. A known
    // transient HTTP failure stays bounded by the same endpoint/lease policy.
    if(response.ok===false&&Number.isInteger(response.status))failure.status=response.status;
    throw failure;
  }
}
function aborted(){return new DOMException('Request cancelled','AbortError');}
function sleep(ms,signal) {
  return new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(aborted());return;}
    const cancel=()=>{clearTimeout(timer);signal?.removeEventListener('abort',cancel);reject(aborted());};
    const timer=setTimeout(()=>{signal?.removeEventListener('abort',cancel);resolve();},ms);
    signal?.addEventListener('abort',cancel,{once:true});
  });
}
export async function retryIdempotentRequest(action,operation,options={}) {
  if(!isIdempotentAction(action))return operation(3000);
  const clock=options.clock??(()=>performance.now()),wait=options.wait??sleep,signal=options.signal;
  // One fixed caller lease bounds all attempts, even if a concurrent heartbeat
  // later extends membership. The caller may start another operation afterward.
  const deadline=options.getDeadline?.();
  if(!Number.isFinite(deadline))throw Error('Membership lease is unavailable');
  const remaining=()=>{
    if(signal?.aborted)throw aborted();
    const ms=deadline-clock();
    if(!Number.isFinite(ms)||ms<1){const error=Error('Membership lease expired');error.name='LeaseExpiredError';throw error;}
    return ms;
  };
  for(let attempt=1;attempt<=3;attempt++) {
    const timeout=Math.max(1,Math.min(3000,Math.floor(remaining())));
    try{const result=await operation(timeout);remaining();return result;}
    catch(error) {
      if(signal?.aborted||attempt===3||!isTransientRequestError(error))throw error;
      const delay=250*attempt;
      if(remaining()<=delay){const expired=Error('Membership lease expired before retry');expired.name='LeaseExpiredError';throw expired;}
      options.onRetry?.({attempt:attempt+1,delayMs:delay});
      await wait(delay,signal);
    }
  }
}
