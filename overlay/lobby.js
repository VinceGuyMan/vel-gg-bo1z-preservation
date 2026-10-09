import {createVerifiedWSManager} from './ws-loader.js';
import {validatePeerMetadata} from './peer-schema.js';
import {createResumeController} from './resume-controller.js';
import {runtimeEvidenceFor} from './runtime-attestation.js';
import {createStatusCollector,readPrediction,browserEnvironment} from './status.js';
import {installStatusDownload} from './status-ui.js';
import {observeSettledStart} from './start-gate.js';
import {readJSONResponse,retryIdempotentRequest,isIdempotentAction} from './request-policy.js';

// Only the explicit Five experiment receives this overlay. Archive controls own
// downloading, rendering, intro, sound activation and pointer lock.
const query = new URLSearchParams(location.search);
if (query.get('coop') === '1' && location.pathname.replace(/\/$/, '') === '/bo1z/five') installLobby();

function installLobby() {
  const FIELDS = ['overlayBuildId', 'protocolVersion', 'bridgeAbiVersion', 'patchSchemaRevision', 'baseWasmSha256',
    'patchedWasmSha256', 'patchManifestSha256', 'shellManifestSha256', 'mapManifestSha256',
    'mapContentSha256', 'mapSlug', 'mode', 'maxPlayers'];
  const DIGESTS = FIELDS.filter(name => name.endsWith('Sha256'));
  const state = { phase: 'idle', room: null, member: null, metadata: null, capability: null,
    service: '', transport:'webrtc',cursor: 0, readySent: false, hookReached: false, started: false,
    prepared: false, nativeConnectIssued: false, restartIssued: false, nativeSettled: false, nativeStartedSent: false,
    restartBaseline: null, settleSample: null, stopped: false, errors: [], events: [], launched: false };
  const edges = new Map(), controllers = new Set(), timers = new Set();
  let resumeManager = null;
  const recovery = new Map();
  let network = {iceServers: [], iceTransportPolicy: 'all'}, busy = false, tickBusy = false;
  const previousSend = globalThis.__coopSend, previousHook = globalThis.__coopBeforeRun;
  const el = (tag, text, className) => {
    const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
    if (className) node.className = className; return node;
  };
  const button = (text, id) => { const node = el('button', text); node.type = 'button'; node.id = id; return node; };
  const panel = el('section', undefined, 'coop-panel'); panel.id = 'coop-lobby';
  panel.setAttribute('aria-label', 'Experimental co-op lobby');
  const heading = el('div', undefined, 'coop-heading');
  const title = el('h2', 'Co-op experiment');
  const collapse = button('Minimize', 'coop-collapse'); heading.append(title, collapse);
  const note = el('p', 'Five · Classic. Prepare Five on this computer, then click Ready when loaded. The host starts when everyone is ready. Other maps and internet relay play have not been validated.', 'coop-note');
  const service = el('input'); service.id = 'coop-service'; service.type = 'url'; service.value = query.get('signaling') || 'http://127.0.0.1:8768';
  service.autocomplete = 'off'; service.spellcheck = false;
  const code = el('input'); code.id = 'coop-code'; code.maxLength = 6; code.placeholder = 'Room code'; code.autocomplete = 'off';
  const invite = el('input'); invite.id = 'coop-invite'; invite.type = 'password'; invite.placeholder = 'Optional invitation'; invite.autocomplete = 'off';
  const label = (text, input) => { const node = el('label', text); node.append(input); return node; };
  const transportChoice=el('select');transportChoice.id='coop-transport';
  for(const[value,text]of[['webrtc','WebRTC (default)'],['websocket-relay','Experimental WebSocket relay']]){const option=el('option',text);option.value=value;transportChoice.append(option);}
  const relayNote=el('p','Choose the same connection type as your host. The relay uses TCP through the host’s server; its tunnel provider can read relay traffic. Relay disconnects end that connection; no automatic fallback or reconnect.', 'coop-note');
  const form = el('div', undefined, 'coop-form');
  form.append(label('Connection type',transportChoice),label('Signaling server', service), label('Join room', code), label('Invitation', invite));
  const actions = el('div', undefined, 'coop-actions');
  const host = button('Host room', 'coop-host'), join = button('Join room', 'coop-join'); actions.append(host, join);
  const roomInfo = el('p', '', 'coop-room'); roomInfo.id = 'coop-room-info';
  const inviteInfo = el('details', undefined, 'coop-invitation'); inviteInfo.hidden = true;
  const invitationText = el('code', ''); inviteInfo.append(el('summary', 'Invitation for your friends'), invitationText);
  const status = el('p', 'Host or join a room to prepare Five on this computer.', 'coop-status'); status.id = 'coop-status';
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const members = el('ul', undefined, 'coop-members'); members.id = 'coop-members';
  const stats = el('p', '', 'coop-stats'); stats.id = 'coop-stats';
  const roomActions = el('div', undefined, 'coop-actions');
  const guestReady = button('Ready', 'coop-ready');
  const start = button('Start match', 'coop-start'), leave = button('Leave room', 'coop-leave'), reload = button('Reload for a new session', 'coop-reload');
  guestReady.hidden = true; start.hidden = true; leave.hidden = true; reload.hidden = true; roomActions.append(guestReady, start, leave, reload);
  panel.append(heading, note, form, relayNote,actions, roomInfo, inviteInfo, status, members, stats, roomActions);
  const compact = button('Co-op', 'coop-toggle'); compact.className = 'coop-toggle'; compact.hidden = true;
  document.body.append(panel, compact);
  // Archive keyboard handling captures on document. Stop UI key events at
  // window first, while preserving browser defaults (typing/Tab/button Enter).
  // Events outside these widgets continue to the original gameplay handlers.
  const protectUIKeys = event => {
    if (event.target?.closest?.('#coop-lobby, #coop-toggle')) event.stopPropagation();
  };
  window.addEventListener('keydown', protectUIKeys, {capture: true});
  window.addEventListener('keyup', protectUIKeys, {capture: true});
  for (const widget of [panel, compact]) {
    for (const name of ['click', 'mousedown', 'mouseup']) {
      widget.addEventListener(name, event => event.stopPropagation());
    }
  }
  function collapsed(value) { panel.hidden = value; compact.hidden = !value; }
  collapse.onclick = () => collapsed(true); compact.onclick = () => collapsed(false);
  reload.onclick = () => location.reload();
  const eventLog = (type, detail = {}) => {
    state.events.push({type, at: Math.round(performance.now()), ...detail});
    if (state.events.length > 80) state.events.shift();
  };
  function message(text) {
    const unresolved = [...recovery.values()].find(value => value.phase === 'refused')
      ?? [...recovery.values()].find(value => value.phase === 'recovering');
    status.textContent = state.phase === 'failed' || !unresolved ? text : unresolved.message;
  }
  function schedule(fn, ms, interval = false) {
    const id = interval ? setInterval(fn, ms) : setTimeout(() => { timers.delete(id); fn(); }, ms);
    timers.add(id); return id;
  }
  function failure(error) {
    if (state.stopped) return;
    const text = String(error?.message ?? error).slice(0, 300);
    state.errors.push(text); if (state.errors.length > 20) state.errors.shift();
    message('Connection stopped: ' + text + '. Reload for a new session.');
    state.phase = 'failed'; collapsed(false);
    void stop(true);
  }
  async function fetchJSON(url, options = {}, timeout = 20000) {
    const controller = new AbortController(); controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store'});
      const result=await readJSONResponse(response);
      if (!response.ok) { const error = Error(String(result.error ?? result.code ?? ('HTTP ' + response.status))); error.status = response.status; throw error; }
      return result;
    } finally { clearTimeout(timer); controllers.delete(controller); }
  }
  async function api(action, body, authenticated = true, method = 'POST') {
    if(method==='POST'&&['ready','start'].includes(action))body={...(body??{}),metadata:state.metadata,transport:state.transport};
    const suffix = state.room ? '/' + state.room.code + (action ? '/' + action : '') : '';
    const headers = {'Content-Type': 'application/json'};
    if (authenticated) headers.Authorization = 'Bearer ' + state.capability;
    const url=state.service + '/coop/api/rooms' + suffix, request={
      method, headers, ...(method === 'POST' ? {body: JSON.stringify(body ?? {})} : {})
    };
    if(!authenticated||method!=='POST'||!isIdempotentAction(action))return fetchJSON(url,request,authenticated?3000:20000);
    const retryController=new AbortController();controllers.add(retryController);
    try{return await retryIdempotentRequest(action,timeout=>fetchJSON(url,request,timeout),{
      signal:retryController.signal,getDeadline:()=>state.lastHeartbeat+state.leaseMs,
      onRetry:event=>eventLog('idempotent-request-retry',{action,...event})
    });}finally{controllers.delete(retryController);}
  }
  function updateMember(member) {
    if (!member || !state.room) return;
    if (state.member?.role === 'guest' && member.role !== 'host' && member.id !== state.member.id) return;
    const index = state.room.members.findIndex(item => item.id === member.id);
    if (index < 0) state.room.members.push(member); else state.room.members[index] = member;
    if (state.member?.id === member.id) state.member = member;
  }
  function edgesReady() {
    if (!state.room || !state.member) return false;
    const peers = state.room.members.filter(item => item.id !== state.member.id
      && (state.member.role === 'host' || item.role === 'host'));
    return peers.length > 0 && peers.every(peer => edges.get(peer.id)?.getStats().ready);
  }
  function localWarm(native = globalThis.__coopBridge?.snapshot()) {
    return state.hookReached && Boolean(globalThis.__coopBridge)
      && native?.serverStates?.[0] === 5 && ['ready', 'playing'].includes(globalThis.five?.screen);
  }
  function canStart() {
    return !busy && !state.stopped && !state.started && state.member?.role === 'host'
      && state.room?.members.length >= 2 && edgesReady()
      && state.room.members.every(member => member.engineReady);
  }
  function render() {
    transportChoice.disabled=busy||Boolean(state.member)||state.stopped;
    host.disabled = join.disabled = busy || Boolean(state.member) || state.stopped;
    start.hidden = state.member?.role !== 'host'; start.disabled = !canStart();
    guestReady.hidden = state.member?.role !== 'guest' || state.readySent || state.started || state.stopped;
    guestReady.disabled = busy || !localWarm() || !edgesReady();
    leave.hidden = !state.member || state.stopped; reload.hidden = !state.stopped;
    form.hidden = Boolean(state.member); actions.hidden = Boolean(state.member);
    roomInfo.textContent = state.room ? 'Room ' + state.room.code + ' · ' + (state.member?.role === 'host' ? 'Hosting' : 'Guest') + ' · ' + (state.transport==='websocket-relay'?'WebSocket relay (experimental)':'WebRTC') : '';
    members.replaceChildren();
    for (const member of state.room?.members ?? []) {
      const isSelf = member.id === state.member?.id;
      const edge = edges.get(member.id)?.getStats();
      const recovering = recovery.get(member.id);
      const connection = recovering?.phase === 'refused' ? 'connection unavailable' : recovering?.phase === 'recovering' ? 'reconnecting' : isSelf ? 'this browser' : edge?.ready ? 'connected' : edge?.connectionState ?? 'connecting';
      members.append(el('li', (member.role === 'host' ? 'Host' : 'Player ' + member.identity.ip.split('.').at(-1))
        + ' · ' + connection + ' · ' + (member.engineReady ? 'ready' : 'preparing')));
    }
    const values = [...edges.values()].map(edge => edge.getStats());
    stats.textContent = values.length ? values.length + ' peer link(s) · ' + values.reduce((n, v) => n + v.sentDatagrams, 0)
      + ' packets sent · ' + values.reduce((n, v) => n + v.receivedDatagrams, 0) + ' received'
      + ' · ' + values.reduce((n, v) => n + v.droppedIncoming + v.droppedOutgoing, 0) + ' dropped' : '';
  }
  async function offer(peer) { await resumeManager.addPeer(peer); }
  async function handle(event) {
    eventLog(event.type);
    if (event.type === 'member-joined') {
      updateMember(event.member);
      if (state.member.role === 'host') await offer(event.member);
    } else if (event.type === 'member-ready') updateMember(event.member);
    else if (event.type === 'member-left') {
      // Remove membership before close so deliberate cleanup is not a transport failure.
      state.room.members = state.room.members.filter(member => member.id !== event.member.id);
      resumeManager.removePeer(event.member.id); recovery.delete(event.member.id);
      if (state.started) message('A player left. Remaining native players continue where the original game permits.');
    } else if (['signal', 'resume-request', 'resume-authorized'].includes(event.type)) {
      await resumeManager.handle(event);
    } else if (event.type === 'match-start') {
      if (state.started) return;
      if (!edgesReady() || !state.readySent || !state.hookReached) throw Error('Match started before local engine/transport readiness');
      if(event.transport!==state.transport||JSON.stringify(validatePeerMetadata(event.metadata))!==JSON.stringify(state.metadata))throw Error('Match identity or connection type changed');
      state.started = true; state.phase = 'joining'; state.room.startEpoch = event.startEpoch;
      if (Array.isArray(event.members)) state.room.members = event.members.filter(member =>
        state.member.role === 'host' || member.role === 'host' || member.id === state.member.id);
      message(state.member.role === 'guest' ? 'Joining the original host engine…' : 'Waiting for native player connections…');
      state.joinDeadline = performance.now() + 120000;
      if (state.member.role === 'guest' && !state.nativeConnectIssued) {
        if (!state.prepared || !globalThis.__coopBridge) throw Error('Guest has not prepared the original game');
        globalThis.__coopBridge.command('connect 10.0.0.1:3074');
        state.nativeConnectIssued = true; eventLog('native-connect');
      }
    } else if (event.type === 'native-started') {
      if (!state.started || event.startEpoch !== state.room.startEpoch || !Array.isArray(event.members)) throw Error('Stale native start confirmation');
      const identity = members => JSON.stringify(members.map(member=>[member.id,member.epoch,member.identity]));
      const present=event.members.filter(member=>state.member.role==='host'||member.role==='host'||member.id===state.member.id);
      if(identity(present)!==identity(state.room.members))throw Error('Native start membership changed');
      state.nativeSettled=true; eventLog('native-start-settled');
    } else if (event.type === 'room-closed') failure(Error('Host closed the room'));
    render();
  }
  const terminalServiceError = error => error.status && ![429, 502, 503, 504].includes(error.status);
  let heartbeatBusy = false;
  async function heartbeat() {
    if (heartbeatBusy || state.stopped) return;
    heartbeatBusy = true;
    try { await api('heartbeat', {}); state.lastHeartbeat = performance.now(); }
    catch (error) {
      if (terminalServiceError(error)) failure(error);
      else eventLog('heartbeat-retry', {reason: String(error.message).slice(0, 120)});
    } finally { heartbeatBusy = false; }
  }
  async function poll() {
    let retry = 0;
    while (!state.stopped) {
      try {
        // Long polling uses its own bound; heartbeat is a separate lease renewal.
        const result = await api('events?after=' + state.cursor + '&wait=1', null, true, 'GET');
        if (state.stopped) return;
        if (!Array.isArray(result.events) || result.events.length > 64) throw Error('Invalid signaling event batch');
        for (const event of result.events) { if (state.stopped) return; await handle(event); }
        state.cursor = result.cursor;
        if (result.closed) throw Error('Room closed');
        retry = 0;
      } catch (error) {
        if (state.stopped) return;
        if (terminalServiceError(error) || ![429,502,503,504].includes(error.status) && !['TypeError', 'AbortError', 'TimeoutError'].includes(error.name)) { failure(error); return; }
        retry++;
        if (retry > 3) { failure(Error('Signaling retry limit exceeded; membership cannot be verified')); return; }
        eventLog('signaling-retry', {attempt: retry});
        await new Promise(resolve => schedule(resolve, Math.min(4000, 500 * 2 ** retry)));
      }
    }
  }
  async function tick() {
    if (tickBusy || state.stopped || !state.member) return;
    tickBusy = true;
    try {
      if (performance.now() - state.lastHeartbeat >= state.leaseMs) throw Error('Signaling membership lease can no longer be guaranteed');
      const screen = globalThis.five?.screen;
      if (screen === 'error') throw Error(globalThis.five?.error ?? 'Original engine reported an error');
      const native = globalThis.__coopBridge?.snapshot();
      if (!state.started) {
        // Every browser must preload the original SP map. Guest readiness also
        // requires its explicit activation gesture and a verified host edge.
        const ready = localWarm(native) && (state.member.role === 'host'
          || state.prepared && screen === 'playing' && edgesReady());
        if (ready !== state.readySent) {
          const result = await api('ready', {ready}); updateMember(result.member); state.readySent = ready;
          if (ready) message(state.member.role === 'host'
            ? 'Host game loaded. Start when every player is ready.' : 'Ready. Waiting for the host to start.');
        }
        if (state.member.role === 'guest' && localWarm(native) && !state.readySent) {
          message(state.prepared
            ? 'Click Ready to allow the game’s mouse and sound controls.'
            : 'Five loaded. Click Ready to prepare this player.');
        }
      }
      if (state.started && state.member.role === 'host' && !state.restartIssued) {
        const guests = state.room.members.filter(member => member.role === 'guest');
        const allNative = native?.serverStates?.[0] === 5 && guests.every(guest => native.serverPeers?.some(peer =>
          peer.state === 5 && peer.address?.slice(4, 8).join('.') === guest.identity.ip));
        if (allNative) {
          state.restartBaseline={snapshotNum:native.frameState?.currentSnapshotNum,serverTime:native.serverTime};
          globalThis.__coopBridge.command('map_restart'); state.restartIssued = true; state.phase = 'match';
          message('Original co-op map start requested. Use the game’s Click to start control.');
          eventLog('native-map-restart');
        } else if (performance.now() > state.joinDeadline) throw Error('Native player connections did not become active within two minutes');
      }
      if(state.started&&state.member.role==='host'&&state.restartIssued&&!state.nativeStartedSent) {
        const observation=observeSettledStart(native,state.room.members,state.restartBaseline,state.settleSample);
        state.settleSample=observation?.sample??null;
        if(observation?.settled) {
          await api('native-started',{startEpoch:state.room.startEpoch}); state.nativeStartedSent=true;
        }
      }
      if (state.started && state.member.role === 'guest' && native?.localConnectionState === 10) {
        state.phase = 'match'; message(edgesReady() ? 'Connected to the host. Use the game’s Click to start control.' : 'Native client is still active; player transport is interrupted.');
      }
      if (screen === 'playing' && state.phase === 'match' && ![...recovery.values()].some(value => value.phase !== 'connected') && !state.didAutoCollapse) { state.didAutoCollapse = true; collapsed(true); }
      render();
    } catch (error) { failure(error); }
    finally { tickBusy = false; }
  }
  async function loadArchive() {
    const deadline = performance.now() + 120000;
    await new Promise((resolve, reject) => {
      const check = () => {
        if (state.stopped) { reject(Error('Room ended before game load')); return; }
        const play = document.getElementById('play');
        if (globalThis.five?.screen === 'error') { reject(Error('Archive player is unavailable')); return; }
        if (play && !play.disabled && !play.hidden && globalThis.five?.screen === 'landing') {
          for (const box of document.querySelectorAll('input[data-mod]')) { box.checked = false; box.disabled = true; }
          state.launched = true; play.click(); resolve();
        } else if (performance.now() > deadline) reject(Error('Archive player did not finish inspecting local files'));
        else schedule(check, 200);
      }; check();
    });
  }
  async function begin(role) {
    if (busy || state.member || state.stopped) return;
    busy = true; state.phase = 'connecting'; message('Connecting to signaling server…'); render();
    try {
      const url = new URL(service.value.trim());
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || !['', '/'].includes(url.pathname)
        || url.search || url.hash) throw Error('Use an HTTP or HTTPS server origin, without a path or credentials');
      state.service = url.origin;
      if(!['webrtc','websocket-relay'].includes(transportChoice.value))throw Error('Invalid connection type');
      state.transport=transportChoice.value;
      const metadata = await fetchJSON('/bo1z/coop/peer-metadata.json');
      state.metadata = validatePeerMetadata(metadata);
      try {
        const config = await fetchJSON('/bo1z/coop/network-config.json');
        if (config.iceServers !== undefined && !Array.isArray(config.iceServers)) throw Error('Invalid ICE server configuration');
        const policy = config.iceTransportPolicy ?? (config.relayOnly ? 'relay' : 'all');
        if (!['all', 'relay'].includes(policy)) throw Error('Invalid ICE transport policy');
        network = {iceServers: config.iceServers ?? [], iceTransportPolicy: policy};
      } catch (error) {
        // A missing seam means direct/local ICE only; configuration errors are visible.
        if (!/HTTP 404|Resource was not captured|Server did not return JSON/.test(error.message)) throw error;
        network = {iceServers: [], iceTransportPolicy: 'all'};
      }
      let response;
      if (role === 'host') response = await api('', {metadata: state.metadata,transport:state.transport}, false);
      else {
        const value = code.value.trim().toUpperCase(); if (!/^[A-Z2-9]{6}$/.test(value)) throw Error('Enter the six-character room code');
        state.room = {code: value};
        response = await api('join', {metadata: state.metadata,transport:state.transport, ...(invite.value.trim() ? {invite: invite.value.trim()} : {})}, false);
      }
      state.lastHeartbeat = performance.now(); state.leaseMs = Number(response.leaseSeconds) * 1000;
      if (!Number.isFinite(state.leaseMs) || state.leaseMs < 1000 || state.leaseMs > 60000) throw Error('Invalid membership lease');
      if(response.room?.transport!==state.transport||JSON.stringify(validatePeerMetadata(response.room.metadata))!==JSON.stringify(state.metadata))throw Error('Room connection type or build identity changed');
      state.room = response.room; state.member = response.member; state.capability = response.capability; state.cursor = response.cursor;
      if(state.transport==='websocket-relay') {
        resumeManager=await createVerifiedWSManager({base:state.service,room:state.room,member:state.member,capability:state.capability,metadata:state.metadata,edges,api,validateMetadata:validatePeerMetadata,
          onPacket:packet=>!state.stopped&&(globalThis.__coopBridge?.receive(packet)??false),
          onEvent:event=>{eventLog(event.type,{...(event.peer?{peer:event.peer}:{})});if(state.stopped)return;
            if(event.type==='transport-terminal'){failure(Error('WebSocket relay disconnected. This connection cannot be restored.'));return;}
            if(event.type==='peer-terminal'){recovery.set(event.peer,{phase:'refused',message:'A relay player disconnected. That connection cannot be restored.'});collapsed(false);message('A relay player disconnected.');}
            if(event.type==='ready'){void tick();render();}
          }});
        for(const peer of state.room.members)if(peer.id!==state.member.id&&(state.member.role==='host'||peer.role==='host'))await resumeManager.addPeer(peer);
        await resumeManager.connect();
      }
      else resumeManager = createResumeController({member: state.member, metadata: state.metadata, network, edges, api,
        getNetworkOptions: async () => api('ice', {}),
        getStartEpoch: () => state.nativeSettled ? state.room.startEpoch : 0,
        // Main engine integration must provide verified read-only native timeouts,
        // last-packet ages and session stamp. No callback means fail-closed retry.
        getNativeAdmission: peer => globalThis.__coopNativeResumeAdmission?.(peer, state.member),
        onPacket: packet => !state.stopped && (globalThis.__coopBridge?.receive(packet) ?? false),
        onEvent: event => {
          eventLog(event.type, {peer: event.peer, ...(event.type==='resume-refused'?{reasonCode:event.reasonCode}:{})});
          if (event.type === 'ready') { void tick(); render(); }
          if (event.type === 'resume-pending') { recovery.set(event.peer,{phase:'recovering',message:'Player connection interrupted. Reconnecting…'}); collapsed(false); message('Player connection interrupted. Reconnecting…'); }
          if (event.type === 'resume-refused') { recovery.set(event.peer,{phase:'refused',reasonCode:event.reasonCode,message:'A player connection could not be restored. Use Leave room to start a new session.'}); collapsed(false); message('A player connection could not be restored.'); }
          if (event.type === 'transport-resumed') { recovery.delete(event.peer); message('Player connection restored.'); }
          render();
        }});
      if (state.member.role === 'guest') await resumeManager.addPeer(state.room.members.find(item => item.role === 'host'));
      globalThis.__coopConfig = {role: role === 'host' ? 'host' : 'client', ip: state.member.identity.ip, port: 3074, deferJoin: role === 'guest'};
      if (response.invite) { invitationText.textContent = response.invite; inviteInfo.hidden = false; }
      state.phase = 'preparing'; message('Preparing saved game files and engine…');
      schedule(() => { void heartbeat(); }, 12000, true);
      schedule(() => { void tick(); }, 1000, true);
      void poll(); await loadArchive();
    } catch (error) {
      if (state.member) failure(error);
      else { state.room = null; state.phase = 'idle'; message('Could not join: ' + String(error.message ?? error)); }
    } finally { busy = false; render(); }
  }
  globalThis.__coopBeforeRun = async (module, args) => {
    if (!state.member || state.stopped) throw Error('Co-op membership is required before engine start');
    if (args.some((value, index) => value === '+set' && args[index + 1] === 'fs_mods')) throw Error('Classic co-op requires original scripts without saved mods');
    if (previousHook) await previousHook(module, args);
    module.__coopBaseWasmSha256 = state.metadata.baseWasmSha256;
    state.hookReached = true; eventLog('engine-hook');
    await tick();
    if (state.member.role === 'guest') message('Preparing Five locally. Click Ready after it loads.');
  };
  globalThis.__coopSend = packet => {
    if (state.stopped) return false;
    for (const edge of edges.values()) if (edge.remote.ip === packet.to) return edge.send(packet);
    return false;
  };
  const protectPlay = event => {
    if (event.target?.closest?.('#play') && (!state.member || state.stopped)) {
      event.preventDefault(); event.stopImmediatePropagation(); collapsed(false);
      message(state.stopped ? 'Reload for a new session before starting another engine.' : 'Host or join a co-op room first.');
    }
  };
  document.addEventListener('click', protectPlay, true);
  async function stop(notify = true) {
    if (state.stopped) return;
    state.stopped = true;
    for (const timer of timers) { clearTimeout(timer); clearInterval(timer); } timers.clear();
    for (const controller of controllers) controller.abort(); controllers.clear();
    resumeManager?.closeAll('leaving room'); edges.clear(); recovery.clear();
    if (notify && state.capability) {
      try { await api(state.member.role === 'host' ? 'close' : 'leave', {}); }
      catch (error) { state.errors.push('Leave notification failed: ' + String(error.message ?? error).slice(0, 200)); }
    }
    try { globalThis.__coopBridge?.command('disconnect'); } catch { /* command queue may already be closing */ }
    globalThis.__coopSend = previousSend;
    // Do not restore the hook for a warm in-place retry. A reload is required.
    if (state.phase !== 'failed') { state.phase = 'left'; message('Room left. Reload to create or join another room.'); }
    render();
  }
  host.onclick = () => { void begin('host'); }; join.onclick = () => { void begin('guest'); };
  guestReady.onclick = async () => {
    if (busy || state.stopped || state.started || state.member?.role !== 'guest' || !localWarm() || !edgesReady()) return;
    busy = true; render();
    try {
      if (globalThis.five?.screen === 'ready') {
        const play = document.getElementById('play');
        if (!play || play.disabled || play.hidden) throw Error('The game start control is unavailable');
        play.click(); eventLog('archive-ready-gesture');
      }
      state.prepared = true;
      message('Preparing player controls…');
      await tick();
    } catch (error) { failure(error); }
    finally { busy = false; render(); }
  };
  start.onclick = async () => {
    if (!canStart()) return;
    busy = true; render();
    try {
      // Keep activation-sensitive audio/fullscreen/mouse capture inside this
      // user gesture. The archive's own handler ends the held introduction.
      if (globalThis.five?.screen === 'ready') {
        const play = document.getElementById('play');
        if (!play || play.disabled || play.hidden) throw Error('The game start control is unavailable');
        play.click();
        eventLog('archive-start-gesture');
      }
      await api('start', {});
    }
    catch (error) { failure(error); }
    finally { busy = false; render(); }
  };
  leave.onclick = () => { void stop(); };
  window.addEventListener('pagehide', () => { void stop(false); }, {once: true});
  globalThis.__coopLobby = Object.freeze({snapshot: () => ({phase: state.phase, roomCode: state.room?.code ?? null,
    transport:state.transport,role: state.member?.role ?? null, identity: state.member?.identity ? {...state.member.identity} : null,
    preparationStrategy: 'native-SP-preload', prepared: state.prepared, nativeConnectIssued: state.nativeConnectIssued,
    hookReached: state.hookReached, engineReady: state.readySent, started: state.started,
    startEpoch: state.room?.startEpoch ?? 0, nativeStartSettled: state.nativeSettled, nativeSettled: state.nativeSettled, nativeStartedSent: state.nativeStartedSent,
    restartIssued: state.restartIssued, stopped: state.stopped, cursor: state.cursor,
    members: (state.room?.members ?? []).map(member => JSON.parse(JSON.stringify(member))),
    connections: [...edges.values()].map(edge => edge.getStats()), resume: resumeManager?.snapshot() ?? [], recovery: [...recovery].map(([peer,value])=>({peer,...value})), errors: [...state.errors],
    events: state.events.map(event => ({...event})), status: status.textContent})});
  installStatusDownload({panel,collector:{report(options){
    const module=globalThis.__coopModule, evidence=runtimeEvidenceFor(module);
    return createStatusCollector({metadata:state.metadata,verifiedRuntime:evidence,
      readLobby:()=>globalThis.__coopLobby.snapshot(),readBridge:()=>globalThis.__coopBridge?.snapshot(),
      readPrediction:()=>readPrediction(module,evidence,state.metadata),
      readEnvironment:()=>browserEnvironment()}).report(options);
  }}});
  render();
}
