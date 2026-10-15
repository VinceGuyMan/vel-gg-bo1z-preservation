#!/usr/bin/env python3
"""Serve experimental BO1Z overlays while reading the preserved archive only."""
import argparse
import hashlib
import json
import os
import re
import socket
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen
from portable_replay import load_archive_replay
from host_settings import MAPS

HERE = Path(__file__).resolve().parent
BUILD = 'bo1z-lan-lobby-v2'
BASE_SHA = '61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98'


class CoopAssetServer(ThreadingHTTPServer):
    request_queue_size = 64

    def server_bind(self):
        if os.name == 'nt':
            # Winsock reuse can share a live listener; require exclusive bind.
            self.allow_reuse_address = False
            self.allow_reuse_port = False
            exclusive = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
            if exclusive is None:
                raise RuntimeError('This Python runtime lacks exclusive Windows socket binding')
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def default_archive():
    sibling = HERE.parent / 'vel-gg-bo1z-2026-10-08'
    return sibling if sibling.is_dir() else HERE.parents[1] / 'outputs/vel-gg-bo1z-2026-10-08'


def discovery_origin(value):
    if not value or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', value) or not 1 <= urlsplit(value).port <= 65535:
        raise ValueError('Discovery origin must be an owned loopback HTTP port')
    return value


def coop_page(root, slug):
    if slug not in MAPS: raise ValueError('Unknown captured map')
    page = (root / ('site/bo1z/' + slug + '.html')).read_text(encoding='utf-8')
    needle = '<script type="module" src="play.js">'
    if page.count(needle) != 1: raise ValueError('Captured map page interface differs')
    return page.replace('</head>', '<link rel="stylesheet" href="/bo1z/coop/lobby.css"></head>').replace(needle, '<script type="module" src="/bo1z/coop/lobby.js"></script><script type="module" src="/bo1z/coop-play.js">').encode()


