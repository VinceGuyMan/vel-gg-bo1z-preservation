// Read-only, build-specific observer: no WASM calls and no writes to engine memory.
// Caller must verify its patched WASM descends from this exact original layout.
export const OBSERVER_LAYOUT_BASE_SHA256 = '61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98';
const CACHE = new WeakMap();
const KEYS = ['round_number', 'zombie_total', 'zombie_health'];
const LAYOUT = Object.freeze({
  levelId: 54544416, variableList: 54544128, capacity: 1293480,
  childStart: 1293488, stringSlab: 53691904, canonicalCount: 54544388,
  canonicalRecords: 51058164, canonicalLookup: 51058168, canonicalMap: 50782284,
  entityBase: 87604176, entityStride: 760, entitySlots: 1024,
});

export function observeZombies(module) {
  const result = {
    layoutBaseWasmSha256: OBSERVER_LAYOUT_BASE_SHA256,
    observation: 'Read-only host authority; guest server script memory is not a replicated round/health view.',
    script: {}, actors: [], errors: [],
    actorScan: { scope: 'First 1024 protocol-addressable entity slots only; excludes any larger private pool.',
      slots: LAYOUT.entitySlots, scanned: 0, liveActorCandidates: 0, invalidActorPointers: 0 },
  };
  const missing = (reason) => {
    for (const key of KEYS) result.script[key] = { available: false, error: reason };
    return result;
  };
  if (!module || (typeof module !== 'object' && typeof module !== 'function')) return missing('Missing module');
  if (module.__coopBaseWasmSha256 && module.__coopBaseWasmSha256 !== OBSERVER_LAYOUT_BASE_SHA256) {
    result.errors.push('Declared base WASM hash differs from observer layout pin');
    return missing(result.errors[0]);
  }
  const buffer = module.HEAPU8?.buffer ?? module.HEAPF32?.buffer;
  if (!buffer || typeof buffer.byteLength !== 'number') return missing('WASM heap view unavailable');
  let view;
  try { view = new DataView(buffer); } catch (error) { return missing('Heap inaccessible: ' + String(error)); }
  const within = (pointer, bytes, alignment = 1) => Number.isSafeInteger(pointer)
    && pointer > 0 && pointer % alignment === 0 && Number.isSafeInteger(bytes)
    && bytes >= 0 && pointer <= view.byteLength - bytes;
  const u32 = (p) => { if (!within(p, 4, 4)) throw Error('Invalid uint32 pointer ' + p); return view.getUint32(p, true); };
  const i32 = (p) => { if (!within(p, 4, 4)) throw Error('Invalid int32 pointer ' + p); return view.getInt32(p, true); };
  const bytes = new Uint8Array(buffer);
  const context = () => ({ levelId: u32(LAYOUT.levelId), list: u32(LAYOUT.variableList),
    capacity: u32(LAYOUT.capacity), childStart: u32(LAYOUT.childStart), slab: u32(LAYOUT.stringSlab),
    canonicalCount: within(LAYOUT.canonicalCount, 2, 2) ? view.getUint16(LAYOUT.canonicalCount, true) : 0,
    canonicalRecords: u32(LAYOUT.canonicalRecords), canonicalLookup: u32(LAYOUT.canonicalLookup) });
  const textMatches = (pointer, key) => {
    if (!within(pointer, key.length + 1)) return false;
    for (let i = 0; i < key.length; i++) if (bytes[pointer + i] !== key.charCodeAt(i)) return false;
    return bytes[pointer + key.length] === 0;
  };
  // Script object fields carry canonical IDs, not ordinary SL string IDs.
  // Scr_GetCanonicalString: lookup[id] -> 8-byte archived record -> text pointer.
  const keyMatches = (ctx, entry, key) => {
    if (!entry || entry.canonicalId <= 0 || entry.canonicalId > ctx.canonicalCount) return false;
    if (entry.source === 'canonical archive') {
      if (!within(ctx.canonicalLookup, (ctx.canonicalCount + 1) * 4, 4)
        || !within(ctx.canonicalRecords, ctx.canonicalCount * 8, 4)) return false;
      const index = u32(ctx.canonicalLookup + entry.canonicalId * 4);
      if (index >= ctx.canonicalCount) return false;
      const record = ctx.canonicalRecords + index * 8;
      return view.getUint16(record, true) === entry.canonicalId
        && u32(record + 4) === entry.pointer && textMatches(entry.pointer, key);
    }
    const id = entry.stringId;
    return Number.isInteger(id) && id > 0 && id < 65536
      && within(LAYOUT.canonicalMap, 131072, 2)
      && view.getUint16(LAYOUT.canonicalMap + id * 2, true) === entry.canonicalId
      && entry.pointer === ctx.slab + id * 16 + 4 && textMatches(entry.pointer, key);
  };
  let ctx;
  try {
    ctx = context();
    result.scriptContext = { ...ctx };
    if (!ctx.levelId || !ctx.list || !ctx.capacity || !ctx.childStart || !ctx.canonicalCount) throw Error('Server script context not initialized');
    if (ctx.capacity < 2 || ctx.capacity > 0x1000000 || ctx.childStart > 0x1000000) throw Error('Invalid dynamic script capacity');
    const table = ctx.list + ctx.childStart * 28;
    if (!within(ctx.list, 28, 4) || !within(table, ctx.capacity * 28, 4)) throw Error('Dynamic script storage outside heap');
    if (ctx.levelId >= ctx.childStart) throw Error('Level object outside parent region');
    const parentStatus = u32(ctx.list + ctx.levelId * 28 + 44);
    if ((parentStatus & 96) !== 96 || (parentStatus & 31) <= 12) throw Error('Level object has invalid parent status');
    let cache = CACHE.get(module);
    if (!cache || cache.slab !== ctx.slab || cache.buffer !== buffer
      || cache.records !== ctx.canonicalRecords || cache.lookup !== ctx.canonicalLookup) {
      cache = { slab: ctx.slab, buffer, records: ctx.canonicalRecords,
        lookup: ctx.canonicalLookup, ids: Object.create(null) }; CACHE.set(module, cache);
    }
    // Revalidate cached IDs/text against current native lookup structures every time.
    const unresolved = KEYS.filter(key => !keyMatches(ctx, cache.ids[key], key));
    for (const key of unresolved) delete cache.ids[key];
    const admit = entry => {
      for (let k = unresolved.length - 1; k >= 0; k--) {
        const key = unresolved[k];
        if (keyMatches(ctx, entry, key)) { cache.ids[key] = entry; unresolved.splice(k, 1); }
      }
    };
    if (within(ctx.canonicalRecords, ctx.canonicalCount * 8, 4)
      && within(ctx.canonicalLookup, (ctx.canonicalCount + 1) * 4, 4)) {
      // At most 65535 records; inspect only each record's string pointer and key bytes.
      for (let index = 0; index < ctx.canonicalCount && unresolved.length; index++) {
        const record = ctx.canonicalRecords + index * 8;
        admit({ canonicalId: view.getUint16(record, true), pointer: u32(record + 4),
          source: 'canonical archive' });
      }
    }
    if (unresolved.length && within(ctx.slab, 1048576, 4)
      && within(LAYOUT.canonicalMap, 131072, 2)) {
      // Debug archive may be disabled. The live compiler map is an exact SL -> canonical mapping.
      for (let id = 1; id < 65536 && unresolved.length; id++) {
        const canonicalId = view.getUint16(LAYOUT.canonicalMap + id * 2, true);
        if (canonicalId) admit({ canonicalId, stringId: id,
          pointer: ctx.slab + id * 16 + 4, source: 'compiler canonical map' });
      }
    }
    for (const key of KEYS) {
      const entry = cache.ids[key], name = entry?.canonicalId;
      if (!name) { result.script[key] = { available: false, error: 'Canonical field name absent from bounded archive/compiler map' }; continue; }
      try {
        const hash = ((ctx.levelId + name) >>> 0) % (ctx.capacity - 1) + 1;
        let slot = hash, matched = false;
        const visited = new Set();
        for (let step = 0; step < 256; step++) {
          if (slot <= 0 || slot >= ctx.capacity || visited.has(slot)) throw Error('Invalid or cyclic variable hash chain');
          visited.add(slot);
          const variableId = u32(table + slot * 28);
          if (!variableId) break;
          if (variableId >= ctx.capacity) throw Error('Variable ID outside dynamic capacity');
          const pointer = table + variableId * 28;
          const status = u32(pointer + 16);
          const chainKind = step === 0 ? 64 : 32;
          if ((status & 96) !== chainKind || (status & 31) >= 13) throw Error('Variable hash status inconsistent');
          if ((status >>> 8) === name) {
            const type = status & 31;
            if (type !== 6 && type !== 5) {
              result.script[key] = { available: false, canonicalId: name, variableId, type,
                error: 'Script value is not an integer or float' };
            } else {
              const value = type === 6 ? i32(pointer + 8) : view.getFloat32(pointer + 8, true);
              if (!Number.isFinite(value)) throw Error('Non-finite script value');
              if (u32(pointer + 16) !== status || !keyMatches(ctx, entry, key)) throw Error('Script value changed during lookup');
              result.script[key] = { available: true, value, type, typeName: type === 6 ? 'integer' : 'float',
                canonicalId: name, nameSource: entry.source, variableId, traversed: step + 1 };
            }
            matched = true; break;
          }
          const next = u32(pointer + 20);
          if (next === hash) break;
          slot = next;
          if (step === 255) throw Error('Variable hash traversal exceeded 256 records');
        }
        if (!matched) result.script[key] = { available: false, canonicalId: name, error: 'Level variable absent' };
      } catch (error) { result.script[key] = { available: false, canonicalId: name, error: String(error.message ?? error) }; }
    }
    const after = context();
    if (Object.keys(ctx).some(key => ctx[key] !== after[key])) {
      result.errors.push('Script storage changed during observation');
      for (const key of KEYS) result.script[key] = { available: false, error: result.errors.at(-1) };
    }
  } catch (error) {
    const message = String(error.message ?? error); result.errors.push(message); missing(message);
  }
  // Host entity storage is independently observable even when script VM is unavailable.
  if (!within(LAYOUT.entityBase, LAYOUT.entityStride * LAYOUT.entitySlots, 4)) {
    result.errors.push('Protocol-bounded entity region outside heap'); return result;
  }
  for (let slot = 0; slot < LAYOUT.entitySlots; slot++) {
    const p = LAYOUT.entityBase + slot * LAYOUT.entityStride;
    result.actorScan.scanned++;
    const inuse = bytes[p + 232], eType = view.getUint16(p + 190, true);
    if (!inuse || eType !== 17) continue;
    const actorPointer = u32(p + 328), health = i32(p + 404);
    if (!actorPointer || !within(actorPointer, 4, 4)) { result.actorScan.invalidActorPointers++; continue; }
    if (health <= 0) continue;
    const number = u32(p), origin = [24, 28, 32].map(offset => view.getFloat32(p + offset, true));
    if (!origin.every(Number.isFinite)) { result.errors.push('Non-finite actor origin at slot ' + slot); continue; }
    if (bytes[p + 232] !== inuse || view.getUint16(p + 190, true) !== eType
      || u32(p + 328) !== actorPointer || u32(p) !== number) continue;
    result.actors.push({ slot, number, eType, health, actorPointer, origin,
      classification: 'Live native actor candidate; not independently classified as a Zombie' });
  }
  result.actorScan.liveActorCandidates = result.actors.length;
  return result;
}
