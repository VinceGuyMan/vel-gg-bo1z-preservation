// Experimental transport only: carries original engine datagrams, never game state.
// One instance is one host/guest edge. A later star host owns one edge per guest.
// Manual bundles contain IP routing labels and SDP; exchange only with the intended peer.
const PROTOCOL = 'bo1z-native-rtc-resume-v2';
const PACKETS = 'native-packets-v1', CONTROL = 'room-control-v1';
const MAGIC = 0x4b425254, HEADER = 36, MAX_DATAGRAM = 65536, MAX_FRAME = 16384;
const MAX_CHUNKS = 64, MAX_ASSEMBLIES = 32, MAX_ASSEMBLY_BYTES = 512 * 1024;
const MAX_QUEUE = 32, MAX_QUEUE_BYTES = 512 * 1024, BUFFER_LIMIT = 256 * 1024;
const EXPIRY_MS = 2000, MAX_CONTROL = 8192, MAX_SDP = 128 * 1024;

function identity(value, fallback) {
  const ip = value?.ip ?? fallback;
  if (typeof ip !== 'string' || !/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) throw new TypeError('Invalid peer IPv4 identity');
  const octets = ip.split('.').map(Number);
  if (octets.some(n => n > 255) || octets.join('.') !== ip) throw new TypeError('Non-canonical peer IPv4 identity');
  const port = value?.port ?? 3074;
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new TypeError('Invalid logical peer port');
  return Object.freeze({ip, port});
}
function same(a, b) { return a?.ip === b.ip && a?.port === b.port; }
function canonical(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
}
function bytes(value) {
  if (value instanceof ArrayBuffer && value.byteLength <= MAX_DATAGRAM) return new Uint8Array(value).slice();
  if (ArrayBuffer.isView(value) && value.byteLength <= MAX_DATAGRAM) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength).slice();
  if (Array.isArray(value) && value.length <= MAX_DATAGRAM && value.every(n => Number.isInteger(n) && n >= 0 && n <= 255)) return Uint8Array.from(value);
  throw new TypeError('Datagram data must be bytes');
}

// Resolve only the selected transport path. Never return raw candidate records.
export function projectNetworkPath(report, sampledAtMs=0) {
  const empty={available:false,route:'unavailable',localCandidateType:null,remoteCandidateType:null,
    protocol:null,relayProtocol:null,roundTripTimeMs:null,bytesSent:null,bytesReceived:null,sampledAtMs:null};
  if(!report?.values)return empty;
  const rows=[...report.values()];
  const selected=[...new Set(rows.filter(r=>r.type==='transport'&&r.dtlsState==='connected'
    &&typeof r.selectedCandidatePairId==='string').map(r=>r.selectedCandidatePairId))];
  if(selected.length!==1)return empty;
  const byId=new Map(rows.map(r=>[r.id,r])),pair=byId.get(selected[0]);
  if(pair?.type!=='candidate-pair'||pair.state!=='succeeded')return empty;
  const local=byId.get(pair.localCandidateId),remote=byId.get(pair.remoteCandidateId);
  const types=['host','srflx','prflx','relay'];
  if(local?.type!=='local-candidate'||remote?.type!=='remote-candidate'
    ||!types.includes(local.candidateType)||!types.includes(remote.candidateType))return empty;
  const finite=(value,max=Number.MAX_SAFE_INTEGER)=>Number.isFinite(value)&&value>=0&&value<=max?value:null;
  const protocol=local.protocol===remote.protocol&&['udp','tcp'].includes(local.protocol)?local.protocol:null;
  const relays=[local,remote].filter(r=>r.candidateType==='relay');
  const relayProtocols=[...new Set(relays.map(r=>r.relayProtocol).filter(v=>['udp','tcp','tls'].includes(v)))];
  return {available:true,route:relays.length?'relay':'direct',localCandidateType:local.candidateType,
    remoteCandidateType:remote.candidateType,protocol,relayProtocol:relayProtocols.length===1?relayProtocols[0]:null,
    roundTripTimeMs:finite(pair.currentRoundTripTime,60)===null?null:pair.currentRoundTripTime*1000,
    bytesSent:finite(pair.bytesSent),bytesReceived:finite(pair.bytesReceived),sampledAtMs:finite(sampledAtMs)};
}