def overlays(root):
    original_engine = (root / 'site/bo1z/engine.js').read_text(encoding='utf-8')
    profile_import = "import {getPlayerProfile} from './coop/player-profile.js';\n"
    engine = profile_import + original_engine
    engine = engine.replace("from './maps.js'", "from './coop-maps.js'")
    engine = engine.replace("import(BASE + 'artifacts/KisakBlack-web.mjs')", "import(BASE + 'artifacts/KisakBlack-web-coop.mjs')")
    engine = "import { prepareVerifiedRuntime } from './coop/runtime-attestation.js';\n" + engine
    needle = 'module = await createKisakBrowser({'
    assert engine.count(needle) == 1
    engine = engine.replace(needle, "const coopRuntime = await prepareVerifiedRuntime().catch(()=>{throw Error('Co-op package verification failed. Close this page and verify the package before retrying.');});\n    " + needle + "\n      __coopObserveWasmBytes: coopRuntime.observeWasmBytes,")
    needle = 'state.timings.wasmReady = performance.now();'
    assert engine.count(needle) == 1
    engine = engine.replace(needle, needle + '\n    globalThis.__coopModule=module; let coopVerified; try {coopVerified=coopRuntime.activate(module,()=>globalThis.__coopConfig);} catch {} if(!coopVerified){module.PThread?.terminateAllThreads();throw Error("Co-op package verification failed. Close this page and verify the package before retrying.");} globalThis.__coopBridge=coopVerified.bridge; globalThis.__coopNativeResumeAdmission=coopVerified.nativeResumeAdmission;')
    needle = 'module.callMain(args);'
    assert engine.count(needle) == 1
    prefs_injection = """
    try {
      const p = JSON.parse(localStorage.getItem('bo1z-title-preferences-v1') || '{}');
      const setDvar = (name, val) => {
        val = String(val);
        let found = false;
        for (let i = 0; i < args.length - 1; ++i) {
          if (args[i] === name && i > 0 && args[i - 1] === '+set') {
            args[i + 1] = val;
            found = true;
          }
        }
        if (!found) {
          const d = args.indexOf('+devmap');
          if (d >= 0) args.splice(d, 0, '+set', name, val);
          else args.push('+set', name, val);
        }
      };
      if (p.fov) setDvar('cg_fov', p.fov);
      if (p.aa) setDvar('r_aaSamples', p.aa);
      if (p.maxfps !== undefined) setDvar('com_maxfps', p.maxfps);
      if (p.aniso) setDvar('r_texFilterAnisoMin', p.aniso);
      if (p.texture !== undefined) setDvar('r_picmip', p.texture);
      if (p.shadows !== undefined) setDvar('sm_enable', p.shadows ? '1' : '0');
      if (p.vsync !== undefined) setDvar('r_vsync', p.vsync ? '1' : '0');
      if (p.dof !== undefined) setDvar('r_dof_enable', p.dof ? '1' : '0');
      if (p.drawFps !== undefined) {
        setDvar('cg_drawFPS', p.drawFps ? '1' : '0');
        setDvar('kisak_fpscounter', p.drawFps ? '1' : '0');
      }
      if (p.zombieCounter) {
        let fsModsIdx = -1;
        for (let i = 0; i < args.length - 1; ++i) {
          if (args[i] === 'fs_mods' && i > 0 && args[i - 1] === '+set') {
            fsModsIdx = i + 1;
            break;
          }
        }
        if (fsModsIdx >= 0) {
          const cur = args[fsModsIdx].split(' ').filter(Boolean);
          if (!cur.includes('zinfo')) {
            cur.push('zinfo');
            args[fsModsIdx] = cur.join(' ');
          }
        } else {
          setDvar('fs_mods', 'zinfo');
        }
        setDvar('zinfo', '1');
        setDvar('kisak_mod_tabinfo', '1');
        setDvar('developer', '0');
        setDvar('developer_script', '0');
        setDvar('con_minicon', '0');
      }
    } catch {}
"""
    original_engine_patched = profile_import + original_engine.replace('module.callMain(args);', prefs_injection + "args.splice(args.indexOf('+devmap'),0,'+set','name',getPlayerProfile().name); module.callMain(args);")
    engine = engine.replace(needle, prefs_injection + """const devmap=args.indexOf('+devmap');
    if(devmap<0)throw Error('Experimental co-op requires a configured Zombies map');
    args.splice(devmap,0,'+set','name',getPlayerProfile().name);
    args.splice(devmap,0,'+set','sv_maxclients',String(globalThis.__coopConfig?.settings?.maxPlayers??4));
    const userRoot=args.indexOf('fs_h');
    if(userRoot>=0)args[userRoot+1]='/opfs/bo1z-lan-lobby-v2-user';
    if(globalThis.__coopConfig?.role==='client' && !globalThis.__coopConfig?.deferJoin)
      args.splice(args.indexOf('+devmap'),2,'+connect','10.0.0.1:3074');
    state.arguments=[...args];
    if(globalThis.__coopBeforeRun)await globalThis.__coopBeforeRun(module,args);
    module.callMain(args);""")
    needle = "if (hordePage) args.splice(args.indexOf('+devmap'), 0, ...hordeArguments(HORDE_GAME));\n    else if (settings.mods?.includes('horde')) args.splice(args.indexOf('+devmap'), 0, ...hordeArguments({ ...settings.horde, mods: settings.mods }));\n    else if (settings.mods?.length) args.splice(args.indexOf('+devmap'), 0, '+set', 'fs_mods', settings.mods.join(' '));"
    if engine.count(needle) != 1:
        raise ValueError('Captured Horde argument interface differs')
    engine = engine.replace(needle, """const roomOptions=globalThis.__coopConfig?.settings;
    if(!roomOptions)throw Error('Host settings are required before co-op engine start');
    if(roomOptions.mode==='horde')args.splice(args.indexOf('+devmap'),0,...hordeArguments({n:roomOptions.enemyCount,round:roomOptions.startRound,mods:['horde',...(roomOptions.counter?['zinfo']:[]),...(roomOptions.noPerks?['noperks']:[])]}));
    else if(roomOptions.counter)args.splice(args.indexOf('+devmap'),0,'+set','fs_mods','zinfo');""")
    engine = engine.replace("'kisak-page-query'", "'bo1z-lan-lobby-v2-page-query'")
    assert engine.count("'kisak-renderer'") == 3
    engine = engine.replace("'kisak-renderer'", "'bo1z-lan-lobby-v2-renderer'")
    raw_maps = (root / 'site/bo1z/maps.js').read_text(encoding='utf-8')
    needle = "opfs: m.zone === FIRST ? 'pack' : 'pack-' + m.slug"
    assert raw_maps.count(needle) == 1
    manifest_needle = "export const manifestUrl = horde ? packBase + 'web-manifest-horde.json' : map.root + 'manifest.json';"
    assert raw_maps.count(manifest_needle) == 1
    manifest_patch = """let wantsMods = horde;
try {
  const p = JSON.parse(localStorage.getItem('bo1z-title-preferences-v1') || '{}');
  if (p.zombieCounter) wantsMods = true;
} catch {}
try {
  const s = JSON.parse(localStorage.getItem(map.settings) || '{}');
  if (s.zombieCounter || (Array.isArray(s.mods) && s.mods.includes('zinfo'))) wantsMods = true;
} catch {}
export const manifestUrl = (wantsMods || horde) ? packBase + 'web-manifest-horde.json' : map.root + 'manifest.json';"""
    solo_maps = raw_maps.replace(manifest_needle, manifest_patch)
    coop_maps = solo_maps.replace(needle, "opfs: 'bo1z-lan-lobby-v2-pack-' + m.slug")
    coop_maps = coop_maps.replace("settings: m.slug + '-settings'", "settings: 'bo1z-lan-lobby-v2-' + m.slug + '-settings'")
    # Preserve workers' BroadcastChannel pairing after changing the page identity.
    raw_glue = (root / 'site/bo1z/artifacts/KisakBlack-web.mjs').read_text(encoding='utf-8')
    solo_glue = raw_glue.replace('requiredLimits:{maxVertexBuffers:adapter.limits.maxVertexBuffers,maxVertexAttributes:adapter.limits.maxVertexAttributes}',
                                 'requiredLimits:{maxVertexBuffers:adapter.limits.maxVertexBuffers,maxVertexAttributes:adapter.limits.maxVertexAttributes,maxTextureDimension3D:adapter.limits.maxTextureDimension3D}')
    glue = raw_glue.replace('kisak-page-query', 'bo1z-lan-lobby-v2-page-query')
    # Observe bytes at the original successful instantiation sites. Keep original
    # Emscripten Asyncify/TLS/worker/runtime startup and fallback paths intact.
    needle = 'var instance=await WebAssembly.instantiate(binary,imports);return instance'
    assert glue.count(needle) == 1
    glue = glue.replace(needle, 'var instance=await WebAssembly.instantiate(binary,imports);try{await Module["__coopObserveWasmBytes"]?.(binary,instance["module"],Module)}catch{}return instance')
    needle = 'var response=fetch(binaryFile,{credentials:"same-origin"});var instantiationResult=await WebAssembly.instantiateStreaming(response,imports);return instantiationResult'
    assert glue.count(needle) == 1
    glue = glue.replace(needle, 'var response=fetch(binaryFile,{credentials:"same-origin"});var observedBytes=Module["__coopObserveWasmBytes"]?response.then(r=>r.clone().arrayBuffer()).catch(()=>null):null;var instantiationResult=await WebAssembly.instantiateStreaming(response,imports);try{if(observedBytes)await Module["__coopObserveWasmBytes"](await observedBytes,instantiationResult["module"],Module)}catch{}return instantiationResult')
    glue = glue.replace('KisakBlack-web.mjs', 'KisakBlack-web-coop.mjs').replace('KisakBlack-web.wasm', 'KisakBlack-web-coop.wasm')
    glue = glue.replace('requiredLimits:{maxVertexBuffers:adapter.limits.maxVertexBuffers,maxVertexAttributes:adapter.limits.maxVertexAttributes}',
                        'requiredLimits:{maxVertexBuffers:adapter.limits.maxVertexBuffers,maxVertexAttributes:adapter.limits.maxVertexAttributes,maxTextureDimension3D:adapter.limits.maxTextureDimension3D}')
    raw_play = (root / 'site/bo1z/play.js').read_text(encoding='utf-8')
    mods_load_needle = "if (Array.isArray(saved?.mods)) savedMods = saved.mods.filter(name => Object.hasOwn(MODS, name));"
    assert raw_play.count(mods_load_needle) == 1
    mods_load_patch = mods_load_needle + """
  try {
    const p = JSON.parse(localStorage.getItem('bo1z-title-preferences-v1') || '{}');
    if (p.zombieCounter || saved?.zombieCounter) {
      if (!savedMods.includes('zinfo')) savedMods.push('zinfo');
    }
  } catch {}"""
    settings_needle = "function settings() {\n  return { sensitivity: Number($('sensitivity').value), volume: Number($('volume').value), fullscreen: $('fullscreen').checked,\n    mods: modBoxes ? modBoxes.filter(box => box.checked).map(box => box.dataset.mod) : savedMods, horde: hordeSettings() };\n}"
    assert raw_play.count(settings_needle) == 1
    settings_patch = """function settings() {
  let activeMods = modBoxes ? modBoxes.filter(box => box.checked).map(box => box.dataset.mod) : savedMods;
  try {
    const p = JSON.parse(localStorage.getItem('bo1z-title-preferences-v1') || '{}');
    if (p.zombieCounter && !activeMods.includes('zinfo')) activeMods = [...activeMods, 'zinfo'];
  } catch {}
  return { sensitivity: Number($('sensitivity').value), volume: Number($('volume').value), fullscreen: $('fullscreen').checked,
    mods: activeMods, horde: hordeSettings() };
}"""
    save_needle = "try { localStorage.setItem(map.settings, JSON.stringify({ ...settings(), volumeChosen })); } catch { /* Optional preference cache. */ }"
    save_patch = """try {
    let prior = {};
    try { prior = JSON.parse(localStorage.getItem(map.settings) || '{}'); } catch {}
    localStorage.setItem(map.settings, JSON.stringify({ ...prior, ...settings(), volumeChosen }));
  } catch { /* Optional preference cache. */ }"""
    solo_play = raw_play.replace(mods_load_needle, mods_load_patch).replace(settings_needle, settings_patch).replace(save_needle, save_patch).replace("const MODS = { horde: 'Hell mode: more zombies at once', zinfo: 'Tab: zombie counter' };", "const MODS = { horde: 'Hell mode: more zombies at once', zinfo: 'On-screen Zombie & Wave Counter' };")
    coop_play = solo_play.replace("from './maps.js'", "from './coop-maps.js'").replace("from './engine.js'", "from './coop-engine.js'")
    coop_play = coop_play.replace("BASE + 'engine-download-worker.js'", "BASE + 'coop-engine-download-worker.js'")
    engine_worker = (root / 'site/bo1z/engine-download-worker.js').read_text(encoding='utf-8').replace("import('./download-worker.js')", "import('./coop-download-worker.js')")
    download_worker = (root / 'site/bo1z/download-worker.js').read_text(encoding='utf-8').replace("from './maps.js'", "from './coop-maps.js'")
    # Preserve the original browser capture body and normal native key/mouse
    # input seam; the optional adapter adds no engine/game-memory operations.
    input_source = (root / 'site/bo1z/input.js').read_text(encoding='utf-8')
    input_decl = 'export function captureInput(canvas, send, hooks = {}) {'
    if input_source.count(input_decl) != 1:
        raise ValueError('Captured input interface does not match this controller overlay')
    input_source = "import { captureWithController } from './coop/gamepad-input.js';\n" + input_source.replace(input_decl, 'function captureOriginalInput(canvas, send, hooks = {}) {')
    input_source += '\nexport function captureInput(canvas, send, hooks = {}) { return captureWithController(captureOriginalInput, canvas, send, hooks); }\n'
    result = {
        '/bo1z/maps.js': ('text/javascript', solo_maps.encode()),
        '/bo1z/play.js': ('text/javascript', solo_play.encode()),
        '/bo1z/engine.js': ('text/javascript', original_engine_patched.encode()),
        '/bo1z/input.js': ('text/javascript', input_source.encode()),
        '/bo1z/coop/gamepad-input.js': ('text/javascript', (HERE / 'gamepad-input.js').read_bytes()),
        '/bo1z/coop-engine.js': ('text/javascript', engine.encode()),
        '/bo1z/coop-maps.js': ('text/javascript', coop_maps.encode()),
        '/bo1z/coop-play.js': ('text/javascript', coop_play.encode()),
        '/bo1z/coop-engine-download-worker.js': ('text/javascript', engine_worker.encode()),
        '/bo1z/coop-download-worker.js': ('text/javascript', download_worker.encode()),
        '/bo1z/artifacts/KisakBlack-web.mjs': ('text/javascript', solo_glue.encode()),
        '/bo1z/artifacts/KisakBlack-web-coop.mjs': ('text/javascript', glue.encode()),
        '/bo1z/artifacts/KisakBlack-web-coop.wasm': ('application/wasm', (HERE / 'KisakBlack-web.wasm').read_bytes()),
    }
    for name in ('main-menu.html', 'main-menu.css', 'main-menu.js', 'lan-lobby.js'):
        mime = {'html':'text/html; charset=utf-8', 'css':'text/css', 'js':'text/javascript'}[name.rsplit('.', 1)[1]]
        result['/bo1z-coop/' + name] = (mime, (HERE / name).read_bytes())
    result['/bo1z-coop/'] = result['/bo1z-coop/main-menu.html']
    for name in ('player-profile.js', 'host-settings.js', 'ws-loader.js', 'ws-transport.js', 'peer-schema.js', 'bridge.js', 'observer.js', 'rtc-transport.js', 'resume-controller.js', 'native-admission.js', 'runtime-attestation.js', 'status.js', 'status-ui.js', 'start-gate.js', 'request-policy.js', 'lobby.js', 'lobby.css'):
        result['/bo1z/coop/' + name] = ('text/css' if name.endswith('.css') else 'text/javascript', (HERE / name).read_bytes())
    zinfo_bytes = (HERE / 'zinfo_overlay.gsc').read_bytes()
    zinfo_sha256 = hashlib.sha256(zinfo_bytes).hexdigest()
    zinfo_size = len(zinfo_bytes)
    mod_support_files = [
        'mods/_stack/maps/_modstack.gsc',
        'mods/_stack/maps/_zombiemode_ffotd.gsc',
        'mods/_stack/maps/zombie_pentagon_ffotd.gsc',
        'mods/zinfo/maps/_zombiemode_ffotd.gsc',
        'mods/zinfo/maps/zinfo/_hooks.gsc',
    ]
    mod_support_data = {
        rel: (root / 'site/bo1z/pack' / rel).read_bytes()
        for rel in mod_support_files
    }
    mod_files = {
        'mods/zinfo/maps/zinfo/_zinfo.gsc': ('text/plain; charset=utf-8', zinfo_bytes),
        **{rel: ('text/plain; charset=utf-8', data) for rel, data in mod_support_data.items()}
    }
    for slug in MAPS:
        prefix = '/bo1z/pack/' if slug == 'five' else f'/bo1z/{slug}/pack/'
        for rel_path, (mtype, data) in mod_files.items():
            result[prefix + rel_path] = (mtype, data)
        if slug == 'five':
            for rel_path, (mtype, data) in mod_files.items():
                result['/bo1z/five/pack/' + rel_path] = (mtype, data)
    for slug in MAPS:
        prefix = '/bo1z/pack/' if slug == 'five' else f'/bo1z/{slug}/pack/'
        src_classic = root / ('site/bo1z/manifest.json' if slug == 'five' else f'site/bo1z/{slug}/manifest.json')
        manifest = json.loads(src_classic.read_text(encoding='utf-8'))
        existing_paths = {f['path'] for f in manifest.get('files', [])}
        extra_files = [
            {'path': rel, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'kind': 'mod', 'priority': 'boot', 'class': 'boot'}
            for rel, data in mod_support_data.items() if rel not in existing_paths
        ]
        zinfo_rel = 'mods/zinfo/maps/zinfo/_zinfo.gsc'
        if zinfo_rel not in existing_paths:
            extra_files.append({'path': zinfo_rel, 'size': zinfo_size, 'sha256': zinfo_sha256, 'kind': 'mod', 'priority': 'boot', 'class': 'boot'})
        else:
            for f in manifest['files']:
                if f['path'] == zinfo_rel:
                    f['sha256'] = zinfo_sha256
                    f['size'] = zinfo_size
        manifest['files'] = manifest.get('files', []) + extra_files
        added_bytes = sum(f['size'] for f in extra_files)
        manifest['total_bytes'] = manifest.get('total_bytes', 0) + added_bytes
        if 'class_bytes' in manifest and 'boot' in manifest['class_bytes']:
            manifest['class_bytes']['boot'] += added_bytes
        manifest['version'] = hashlib.sha256(json.dumps(manifest['files']).encode('utf-8')).hexdigest()
        manifest_bytes = json.dumps(manifest, separators=(',', ':')).encode('utf-8')
        result[prefix + 'web-manifest-horde.json'] = ('application/json', manifest_bytes)
        result[prefix + 'manifest.json'] = ('application/json', manifest_bytes)
        if slug == 'five':
            result['/bo1z/manifest.json'] = ('application/json', manifest_bytes)
            result['/bo1z/five/manifest.json'] = ('application/json', manifest_bytes)
            result['/bo1z/five/pack/manifest.json'] = ('application/json', manifest_bytes)
            result['/bo1z/five/pack/web-manifest-horde.json'] = ('application/json', manifest_bytes)
        else:
            result[f'/bo1z/{slug}/manifest.json'] = ('application/json', manifest_bytes)
    full = json.loads((HERE / 'build-metadata.json').read_text(encoding='utf-8'))
    peer = {key: full[key] for key in full['peerGuardFields']}
    actual = hashlib.sha256(result['/bo1z/artifacts/KisakBlack-web-coop.wasm'][1]).hexdigest()
    if full.get('overlayBuildId') != BUILD:
        raise ValueError('Build identity is stale; regenerate metadata before launching')
    catalog = [{'slug':m['slug'], 'label':m['label'], 'url':'/bo1z/' + m['slug'], 'hostModes':list(m['modes'])} for m in full['maps']]
    if len(catalog) != 10 or len({m['slug'] for m in catalog}) != 10:
        raise ValueError('Expected the preserved ten-map catalog')
    result['/bo1z-coop/menu.json'] = ('application/json', json.dumps({'build':BUILD, 'soloMaps':catalog, 'multiplayer':{'mapSlug':'five','mode':'classic','experimental':True}}).encode())
    if full['baseWasmSha256'] != BASE_SHA or full['patchedWasmSha256'] != actual:
        raise ValueError('Build metadata is stale; regenerate it before launching')
    result['/bo1z/coop/peer-metadata.json'] = ('application/json', json.dumps(peer).encode())
    contexts = {'peer':peer, 'maps':[{'slug':m['slug'], 'zone':m['zone'], 'label':m['label'], 'modes':{mode:{k:v[k] for k in ('mapManifestSha256', 'mapContentSha256')} for mode,v in m['modes'].items()}} for m in full['maps']]}
    result['/bo1z/coop/contexts.json'] = ('application/json', json.dumps(contexts).encode())
    network_path = HERE / 'network-config.json'
    network = json.loads(network_path.read_text(encoding='utf-8')) if network_path.exists() else {'iceServers': [], 'iceTransportPolicy': 'all'}
    if type(network) is not dict or type(network.get('iceServers')) is not list or network.get('iceTransportPolicy') not in ('all', 'relay'):
        raise ValueError('Invalid network-config.json')
    result['/bo1z/coop/network-config.json'] = ('application/json', json.dumps(network).encode())
    result['/bo1z/coop/health.json'] = ('application/json', json.dumps({'application': 'bo1z-coop', 'build': BUILD, 'engineSha256': actual, 'archiveReadOnly': True}).encode())
    return result


