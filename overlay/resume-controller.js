import {createRTCTransport} from './rtc-transport.js';

// Credentials are transient inputs, never compatibility or diagnostic fields.
export function validateIceSession(value, {nowMs=Date.now(), minValidityMs=20000}={}) {
  const keys=['schemaVersion','issuedAtMs','expiresAtMs','iceServers','iceTransportPolicy'];
  if(!value || typeof value!=='object' || Array.isArray(value) || Object.keys(value).sort().join()!==keys.sort().join()
    || value.schemaVersion!==1 || !Number.isSafeInteger(value.issuedAtMs) || !Number.isSafeInteger(value.expiresAtMs)
    || !Number.isFinite(nowMs) || !Number.isFinite(minValidityMs) || minValidityMs<0
    || value.issuedAtMs>nowMs+30000 || value.expiresAtMs-value.issuedAtMs<60000
    || value.expiresAtMs-value.issuedAtMs>3600000 || value.expiresAtMs-nowMs<minValidityMs
    || !['all','relay'].includes(value.iceTransportPolicy) || !Array.isArray(value.iceServers) || value.iceServers.length>8)
    throw Error('Invalid or expired ICE session');
  const iceServers=value.iceServers.map(server=>{
    if(!server || typeof server!=='object' || Array.isArray(server) || Object.keys(server).some(k=>!['urls','username','credential'].includes(k)))
      throw Error('Invalid ICE server schema');
    const urls=typeof server.urls==='string'?[server.urls]:server.urls;
    if(!Array.isArray(urls)||!urls.length||urls.length>8||urls.some(url=>{
      if(typeof url!=='string'||url.length>320)return true;
      const match=/^(stun|stuns|turn|turns):([A-Za-z0-9.-]{1,253}|\[[0-9A-Fa-f:]{2,45}\])(?::([0-9]{1,5}))?(?:\?transport=(udp|tcp))?$/.exec(url);
      return !match || match[3] && (Number(match[3])<1||Number(match[3])>65535) || match[1].startsWith('stun')&&match[4];
    }))throw Error('Invalid ICE server URL');
    const turn=urls.some(url=>url.startsWith('turn:')||url.startsWith('turns:'));
    if(turn && (typeof server.username!=='string'||!server.username.length||server.username.length>256
      || typeof server.credential!=='string'||!server.credential.length||server.credential.length>1024))throw Error('TURN credentials unavailable');
    if(!turn && (server.username!==undefined||server.credential!==undefined))throw Error('Unexpected ICE credentials');
    return {urls:[...urls],...(turn?{username:server.username,credential:server.credential}:{})};
  });
  if(value.iceTransportPolicy==='relay'&&!iceServers.some(s=>s.urls.some(url=>/^turns?:/.test(url))))throw Error('Relay ICE service unavailable');
  return {iceServers,iceTransportPolicy:value.iceTransportPolicy};
}

// Fixed diagnostic vocabulary; never export an exception containing peer,
// membership, routing, capability or opaque native-stamp data.
const REFUSALS = Object.freeze({
  'Verified native ACTIVE session and timeout headroom are unavailable':'native_admission_unavailable',
  'Native connection identity changed':'native_identity_changed',
  'Original native connection identity was not observed':'native_original_unobserved',
  'Match has not started':'match_not_started',
  'Transport resume attempts exhausted':'attempts_exhausted',
  'Native recovery window elapsed':'recovery_window_elapsed',
  'Replacement RTC edge failed':'replacement_rtc_failed',
  'RTC identity/build protocol rejected':'rtc_protocol_rejected'
});
export const resumeRefusalCode = reason => typeof reason==='string'&&Object.prototype.hasOwnProperty.call(REFUSALS,reason)?REFUSALS[reason]:'resume_other_failure';