export function createRTCTransport(options = {}) {
  const role = options.role;
  if (role !== 'host' && role !== 'guest') throw new TypeError('Role must be host or guest');
  const local = identity(options.local, role === 'host' ? '10.0.0.1' : '10.0.0.2');
  const remote = identity(options.remote, role === 'host' ? '10.0.0.2' : '10.0.0.1');
  if (same(local, remote)) throw new TypeError('Peer identities must differ');
  const metadata = JSON.parse(JSON.stringify(options.metadata ?? {}));
  const metadataText = canonical(metadata);
  if (metadataText.length > MAX_CONTROL / 2) throw new RangeError('Build/map metadata is too large');
  const policy = options.iceTransportPolicy ?? 'all';
  if (!['all', 'relay'].includes(policy)) throw new TypeError('Invalid ICE transport policy');
  const gatheringTimeout = options.iceGatheringTimeoutMs ?? 15000;
  if (!Number.isInteger(gatheringTimeout) || gatheringTimeout < 1 || gatheringTimeout > 60000) throw new RangeError('Invalid ICE gathering timeout');
  const generation = options.generation ?? 1;
  if (!Number.isInteger(generation) || generation < 1 || generation > 3) throw Error('Invalid negotiation generation');
  const pc = new RTCPeerConnection({iceServers: options.iceServers ?? [], iceTransportPolicy: policy});
  const outgoingSock = role === 'host' ? 1 : 0, incomingSock = 1 - outgoingSock;
  const packetHandlers = new Set(options.onPacket ? [options.onPacket] : []);
  const eventHandlers = new Set(options.onEvent ? [options.onEvent] : []);
  const subscriptions = [], assemblies = new Map(), queue = [], pendingGather = new Set();
  const counters = {sentDatagrams: 0, sentBytes: 0, receivedDatagrams: 0, receivedBytes: 0,
    sentFrames: 0, receivedFrames: 0, droppedOutgoing: 0, droppedIncoming: 0,
    expiredAssemblies: 0, malformedFrames: 0, sendErrors: 0, callbackErrors: 0};
  const events = [];
  let packetChannel, controlChannel, verified = false, ready = false, closed = false;
  let negotiating = false, queueBytes = 0, assemblyBytes = 0, nextId = 0;
  const clock = () => performance.now();
  let networkPath=projectNetworkPath(null),pathPending=false,lastPathSample=-Infinity;
  async function samplePath() {
    if(closed||pc.connectionState!=='connected'||pathPending||clock()-lastPathSample<2000)return;
    pathPending=true;lastPathSample=clock();
    try {const report=await pc.getStats();if(!closed)networkPath=projectNetworkPath(report,clock());}
    catch {networkPath=projectNetworkPath(null);}
    finally {pathPending=false;}
  }
  function event(type, detail = {}) {
    const item = {type, at: clock(), ...detail};
    events.push(item); if (events.length > 64) events.shift();
    for (const fn of eventHandlers) {
      try { const result = fn(item); if (result?.then) Promise.resolve(result).catch(() => counters.callbackErrors++); }
      catch { counters.callbackErrors++; }
    }
  }
  function listen(target, name, fn) {
    target.addEventListener(name, fn);
    subscriptions.push(() => target.removeEventListener(name, fn));
  }
  function updateReady() {
    const value = !closed && pc.connectionState === 'connected' && verified && packetChannel?.readyState === 'open' && controlChannel?.readyState === 'open';
    if (value !== ready) { ready = value; event(value ? 'ready' : 'not-ready'); }
    if (ready) drain();
  }
  function controlSend(value) {
    const text = JSON.stringify(value);
    if (text.length > MAX_CONTROL || controlChannel?.readyState !== 'open') return false;
    try { controlChannel.send(text); return true; }
    catch (error) { event('control-error', {message: String(error)}); return false; }
  }
  function hello() {
    if (!controlSend({type: 'hello', protocol: PROTOCOL, role, local, remote, metadata, generation})) close('control hello failed');
  }
  function receiveControl(data) {
    try {
      if (typeof data !== 'string' || data.length > MAX_CONTROL) throw new Error('Invalid control frame');
      const message = JSON.parse(data);
      if (message.type === 'leave' && message.protocol === PROTOCOL) { close('peer left', false); return; }
      if (message.type !== 'hello' || message.generation !== generation || message.protocol !== PROTOCOL || message.role !== (role === 'host' ? 'guest' : 'host') ||
          !same(message.local, remote) || !same(message.remote, local) || canonical(message.metadata) !== metadataText) {
        throw new Error('Peer identity or build/map metadata mismatch');
      }
      verified = true; updateReady();
    } catch (error) { event('protocol-error', {message: String(error)}); close('control protocol rejected'); }
  }
  function bind(channel) {
    if (channel.label === PACKETS) {
      if (packetChannel || channel.ordered || channel.maxRetransmits !== 0) { channel.close(); close('Invalid native channel'); return; }
      packetChannel = channel; channel.binaryType = 'arraybuffer'; channel.bufferedAmountLowThreshold = BUFFER_LIMIT / 2;
      listen(channel, 'message', e => receiveFrame(e.data));
      listen(channel, 'bufferedamountlow', drain);
    } else if (channel.label === CONTROL) {
      if (controlChannel || !channel.ordered || channel.maxRetransmits !== null || channel.maxPacketLifeTime !== null) {
        channel.close(); close('Invalid control channel'); return;
      }
      controlChannel = channel; listen(channel, 'message', e => receiveControl(e.data));
      listen(channel, 'open', hello);
    } else { channel.close(); close('Unexpected data channel'); return; }
    listen(channel, 'open', updateReady);
    listen(channel, 'close', () => { if (!closed) close('data channel closed', false); });
    listen(channel, 'error', e => event('channel-error', {channel: channel.label, message: String(e.error ?? 'Data channel error')}));
    if (channel.readyState === 'open') { if (channel.label === CONTROL) hello(); updateReady(); }
  }
  listen(pc, 'datachannel', e => {
    if (closed || role !== 'guest') { e.channel.close(); return; }
    bind(e.channel);
  });
  listen(pc, 'connectionstatechange', () => {
    updateReady();
    event('connection-state', {state: pc.connectionState});
    if (pc.connectionState === 'disconnected') event('disconnect', {temporary: true});
    if (['failed', 'closed'].includes(pc.connectionState) && !closed) close('peer connection ' + pc.connectionState, false);
  });
  listen(pc, 'iceconnectionstatechange', () => event('ice-state', {state: pc.iceConnectionState}));

  function wireSize() {
    const negotiated = pc.sctp?.maxMessageSize;
    const limit = negotiated > 0 ? Math.min(MAX_FRAME, negotiated) : MAX_FRAME;
    return Math.floor(limit);
  }
  function encode(packet, data) {
    const capacity = wireSize() - HEADER;
    if (capacity < 1024) throw new Error('Negotiated SCTP message limit is too small');
    const count = Math.ceil(data.length / capacity), id = nextId++ >>> 0;
    if (count > MAX_CHUNKS) throw new Error('Too many datagram chunks');
    const frames = [];
    for (let i = 0; i < count; i++) {
      const payload = data.subarray(i * capacity, (i + 1) * capacity);
      const frame = new Uint8Array(HEADER + payload.length), view = new DataView(frame.buffer);
      view.setUint32(0, MAGIC); view.setUint8(4, 1); view.setUint8(5, packet.sock); view.setUint16(6, HEADER);
      view.setUint32(8, id); view.setUint32(12, data.length);
      frame.set(local.ip.split('.').map(Number), 16); frame.set(remote.ip.split('.').map(Number), 20);
      view.setUint16(24, local.port); view.setUint16(26, remote.port);
      view.setUint16(28, i); view.setUint16(30, count); view.setUint32(32, capacity);
      frame.set(payload, HEADER); frames.push(frame);
    }
    return {frames, length: data.length, wireBytes: data.length + count * HEADER, at: clock()};
  }
  function send(packet) {
    if (closed || !ready) { counters.droppedOutgoing++; return false; }
    try {
      if (!packet || packet.sock !== outgoingSock || packet.to !== remote.ip ||
          (packet.from !== undefined && packet.from !== local.ip) ||
          (packet.fromPort ?? local.port) !== local.port || (packet.toPort ?? remote.port) !== remote.port) {
        throw new Error('Unknown datagram destination, source, socket or port');
      }
      const data = bytes(packet.data);
      if (!data.length || data.length > MAX_DATAGRAM) throw new RangeError('Invalid native datagram length');
      const item = encode(packet, data);
      if (queue.length >= MAX_QUEUE || queueBytes + item.wireBytes > MAX_QUEUE_BYTES) {
        counters.droppedOutgoing++; event('backpressure', {kind: 'queue-full'}); return false;
      }
      queue.push(item); queueBytes += item.wireBytes; drain(); return true;
    } catch (error) { counters.droppedOutgoing++; event('send-rejected', {message: String(error)}); return false; }
  }
  function drain() {
    if (!ready || closed) return;
    while (queue.length) {
      const item = queue[0];
      if (clock() - item.at > EXPIRY_MS) {
        queue.shift(); queueBytes -= item.wireBytes; counters.droppedOutgoing++; event('backpressure', {kind: 'queue-expired'}); continue;
      }
      if (packetChannel.bufferedAmount + item.wireBytes > BUFFER_LIMIT) return;
      queue.shift(); queueBytes -= item.wireBytes;
      try {
        for (const frame of item.frames) { packetChannel.send(frame.buffer); counters.sentFrames++; }
        counters.sentDatagrams++; counters.sentBytes += item.length;
      } catch (error) {
        // Partial chunks are never delivered to the engine. Native Netchan owns retries.
        counters.sendErrors++; counters.droppedOutgoing++; event('send-error', {message: String(error)});
      }
    }
  }
  function forget(id) {
    const entry = assemblies.get(id);
    if (entry) { assemblyBytes -= entry.length; assemblies.delete(id); }
  }
  function receiveFrame(buffer) {
    if (closed || !ready) { counters.droppedIncoming++; return; }
    let id;
    try {
      if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < HEADER || buffer.byteLength > MAX_FRAME) throw new Error('Invalid binary frame size');
      const frame = new Uint8Array(buffer), view = new DataView(buffer);
      if (view.getUint32(0) !== MAGIC || view.getUint8(4) !== 1 || view.getUint16(6) !== HEADER || view.getUint8(5) !== incomingSock) throw new Error('Invalid binary frame header');
      if (Array.from(frame.subarray(16, 20)).join('.') !== remote.ip || Array.from(frame.subarray(20, 24)).join('.') !== local.ip ||
          view.getUint16(24) !== remote.port || view.getUint16(26) !== local.port) throw new Error('Frame identity mismatch');
      id = view.getUint32(8);
      const length = view.getUint32(12), index = view.getUint16(28), count = view.getUint16(30), capacity = view.getUint32(32);
      if (!length || length > MAX_DATAGRAM || capacity < 1024 || capacity > MAX_FRAME - HEADER || !count || count > MAX_CHUNKS ||
          count !== Math.ceil(length / capacity) || index >= count || frame.length - HEADER !== Math.min(capacity, length - index * capacity)) {
        throw new Error('Invalid datagram chunk bounds');
      }
      counters.receivedFrames++;
      let entry = assemblies.get(id);
      if (!entry) {
        if (assemblies.size >= MAX_ASSEMBLIES || assemblyBytes + length > MAX_ASSEMBLY_BYTES) { counters.droppedIncoming++; event('backpressure', {kind: 'assembly-full'}); return; }
        entry = {length, capacity, count, at: clock(), data: new Uint8Array(length), seen: new Uint8Array(count), received: 0};
        assemblies.set(id, entry); assemblyBytes += length;
      }
      if (entry.length !== length || entry.capacity !== capacity || entry.count !== count) throw new Error('Inconsistent datagram chunks');
      const offset = index * capacity, payload = frame.subarray(HEADER);
      if (entry.seen[index]) {
        if (payload.some((b, n) => entry.data[offset + n] !== b)) throw new Error('Conflicting duplicate chunk');
        return;
      }
      entry.data.set(payload, offset); entry.seen[index] = 1; entry.received++;
      if (entry.received !== count) return;
      forget(id); counters.receivedDatagrams++; counters.receivedBytes += length;
      // Source identity is taken from configured membership, never trusted from the envelope.
      const packet = {sock: incomingSock, from: remote.ip, fromPort: remote.port, to: local.ip, toPort: local.port, data: entry.data};
      for (const fn of packetHandlers) {
        const failed = error => { counters.callbackErrors++; event('packet-callback-error', {message: String(error)}); };
        try { const result = fn(packet); if (result?.then) Promise.resolve(result).catch(failed); }
        catch (error) { failed(error); }
      }
    } catch (error) {
      if (id !== undefined) forget(id);
      counters.malformedFrames++; counters.droppedIncoming++; event('frame-rejected', {message: String(error)});
    }
  }
  function validateBundle(bundle, type) {
    if (!bundle || bundle.generation !== generation || bundle.protocol !== PROTOCOL || bundle.type !== type || typeof bundle.sdp !== 'string' ||
        !bundle.sdp.length || bundle.sdp.length > MAX_SDP || !same(bundle.local, remote) || !same(bundle.remote, local) ||
        canonical(bundle.metadata) !== metadataText) throw new Error('Signaling identity, build/map metadata or SDP mismatch');
  }
  async function gather() {
    if (pc.iceGatheringState === 'complete') return;
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => finish(new Error('ICE gathering timed out')), gatheringTimeout);
      function changed() { if (pc.iceGatheringState === 'complete') finish(); }
      function state() { if (closed) finish(new Error('Transport closed during ICE gathering')); }
      function finish(error) { clearTimeout(timeout); pendingGather.delete(finish); pc.removeEventListener('icegatheringstatechange', changed); pc.removeEventListener('connectionstatechange', state); error ? reject(error) : resolve(); }
      pc.addEventListener('icegatheringstatechange', changed); pc.addEventListener('connectionstatechange', state);
      pendingGather.add(finish);
      changed(); state();
    });
  }
  function bundle() {
    return {protocol: PROTOCOL, type: pc.localDescription.type, sdp: pc.localDescription.sdp, local, remote, metadata: JSON.parse(metadataText), generation};
  }
  async function negotiate(action) {
    if (closed || negotiating) throw new Error('Transport closed or negotiation already running');
    negotiating = true;
    try { return await action(); }
    catch (error) { event('negotiation-error', {message: String(error)}); throw error; }
    finally { negotiating = false; }
  }
  function close(reason = 'closed', notify = true) {
    if (closed) return;
    if (notify) controlSend({type: 'leave', protocol: PROTOCOL});
    closed = true; ready = false; verified = false; clearInterval(timer);
    for (const finish of pendingGather) finish(new Error('Transport closed during ICE gathering'));
    counters.droppedOutgoing += queue.length; queue.length = 0; queueBytes = 0;
    counters.droppedIncoming += assemblies.size; assemblies.clear(); assemblyBytes = 0;
    subscriptions.splice(0).forEach(remove => remove());
    packetChannel?.close(); controlChannel?.close(); pc.close();
    event('closed', {reason});
    packetHandlers.clear(); eventHandlers.clear();
  }
  const timer = setInterval(() => {
    for (const [id, entry] of assemblies) if (clock() - entry.at > EXPIRY_MS) {
      forget(id); counters.expiredAssemblies++; counters.droppedIncoming++;
    }
    drain();
  }, 50);

  return {
    local, remote, role, protocol: PROTOCOL,
    createOffer: () => negotiate(async () => {
      if (role !== 'host' || pc.signalingState !== 'stable' || packetChannel) throw new Error('Only a new host edge may create an offer');
      bind(pc.createDataChannel(PACKETS, {ordered: false, maxRetransmits: 0}));
      bind(pc.createDataChannel(CONTROL, {ordered: true}));
      await pc.setLocalDescription(await pc.createOffer()); await gather(); return bundle();
    }),
    acceptOffer: offer => negotiate(async () => {
      if (role !== 'guest' || pc.signalingState !== 'stable' || pc.remoteDescription) throw new Error('Only a new guest edge may accept an offer');
      validateBundle(offer, 'offer'); await pc.setRemoteDescription({type: 'offer', sdp: offer.sdp});
      await pc.setLocalDescription(await pc.createAnswer()); await gather(); return bundle();
    }),
    acceptAnswer: answer => negotiate(async () => {
      if (role !== 'host' || pc.signalingState !== 'have-local-offer') throw new Error('Host has no pending offer');
      validateBundle(answer, 'answer'); await pc.setRemoteDescription({type: 'answer', sdp: answer.sdp});
    }),
    send,
    onPacket(fn) { if (closed || typeof fn !== 'function') throw new TypeError('Open transport and packet handler required'); packetHandlers.add(fn); return () => packetHandlers.delete(fn); },
    onEvent(fn) { if (closed || typeof fn !== 'function') throw new TypeError('Open transport and event handler required'); eventHandlers.add(fn); return () => eventHandlers.delete(fn); },
    getStats() { void samplePath(); return {protocol: PROTOCOL, generation, role, local, remote, ready, closed, verified,
      networkPath:{...(closed||pc.connectionState!=='connected'?projectNetworkPath(null):networkPath)}, connectionState: pc.connectionState,
      iceConnectionState: pc.iceConnectionState, iceGatheringState: pc.iceGatheringState, signalingState: pc.signalingState,
      negotiatedMaxMessageSize: pc.sctp?.maxMessageSize ?? null, bufferedAmount: packetChannel?.bufferedAmount ?? 0,
      queuedDatagrams: queue.length, queuedBytes: queueBytes, assemblies: assemblies.size, assemblyBytes, ...counters,
      events: events.map(item => ({...item}))}; },
    async getRTCStats() {
      if (closed) return [];
      const report = await pc.getStats(), rows = [];
      report.forEach(row => {
        if (!['candidate-pair', 'data-channel', 'transport'].includes(row.type)) return;
        const result = {id: row.id, type: row.type};
        for (const key of ['state', 'nominated', 'bytesSent', 'bytesReceived', 'messagesSent', 'messagesReceived', 'currentRoundTripTime', 'dtlsState']) {
          if (row[key] !== undefined) result[key] = row[key];
        }
        rows.push(result);
      }); return rows;
    },
    close
  };
}