def handler(root, launch_id=None, discovery_url=None):
    if discovery_url: discovery_origin(discovery_url)
    root = root.resolve()
    archive = load_archive_replay(root)
    resources = overlays(root)
    resources['/coop/health'] = ('application/json', json.dumps({'ok': True, 'service': 'bo1z-coop-assets', 'launchId': launch_id, 'build': BUILD}).encode())

    class Handler(archive.Handler):
        def respond(self, body):
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == '/bo1z-coop':
                self.send_response(302)
                self.send_header('Location', '/bo1z-coop/' + ('?' + parsed.query if parsed.query else ''))
                self.end_headers()
                return
            if path == '/bo1z/coop/':
                self.send_response(302)
                self.send_header('Location', '/bo1z/five?coop=1')
                self.end_headers()
                return
            data = resources.get(path)
            if path == '/coop/lan/rooms':
                try:
                    if not discovery_url: raise ValueError('Launch the game with launch_coop.py to enable LAN discovery')
                    with urlopen(discovery_url + '/coop/lan/rooms', timeout=2) as response:
                        content = response.read(131073)
                        if response.status != 200 or len(content) > 131072: raise ValueError('Invalid discovery response')
                        payload = json.loads(content)
                        if type(payload) is not dict or payload.get('ok') is not True or type(payload.get('rooms')) is not list: raise ValueError('Invalid discovery response')
                    data = ('application/json', content)
                except (OSError, ValueError) as error:
                    data = ('application/json', json.dumps({'ok':True, 'rooms':[], 'warnings':[str(error)[:180]], 'scannedAt':0}).encode())
            slug = path.rstrip('/').removeprefix('/bo1z/').removesuffix('.html')
            if slug in MAPS and parse_qs(parsed.query).get('coop') == ['1']:
                data = ('text/html; charset=utf-8', coop_page(root, slug))
            if data is None:
                return super().respond(body)
            mime, content = data
            self.send_response(200)
            for key, value in {'Content-Type': mime, 'Content-Length': str(len(content)),
                               'Cross-Origin-Opener-Policy': 'same-origin',
                               'Cross-Origin-Embedder-Policy': 'require-corp',
                               'Cross-Origin-Resource-Policy': 'same-origin',
                               'Cache-Control': 'no-store'}.items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                try:
                    self.wfile.write(content)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def log_message(self, *_):
            pass

    if os.name == 'nt':
        from segmented_writer import make_segmented_handler
        return make_segmented_handler(Handler)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, default=default_archive())
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--launch-id')
    parser.add_argument('--discovery-url', type=discovery_origin)
    args = parser.parse_args()
    server = CoopAssetServer(('127.0.0.1', args.port), handler(args.archive, args.launch_id, args.discovery_url))
    print(json.dumps({'application': 'bo1z-coop', 'url': f'http://127.0.0.1:{server.server_port}/bo1z-coop/', 'build': BUILD, 'archiveReadOnly': True}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