// Same-page transport replacement only. This module never calls the engine,
// allocates a membership, persists a token, or issues a native command.
// The caller must supply verified, read-only native timeout headroom. Without
// that callback, initial transport works but recovery fails closed.
export function createResumeController(options) {
  const {member, metadata, api, getStartEpoch, getNativeAdmission, onPacket} = options;
  const edges = options.edges ?? new Map(), records = new Map();
  const clock = options.clock ?? (() => performance.now());
  let stopped = false;
  const emit = (type, peer, detail = {}) => options.onEvent?.({type, peer: peer?.id, ...detail});
  const snapshot = () => [...records.values()].map(r => ({peer: r.peer.id, generation: r.generation,
    attempts: r.attempts, phase: r.phase, deadlineRemainingMs: r.deadline ? Math.max(0, Math.round(r.deadline - clock())) : null,
    refusalReasonCode:r.refusalReasonCode ?? null,
    admission:r.admission ? {...r.admission,originalStampObserved:r.stamp!==null,
      observationAgeMs:Math.min(60000,Math.max(0,Math.round(clock()-r.admissionAt))),
      lastPositiveAgeMs:r.lastPositiveAt===null?null:Math.min(60000,Math.max(0,Math.round(clock()-r.lastPositiveAt)))} : null}));
  function read(r, needsBudget = false) {
    let value;
    try { value = getNativeAdmission?.(r.peer); }
    catch { r.admissionAt=clock();r.admission={active:false,budgetMs:null,stampMatchesOriginal:null,category:'callback_failed'};throw Error('Verified native ACTIVE session and timeout headroom are unavailable'); }
    const validStamp=typeof value?.stamp==='string'&&value.stamp.length>0&&value.stamp.length<=512;
    r.admissionAt=clock();
    const active=value?.active===true;
    r.admission={active,budgetMs:Number.isFinite(value?.budgetMs)?Math.max(0,Math.min(5000,Math.round(value.budgetMs))):null,
      stampMatchesOriginal:r.stamp!==null&&validStamp?r.stamp===value.stamp:null,
      category:!value?'unavailable':!active?'inactive_or_reader_reset':!validStamp?'invalid_stamp':
        r.stamp!==null&&r.stamp!==value.stamp?'stamp_changed':needsBudget&&(!Number.isFinite(value.budgetMs)||value.budgetMs<250)?'budget_unavailable':'eligible'};
    if(active&&validStamp)r.lastPositiveAt=r.admissionAt;
    if (!value || value.active !== true || typeof value.stamp !== 'string' || !value.stamp.length || value.stamp.length > 512 ||
        needsBudget && (!Number.isFinite(value.budgetMs) || value.budgetMs < 250)) throw Error('Verified native ACTIVE session and timeout headroom are unavailable');
    if (r.stamp !== null && r.stamp !== value.stamp) throw Error('Native connection identity changed');
    // Fresh native clocks may consume headroom faster than wall time. A later
    // admission can shorten the established bound; it can never extend it.
    if (needsBudget && r.deadline) r.deadline = Math.min(r.deadline, clock() + value.budgetMs);
    return value;
  }
  function detach(r, reason) {
    const old = edges.get(r.peer.id); edges.delete(r.peer.id);
    old?.close(reason, false); // No leave control; this is not room membership departure.
  }
  function terminal(r, reason) {
    if (r.phase === 'failed') return;
    r.refusalReasonCode=resumeRefusalCode(reason);
    r.phase = 'failed'; r.deadline = 0; r.pending = false;
    detach(r, reason); emit('resume-refused', r.peer, {reason:r.refusalReasonCode!=='resume_other_failure'?reason:'Transport recovery refused',reasonCode:r.refusalReasonCode});
  }
  function beginBound(r) {
    if (!getStartEpoch?.()) throw Error('Match has not started');
    if (r.attempts >= 2) throw Error('Transport resume attempts exhausted');
    const value = read(r, true);
    if (r.stamp === null) throw Error('Original native connection identity was not observed');
    if (!r.deadline) r.deadline = clock() + Math.min(value.budgetMs, 5000);
    if (clock() >= r.deadline) throw Error('Native recovery window elapsed');
    r.phase = 'recovering'; emit('resume-pending', r.peer);
  }
  function observeHealthyNative(r) {
    // Background DOM timers can be throttled despite native RTC traffic. Both
    // timer and accepted packets refresh the same fail-closed reader; neither
    // path overwrites the first native stamp or creates a recovery deadline.
    try { const value=read(r);if(r.stamp===null)r.stamp=value.stamp; }
    catch { /* A working edge is preserved; no recovery is admitted. */ }
  }
  async function make(r) {
    if(r.creating)return r.creating;
    r.creating=createEdge(r);
    try{return await r.creating;}finally{r.creating=null;}
  }
  async function createEdge(r) {
    const generation = r.generation;
    let remaining = r.deadline ? Math.floor(r.deadline - clock()) : 15000;
    let network=options.network ?? {};
    if(options.getNetworkOptions) {
      let session;
      let timer;
      try {session=await Promise.race([
        Promise.resolve().then(()=>options.getNetworkOptions({peer:r.peer,generation,budgetMs:remaining})),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('ICE session deadline')),Math.max(1,Math.min(3000,remaining)));})]);}
      catch {throw Error('ICE session unavailable');}
      finally {clearTimeout(timer);}
      if(stopped||records.get(r.peer.id)!==r||r.generation!==generation||r.phase==='failed')throw Error('ICE edge no longer authorized');
      if(r.deadline) {read(r,true);remaining=Math.floor(r.deadline-clock());}
      if(remaining<1)throw Error('Native recovery window elapsed');
      network=validateIceSession(session,{minValidityMs:remaining+5000});
    }
    const edge = createRTCTransport({role: member.role, local: member.identity, remote: r.peer.identity,
      metadata, ...network, generation, iceGatheringTimeoutMs: remaining,
      async onPacket(packet) {
        if (stopped || edges.get(r.peer.id) !== edge || r.generation !== generation || r.phase === 'failed') return;
        if (r.deadline) {
          try { read(r, true); if (clock() >= r.deadline) throw Error('Native recovery window elapsed'); }
          catch (error) { terminal(r, error.message); return; }
        }
        const accepted = await onPacket?.(packet);
        if (accepted === false || stopped || edges.get(r.peer.id) !== edge || r.generation !== generation) return;
        if (!r.deadline && r.phase==='connected' && getStartEpoch?.()) observeHealthyNative(r);
        if (r.deadline && edge.getStats().ready) {
          r.deadline = 0; r.pending = false; r.phase = 'connected';
          emit('transport-resumed', r.peer, {generation, nativeGameplayProven: false});
        }
      },
      onEvent(event) {
        if (stopped || edges.get(r.peer.id) !== edge || r.generation !== generation || r.phase === 'failed') return;
        emit('rtc-' + event.type, r.peer, {generation, state: event.state});
        if (event.type === 'ready') {
          try {
            if (r.deadline) read(r, true);
            else { try { r.stamp = read(r).stamp; } catch { /* Initial room transport may precede engine. */ } }
            r.phase = r.deadline ? 'transport-ready-awaiting-native-packet' : 'connected';
            emit('ready', r.peer, {generation});
          } catch (error) { terminal(r, error.message); }
        }
        if (event.type === 'protocol-error') terminal(r, 'RTC identity/build protocol rejected');
        else if (event.type === 'disconnect' || event.type === 'closed') {
          if (r.deadline) { if (event.type === 'closed') terminal(r, 'Replacement RTC edge failed'); }
          else void request(r.peer.id).catch(error => terminal(r, error.message));
        }
      }});
    edges.set(r.peer.id, edge); return edge;
  }
  async function publishOffer(r) {
    const edge = edges.get(r.peer.id) ?? await make(r), generation = r.generation;
    const bundle = await edge.createOffer();
    if (!stopped && edges.get(r.peer.id) === edge && r.generation === generation)
      await api('signal', {target: r.peer.id, epoch: r.peer.epoch, bundle});
  }
  async function addPeer(peer) {
    if (stopped || peer.id === member.id) return;
    let r = records.get(peer.id);
    if (r) { if (r.peer.epoch !== peer.epoch) throw Error('Membership changed; native resume is forbidden'); return; }
    r = {peer, generation: 1, attempts: 0, deadline: 0, pending: false, stamp: null, phase: 'connecting',
      admission:null,admissionAt:0,lastPositiveAt:null,refusalReasonCode:null};
    records.set(peer.id, r); await make(r);
    if (member.role === 'host') await publishOffer(r);
  }
  async function request(peerId) {
    const r = records.get(peerId);
    if (stopped || !r || r.pending || r.phase === 'failed') return false;
    try {
      // Capture the established native identity before replacing any edge.
      // Initial RTC opens before native connect, so a post-start observation is required.
      if (r.stamp === null) r.stamp = read(r, true).stamp;
      beginBound(r); r.pending = true;
      if (member.role === 'host') {
        const event = await api('resume', {target: r.peer.id, epoch: r.peer.epoch});
        await handle(event);
      } else {
        try { await api('resume-request', {generation: r.generation}); }
        catch (error) { if (error.message !== 'stale_resume_request') throw error; }
      }
      return true;
    } catch (error) { terminal(r, String(error.message ?? error)); return false; }
  }
  async function handle(event) {
    if (stopped) return;
    if (event.type === 'resume-request') {
      if (member.role !== 'host' || event.startEpoch !== getStartEpoch?.()) throw Error('Invalid resume authority');
      const r = records.get(event.member?.id);
      if (!r || r.peer.epoch !== event.member.epoch) throw Error('Stale resume membership');
      if (event.generation !== r.generation) { emit('stale-resume-request-ignored', r.peer); return; }
      return request(r.peer.id);
    }
    if (event.type === 'resume-authorized') {
      if (event.startEpoch !== getStartEpoch?.()) throw Error('Stale match resume authorization');
      const peerId = member.role === 'host' ? event.member?.id : 'host', r = records.get(peerId);
      if (!r || event.member?.epoch !== (member.role === 'host' ? r.peer.epoch : member.epoch)) throw Error('Stale resume membership');
      if (r.phase === 'failed') return;
      if (event.generation <= r.generation) return; // Duplicate private event after host API response.
      if (event.generation !== r.generation + 1) throw Error('Unexpected resume generation');
      try {
        if (r.stamp === null) r.stamp = read(r, true).stamp;
        beginBound(r); r.attempts++; r.generation = event.generation; r.pending = true;
        detach(r, 'Replacing RTC transport'); await make(r);
        if (member.role === 'host') await publishOffer(r);
      } catch (error) { terminal(r, String(error.message ?? error)); }
      return;
    }
    if (event.type !== 'signal') return;
    if (event.epoch !== member.epoch) throw Error('Stale signal recipient membership');
    const r = records.get(event.from);
    if (!r || r.peer.epoch !== event.fromEpoch) throw Error('Unknown signal sender membership');
    if (event.bundle.generation !== r.generation) { emit('stale-signal-ignored', r.peer); return; }
    if (r.phase === 'failed') return;
    const edge = edges.get(r.peer.id);
    if (member.role === 'guest') {
      const bundle = await edge.acceptOffer(event.bundle);
      if (!stopped && edges.get(r.peer.id) === edge) await api('signal', {target: r.peer.id, epoch: r.peer.epoch, bundle});
    } else await edge.acceptAnswer(event.bundle);
  }
  const timer = setInterval(() => {
    for (const r of records.values()) {
      if (r.deadline) {
        try { read(r, true); if (clock() >= r.deadline) throw Error('Native recovery window elapsed'); }
        catch (error) { terminal(r, error.message); }
      } else if (getStartEpoch?.() && r.phase === 'connected') {
        // Pin only the first observed native session, never overwrite it on reconnect.
        // Continue sampling healthy peers so admission's advancing-clock proof
        // stays fresh. Unavailable/changed state forbids later recovery without
        // tearing down an otherwise working transport or replacing the stamp.
        observeHealthyNative(r);
      }
    }
  }, 100);
  function removePeer(id) { const r = records.get(id); if (r) { records.delete(id); detach(r, 'Member left'); } }
  function closeAll(reason = 'Room closed') { stopped = true; clearInterval(timer); for (const r of records.values()) detach(r, reason); records.clear(); }
  return {addPeer, handle, request, removePeer, closeAll, snapshot, edges};
}
