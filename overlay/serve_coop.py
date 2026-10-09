#!/usr/bin/env python3
"""Serve experimental BO1Z overlays while reading the preserved archive only."""
import argparse
import hashlib
import json
import os
import socket
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from portable_replay import load_archive_replay

HERE = Path(__file__).resolve().parent
BUILD = 'bo1z-portfix-v1'
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


def overlays(root):
    engine = (root / 'site/bo1z/engine.js').read_text(encoding='utf-8')
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
    engine = engine.replace(needle, """const devmap=args.indexOf('+devmap');
    if(devmap<0)throw Error('Experimental co-op requires a configured Zombies map');
    args.splice(devmap,0,'+set','sv_maxclients','4');
    const userRoot=args.indexOf('fs_h');
    if(userRoot>=0)args[userRoot+1]='/opfs/bo1z-portfix-v1-user';
    if(globalThis.__coopConfig?.role==='client' && !globalThis.__coopConfig?.deferJoin)
      args.splice(args.indexOf('+devmap'),2,'+connect','10.0.0.1:3074');
    state.arguments=[...args];
    if(globalThis.__coopBeforeRun)await globalThis.__coopBeforeRun(module,args);
    module.callMain(args);""")
    engine = engine.replace("'kisak-page-query'", "'bo1z-portfix-v1-page-query'")
    assert engine.count("'kisak-renderer'") == 3
    engine = engine.replace("'kisak-renderer'", "'bo1z-portfix-v1-renderer'")
    maps = (root / 'site/bo1z/maps.js').read_text(encoding='utf-8')
    needle = "opfs: m.zone === FIRST ? 'pack' : 'pack-' + m.slug"
    assert maps.count(needle) == 1
    maps = maps.replace(needle, "opfs: 'bo1z-portfix-v1-pack-' + m.slug")
    maps = maps.replace("settings: m.slug + '-settings'", "settings: 'bo1z-portfix-v1-' + m.slug + '-settings'")
    # Preserve workers' BroadcastChannel pairing after changing the page identity.
    glue = (root / 'site/bo1z/artifacts/KisakBlack-web.mjs').read_text(encoding='utf-8')
    glue = glue.replace('kisak-page-query', 'bo1z-portfix-v1-page-query')
    # Observe bytes at the original successful instantiation sites. Keep original
    # Emscripten Asyncify/TLS/worker/runtime startup and fallback paths intact.
    needle = 'var instance=await WebAssembly.instantiate(binary,imports);return instance'
    assert glue.count(needle) == 1
    glue = glue.replace(needle, 'var instance=await WebAssembly.instantiate(binary,imports);try{await Module["__coopObserveWasmBytes"]?.(binary,instance["module"],Module)}catch{}return instance')
    needle = 'var response=fetch(binaryFile,{credentials:"same-origin"});var instantiationResult=await WebAssembly.instantiateStreaming(response,imports);return instantiationResult'
    assert glue.count(needle) == 1
    glue = glue.replace(needle, 'var response=fetch(binaryFile,{credentials:"same-origin"});var observedBytes=Module["__coopObserveWasmBytes"]?response.then(r=>r.clone().arrayBuffer()).catch(()=>null):null;var instantiationResult=await WebAssembly.instantiateStreaming(response,imports);try{if(observedBytes)await Module["__coopObserveWasmBytes"](await observedBytes,instantiationResult["module"],Module)}catch{}return instantiationResult')
    # Separate URLs preserve every Solo dependency's original bytes. Keep the
    # artifact directory stable for native worker-relative asset references.
    glue = glue.replace('KisakBlack-web.mjs', 'KisakBlack-web-coop.mjs').replace('KisakBlack-web.wasm', 'KisakBlack-web-coop.wasm')
    play = (root / 'site/bo1z/play.js').read_text(encoding='utf-8')
    play = play.replace("from './maps.js'", "from './coop-maps.js'").replace("from './engine.js'", "from './coop-engine.js'")
    play = play.replace("BASE + 'engine-download-worker.js'", "BASE + 'coop-engine-download-worker.js'")
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
        '/bo1z/input.js': ('text/javascript', input_source.encode()),
        '/bo1z/coop/gamepad-input.js': ('text/javascript', (HERE / 'gamepad-input.js').read_bytes()),
        '/bo1z/coop-engine.js': ('text/javascript', engine.encode()),
        '/bo1z/coop-maps.js': ('text/javascript', maps.encode()),
        '/bo1z/coop-play.js': ('text/javascript', play.encode()),
        '/bo1z/coop-engine-download-worker.js': ('text/javascript', engine_worker.encode()),
        '/bo1z/coop-download-worker.js': ('text/javascript', download_worker.encode()),
        '/bo1z/artifacts/KisakBlack-web-coop.mjs': ('text/javascript', glue.encode()),
        '/bo1z/artifacts/KisakBlack-web-coop.wasm': ('application/wasm', (HERE / 'KisakBlack-web.wasm').read_bytes()),
    }
    for name in ('main-menu.html', 'main-menu.css', 'main-menu.js'):
        mime = {'html':'text/html; charset=utf-8', 'css':'text/css', 'js':'text/javascript'}[name.rsplit('.', 1)[1]]
        result['/bo1z-coop/' + name] = (mime, (HERE / name).read_bytes())
    result['/bo1z-coop/'] = result['/bo1z-coop/main-menu.html']
    for name in ('ws-loader.js', 'ws-transport.js', 'peer-schema.js', 'bridge.js', 'observer.js', 'rtc-transport.js', 'resume-controller.js', 'native-admission.js', 'runtime-attestation.js', 'status.js', 'status-ui.js', 'start-gate.js', 'request-policy.js', 'lobby.js', 'lobby.css'):
        result['/bo1z/coop/' + name] = ('text/css' if name.endswith('.css') else 'text/javascript', (HERE / name).read_bytes())
    full = json.loads((HERE / 'build-metadata.json').read_text(encoding='utf-8'))
    peer = {key: full[key] for key in full['peerGuardFields']}
    actual = hashlib.sha256(result['/bo1z/artifacts/KisakBlack-web-coop.wasm'][1]).hexdigest()
    if full.get('overlayBuildId') != BUILD:
        raise ValueError('Build identity is stale; regenerate metadata before launching')
    catalog = [{'slug':m['slug'], 'label':m['label'], 'url':'/bo1z/' + m['slug']} for m in full['maps']]
    if len(catalog) != 10 or len({m['slug'] for m in catalog}) != 10:
        raise ValueError('Expected the preserved ten-map catalog')
    result['/bo1z-coop/menu.json'] = ('application/json', json.dumps({'build':BUILD, 'soloMaps':catalog, 'multiplayer':{'mapSlug':'five','mode':'classic','experimental':True}}).encode())
    if full['baseWasmSha256'] != BASE_SHA or full['patchedWasmSha256'] != actual:
        raise ValueError('Build metadata is stale; regenerate it before launching')
    result['/bo1z/coop/peer-metadata.json'] = ('application/json', json.dumps(peer).encode())
    network_path = HERE / 'network-config.json'
    network = json.loads(network_path.read_text(encoding='utf-8')) if network_path.exists() else {'iceServers': [], 'iceTransportPolicy': 'all'}
    if type(network) is not dict or type(network.get('iceServers')) is not list or network.get('iceTransportPolicy') not in ('all', 'relay'):
        raise ValueError('Invalid network-config.json')
    result['/bo1z/coop/network-config.json'] = ('application/json', json.dumps(network).encode())
    result['/bo1z/coop/health.json'] = ('application/json', json.dumps({'application': 'bo1z-coop', 'build': BUILD, 'engineSha256': actual, 'archiveReadOnly': True}).encode())
    return result


def handler(root, launch_id=None):
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
                self.send_header('Location', '/bo1z/five?coop=1&renderer=webgl2')
                self.end_headers()
                return
            data = resources.get(path)
            if path.rstrip('/') in ('/bo1z/five', '/bo1z/five.html') and parse_qs(parsed.query).get('coop') == ['1']:
                page = (root / 'site/bo1z/five.html').read_text(encoding='utf-8')
                page = page.replace('</head>', '<link rel="stylesheet" href="coop/lobby.css"></head>')
                page = page.replace('<script type="module" src="play.js">', '<script type="module" src="coop/lobby.js"></script><script type="module" src="coop-play.js">')
                data = ('text/html; charset=utf-8', page.encode())
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
    args = parser.parse_args()
    server = CoopAssetServer(('127.0.0.1', args.port), handler(args.archive, args.launch_id))
    print(json.dumps({'application': 'bo1z-coop', 'url': f'http://127.0.0.1:{server.server_port}/bo1z-coop/', 'build': BUILD, 'archiveReadOnly': True}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
