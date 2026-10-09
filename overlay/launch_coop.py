#!/usr/bin/env python3
"""Launch the experimental local co-op package; owns only the children it starts."""
import sys

if sys.version_info < (3, 10):
    print('Python 3.10 or newer is required. Install Python from python.org, then run this launcher again.', file=sys.stderr)
    raise SystemExit(1)

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import queue
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import tempfile
import time
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import ProxyHandler, HTTPRedirectHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent
HTTP = build_opener(ProxyHandler({}))
SIGNALING_PROTOCOL = 'bo1z-native-rtc-resume-v2'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


EXTERNAL_HTTP = build_opener(ProxyHandler({}), NoRedirect())


def signaling_origin(value):
    value = value.strip()
    if not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or any(c in value for c in '?#'):
        raise RuntimeError('Use a signaling origin without credentials, query or fragment.')
    try:
        url = urlsplit(value)
        host = url.hostname
        port = url.port
        if not host or url.username is not None or url.password is not None or url.path not in ('', '/') or '%' in host:
            raise ValueError('origin')
        try:
            address = ipaddress.ip_address(host)
            loopback = address.is_loopback
            normalized_host = '[' + address.compressed + ']' if address.version == 6 else address.compressed
        except ValueError:
            normalized_host = host.encode('idna').decode('ascii').lower()
            labels = normalized_host.rstrip('.').split('.')
            if len(normalized_host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
                raise ValueError('hostname')
            loopback = normalized_host == 'localhost'
        if url.scheme not in ('https', 'http') or url.scheme == 'http' and not loopback or port is not None and not 1 <= port <= 65535:
            raise ValueError('scheme/port')
        netloc = normalized_host + (':' + str(port) if port is not None else '')
        return urlunsplit((url.scheme, netloc, '', '', ''))
    except (ValueError, UnicodeError):
        raise RuntimeError('Use an HTTPS signaling origin; HTTP is allowed only for loopback tests. No credentials, path, query or fragment.') from None


def admit_external_signaling(origin):
    # A socket timeout alone resets on each incoming byte. Bound the complete
    # response too, before any local child or browser can be started.
    outcome = queue.Queue(maxsize=1)
    def read_health():
        try:
            outcome.put((True, health(origin + '/coop/health', timeout=3, opener=EXTERNAL_HTTP)))
        except (OSError, ValueError, RuntimeError):
            outcome.put((False, None))
    threading.Thread(target=read_health, daemon=True).start()
    try:
        available, result = outcome.get(timeout=3)
    except queue.Empty:
        available, result = False, None
    if not available:
        raise RuntimeError('External signaling health could not be verified. Check its address, HTTPS certificate and availability.') from None
    if result.get('ok') is not True or result.get('service') != 'bo1z-local-signaling' or type(result.get('protocolVersion')) is not int or result.get('protocolVersion') != 2 or result.get('transportProtocol') != SIGNALING_PROTOCOL or result.get('gameAssets') is not False:
        raise RuntimeError('External signaling health does not match this package protocol.')


def archive_path(explicit=None):
    candidates = [Path(explicit).expanduser()] if explicit else [
        ROOT / 'archive', ROOT.parent / 'vel-gg-bo1z-2026-10-08',
        ROOT.parent.parent / 'outputs/vel-gg-bo1z-2026-10-08']
    for candidate in candidates:
        if (candidate / 'serve.py').is_file() and (candidate / 'site/bo1z/index.html').is_file():
            return candidate.resolve()
    raise RuntimeError('Archive not found. Keep the captured archive beside this package, or pass --archive PATH.')


def reserve_port(bind, port):
    reserved = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == 'nt':
            # Winsock SO_REUSEADDR can share a live listener. Reserve exclusive
            # ownership instead; Windows runtime/relaunch remains a separate gate.
            exclusive = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
            if exclusive is None:
                raise RuntimeError('This Python runtime cannot reserve exclusive Windows ports.')
            reserved.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        # Leave POSIX address reuse disabled during reservation. On macOS,
        # SO_REUSEADDR can admit a wildcard listener beside a live loopback
        # listener. Automatic selection also handles recently closed ports.
        reserved.bind((bind, port))
        reserved.listen(1)
        return reserved
    except RuntimeError:
        reserved.close()
        raise
    except OSError as error:
        reserved.close()
        raise RuntimeError(f'Port {port} on {bind} is unavailable. Choose another --port or --signal-port; stop any previous launcher in its own terminal.') from error


def reserve_launch_port(bind, requested, preferred):
    """Keep an exclusive reservation; automatic defaults may use a free OS port."""
    if requested is not None:
        return reserve_port(bind, requested)
    try:
        return reserve_port(bind, preferred)
    except RuntimeError as error:
        if not isinstance(error.__cause__, OSError):
            raise
    return reserve_port(bind, 0)


def health(url, timeout=0.8, opener=HTTP):
    with opener.open(url, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError('Service did not return HTTP 200')
        raw = response.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('Service health response is too large')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeError('Service health must be a JSON object')
        return result


def wait_ready(process, url, service, launch_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{service} exited before readiness (code {process.returncode}). See the message above.')
        try:
            result = health(url)
        except (OSError, ValueError, RuntimeError):
            time.sleep(0.1)
            continue
        if result.get('service') != service or result.get('launchId') != launch_id:
            raise RuntimeError(f'Unexpected service identity at {url}; refusing to reuse it.')
        if result.get('ok') is not True:
            raise RuntimeError(f'{service} reports that it is not ready.')
        if process.poll() is not None:
            raise RuntimeError(f'{service} exited while reporting readiness; refusing to admit it.')
        return
    raise RuntimeError(f'{service} did not become ready within {timeout} seconds.')


def local_lan_addresses():
    """Read local interface configuration; no Internet route probe or DNS query."""
    addresses = set()
    try:
        if sys.platform == 'darwin':
            command = ['/sbin/ifconfig']
        elif sys.platform == 'win32':
            command = ['ipconfig']
        elif shutil.which('ip'):
            command = ['ip', '-4', 'address', 'show']
        else:
            return []
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, errors='replace')
        lines = result.stdout.splitlines()
        for line in lines:
            if sys.platform == 'win32':
                # Exclude gateways/masks; Windows labels contain IPv4 even in localized output.
                if 'IPv4' not in line:
                    continue
            elif not re.search(r'\binet\s', line):
                continue
            for item in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', line):
                address = ipaddress.ip_address(item)
                if not (address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local) and not item.startswith('255.'):
                    addresses.add(item)
                    break
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return sorted(addresses)


def open_browser(url):
    if sys.platform == 'darwin':
        for base in (Path('/Applications'), Path.home() / 'Applications'):
            for name in ('Google Chrome', 'Brave Browser', 'Microsoft Edge', 'Chromium'):
                app = base / (name + '.app')
                if app.is_dir():
                    # LaunchServices has failed to open a usable Brave session
                    # in this project. The app's normal executable handles both
                    # an existing browser and a cold launch without security
                    # flags or a special browser profile.
                    executable = app / 'Contents' / 'MacOS' / name
                    if executable.is_file() and os.access(executable, os.X_OK):
                        subprocess.Popen([str(executable), url], stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         start_new_session=True)
                        return
        print('Open the game URL above in Chrome, Brave, Edge or Chromium.', flush=True)
        return
    if sys.platform == 'win32':
        for base in (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'), os.environ.get('LOCALAPPDATA')):
            if not base:
                continue
            for relative in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
                exe = Path(base) / relative
                if exe.is_file():
                    subprocess.Popen([str(exe), url])
                    return
    if not webbrowser.open(url):
        print('Open the game URL above in Chrome or Edge.', flush=True)


def stop_child(process):
    if process is None:
        return True
    # These child process groups were created here; never signal an unrelated PID.
    for sig, timeout in ((signal.SIGINT, 4), (signal.SIGTERM, 2), (getattr(signal, 'SIGKILL', 9), 2)):
        if process.poll() is not None:
            return True
        try:
            if os.name == 'nt':
                if sig == signal.SIGINT:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                elif sig == signal.SIGTERM:
                    process.terminate()
                else:
                    process.kill()
            else:
                os.killpg(process.pid, sig)
        except OSError:
            # Exits between poll and signal are normal; still wait and continue
            # cleanup of every other owned child even if one group is gone.
            pass
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            continue
    return process.poll() is not None


def child(command, *, env=None, **extra):
    options = {'cwd': str(ROOT), 'stdin': subprocess.DEVNULL}
    if env is not None:
        options['env'] = env
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options['start_new_session'] = True
    options.update(extra)
    return subprocess.Popen(command, **options)


def node_environment():
    # Per-child only: inherited Node preload/options cannot alter this replay backend.
    return {key:value for key,value in os.environ.items() if not key.upper().startswith('NODE_')}


def discover_node(explicit=None):
    value = explicit or shutil.which('node.exe') or shutil.which('node')
    if not value:
        raise RuntimeError('Windows asset delivery requires an existing Node.js 22, 24 or 26 runtime. Supply --node PATH; this launcher does not download or install it.')
    executable = Path(value).expanduser().resolve()
    if not executable.is_file() or os.name == 'nt' and executable.suffix.lower() != '.exe':
        raise RuntimeError('Use the installed node.exe executable, not a shell wrapper.')
    probe = "const fs=require('node:fs'),http=require('node:http'),s=require('node:stream');console.log(JSON.stringify({version:process.versions.node,platform:process.platform,apis:typeof fs.createReadStream==='function'&&typeof http.createServer==='function'&&typeof s.pipeline==='function'}))"
    try:
        result = subprocess.run([str(executable), '-e', probe], capture_output=True, text=True, timeout=5, check=False, env=node_environment())
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not isinstance(data.get('version'), str) or not re.fullmatch(r'\d+\.\d+\.\d+', data['version']):
            raise ValueError('runtime_schema')
        version = data['version']
        major = int(version.split('.')[0])
        if result.returncode != 0 or major not in (22, 24, 26) or data.get('apis') is not True or os.name == 'nt' and data.get('platform') != 'win32':
            raise ValueError('runtime')
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        raise RuntimeError('The supplied Node executable did not pass the supported runtime/API check.') from None
    return executable


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', help='Path to the complete captured archive')
    parser.add_argument('--port', type=int, help='Exact game port; otherwise prefer 8767 and automatically find a free port')
    parser.add_argument('--signal-port', type=int, help='Exact signaling port; otherwise prefer 8768 and automatically find a free port')
    parser.add_argument('--lan', action='store_true', help='Explicitly allow LAN connections to signaling; assets remain loopback-only')
    parser.add_argument('--signaling-url', help='Use an existing HTTPS signaling service; start only local game assets')
    parser.add_argument('--node', help='Existing Windows Node.js executable (22, 24 or 26); no installation or download')
    parser.add_argument('--free-internet-host', action='store_true', help='Opt-in temporary HTTPS lobby and free direct STUN test; no paid relay')
    parser.add_argument('--cloudflared', help='Explicit exact official cloudflared2026.10.0 MacARM64/WindowsAMD64 binary; never downloaded')
    parser.add_argument('--diagnostics-work-root', help='Explicit actual workspace work root for private Mac startup diagnostics; never outputs')
    parser.add_argument('--startup-diagnostics', help='New bounded private Mac raw startup log; unavailable on Windows pending ACL admission')
    parser.add_argument('--no-open', action='store_true', help='Start services without opening a browser')
    args = parser.parse_args(argv)
    if args.free_internet_host and (args.lan or args.signaling_url):
        parser.error('--free-internet-host owns loopback signaling; do not combine it with --lan or --signaling-url')
    if args.cloudflared and not args.free_internet_host:
        parser.error('--cloudflared requires explicit --free-internet-host')
    if bool(args.startup_diagnostics) != bool(args.diagnostics_work_root):
        parser.error('Private diagnostics require both --startup-diagnostics and --diagnostics-work-root')
    if args.startup_diagnostics and not args.free_internet_host:
        parser.error('--startup-diagnostics requires explicit --free-internet-host')
    if args.signaling_url and args.lan:
        parser.error('--signaling-url and --lan select different signaling owners; use one')
    if any(port is not None and not 1 <= port <= 65535 for port in (args.port, args.signal_port)) or (not args.signaling_url and args.port is not None and args.port == args.signal_port):
        parser.error('ports must be distinct integers between 1 and 65535')
    processes, reserved = [], []
    previous_break_handler = None
    previous_exit_handlers = {}
    snapshot = None
    registration = None
    diagnostics = None
    discovery = None
    startup_outcome = None
    result_code = 0
    try:
        if os.name != 'nt':
            for name in ('SIGTERM', 'SIGHUP'):
                value = getattr(signal, name, None)
                if value is not None:
                    previous_exit_handlers[value] = signal.getsignal(value)
                    signal.signal(value, signal.default_int_handler)
        if os.name == 'nt':
            # CTRL_BREAK produces SIGBREAK, whose default exit skips Python's
            # finally cleanup. Route it through the same owned-child shutdown
            # as Control-C, including events sent to the CMD process group.
            previous_break_handler = signal.getsignal(signal.SIGBREAK)
            signal.signal(signal.SIGBREAK, signal.default_int_handler)
        binary = None
        if args.free_internet_host:
            from free_host import verified_binary, tunnel_environment, StartupDiagnostics
            binary = verified_binary(args.cloudflared)
            if args.startup_diagnostics:
                diagnostics = StartupDiagnostics(args.startup_diagnostics, args.diagnostics_work_root, ROOT)
        archive = archive_path(args.archive)
        node = discover_node(args.node) if os.name == 'nt' else None
        if args.node and os.name != 'nt':
            raise RuntimeError('--node selects the Windows asset backend only; Mac uses the preserved Python backend.')
        remote = signaling_origin(args.signaling_url) if args.signaling_url else None
        for name in (('serve_coop.py',) if remote else ('serve_coop.py', 'signaling.py')):
            if not (ROOT / name).is_file():
                raise RuntimeError(f'Package component missing: {name}. Finish copying the package before launching.')
        if remote:
            admit_external_signaling(remote)
        signal_bind = '0.0.0.0' if args.lan else '127.0.0.1'
        reserved.append(reserve_launch_port('127.0.0.1', args.port, 8767))
        args.port = reserved[0].getsockname()[1]
        if not remote:
            reserved.append(reserve_launch_port(signal_bind, args.signal_port, 8768))
            args.signal_port = reserved[1].getsockname()[1]
        print(f'Using game port {args.port}' + (f' and signaling port {args.signal_port}.' if not remote else '.'), flush=True)
        launch_id = secrets.token_urlsafe(24)
        from lan_discovery import LanDiscovery
        # A local scanner exists for hosts and guests alike. Only the explicit
        # LAN launcher advertises its own active rooms; public/Internet rooms
        # and their private invitations never enter broadcast discovery.
        discovery = LanDiscovery(signal_port=args.signal_port if not remote else None,
                                 advertise=args.lan)
        discovery.start()
        for warning in discovery.warnings:
            print(warning, flush=True)
        # Close a reservation only when launching the corresponding child. Health
        # launchId verification protects against a competing bind in this interval.
        if node is not None:
            for name in ('export_assets.py', 'serve_assets.cjs'):
                if not (ROOT / name).is_file():
                    raise RuntimeError('Windows asset backend component missing: ' + name)
            from export_assets import export_snapshot
            snapshot = Path(tempfile.mkdtemp(prefix='bo1z-assets-owned-'))
            manifest = export_snapshot(archive, snapshot, launch_id)
            asset_command = [str(node), str(ROOT / 'serve_assets.cjs'), '--manifest', str(manifest), '--port', str(args.port),
                             '--discovery-url', discovery.url]
        else:
            asset_command = [sys.executable, '-u', str(ROOT / 'serve_coop.py'), '--port', str(args.port),
                             '--archive', str(archive), '--launch-id=' + launch_id,
                             '--discovery-url', discovery.url]
        reserved[0].close()
        assets = child(asset_command, env=node_environment()) if node is not None else child(asset_command)
        processes.append(assets)
        wait_ready(assets, f'http://127.0.0.1:{args.port}/coop/health', 'bo1z-coop-assets', launch_id)
        if not remote:
            reserved[1].close()
            signal_command = [sys.executable, '-u', str(ROOT / 'signaling.py'), '--bind', signal_bind,
                              '--port', str(args.signal_port), '--launch-id=' + launch_id]
            if args.free_internet_host:
                from free_host import STUN_URL
                # Use signaling's normal exact-loopback-origin policy. Guests
                # also select their own free asset ports; their ports need not
                # equal the host's. Invitation/ticket authentication is unchanged.
                signal_command += ['--require-invite', '--stun-url', STUN_URL]
            signals = child(signal_command, **({'env': tunnel_environment()} if args.free_internet_host else {}))
            processes.append(signals)
            wait_ready(signals, f'http://127.0.0.1:{args.signal_port}/coop/health', 'bo1z-local-signaling', launch_id)
        signaling = remote or f'http://127.0.0.1:{args.signal_port}'
        if args.free_internet_host:
            from free_host import TunnelRegistration, tunnel_command, wait_public_ready, verify_no_default_config
            print('Starting free temporary HTTPS lobby. Direct-connection test; some networks may not connect.', flush=True)
            verify_no_default_config()
            tunnel = child(tunnel_command(binary, args.signal_port), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, env=tunnel_environment())
            processes.append(tunnel)
            registration = TunnelRegistration(tunnel, diagnostics=diagnostics)
            origin, registered_at = registration.wait(processes)
            signaling = wait_public_ready(origin, registered_at, launch_id, processes,
                                           notify=lambda message: print(message, flush=True), reader=registration)
            registration.ready()
        query_values = {'signaling': signaling}
        if args.free_internet_host:
            query_values['freehost'] = '1'
        query = urlencode(query_values)
        url = f'http://127.0.0.1:{args.port}/bo1z-coop/?{query}'
        print(f'Game menu: {url}', flush=True)
        print('Keep this terminal open. Control-C stops the local services started here.', flush=True)
        if args.free_internet_host:
            print('Temporary HTTPS lobby ready. Choose Multiplayer → Host and privately share its address, room code and invite.', flush=True)
            print('Game assets stay local. Keep this terminal open. No TURN, paid fallback or game relay is enabled.', flush=True)
        elif args.lan:
            addresses = local_lan_addresses()
            print('LAN signaling enabled. Host a room in Multiplayer; friends launch their package and select it from LAN games.', flush=True)
            print('If network discovery is blocked, use one of these signaling addresses and your room code:', flush=True)
            for address in addresses:
                print(f'  http://{address}:{args.signal_port}', flush=True)
            if not addresses:
                print(f'  http://<this computer Wi-Fi/Ethernet IPv4 address>:{args.signal_port}', flush=True)
            print('Choose the address on the same network as your friends. Shared gameplay remains experimental.', flush=True)
        elif remote:
            print('External signaling protocol verified. Only local game assets were started; the external service remains independently owned.', flush=True)
        else:
            print('LAN game browsing is enabled. Use Launch LAN Host or --lan when this computer hosts a discoverable room.', flush=True)
        if not args.no_open:
            try:
                open_browser(url)
            except OSError:
                print('Browser could not open automatically. Open the game URL above in Chrome or Edge.', flush=True)
        while True:
            discovery.check()
            if registration is not None:
                registration.check_stream()
            for process in processes:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f'A co-op service stopped (code {code}). All owned launcher services will close.')
            time.sleep(0.2)
    except KeyboardInterrupt:
        print('\nStopping co-op services…', flush=True)
        result_code = 0
    except (OSError, RuntimeError, ValueError) as error:
        if registration is not None:
            registration.capture_failure('health_failed' if registration.phase == 'health' else 'startup_failed')
            startup_outcome = registration.snapshot()
            print(json.dumps({'freeHostStartup': startup_outcome}), file=sys.stderr, flush=True)
        print(f'Co-op launch failed: {error}', file=sys.stderr, flush=True)
        result_code = 1
    finally:
        cleanup_failed = False
        if discovery is not None:
            cleanup_failed = not discovery.stop()
        for process in reversed(processes):
            try:
                cleanup_failed = stop_child(process) is False or cleanup_failed
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
        for reservation in reserved:
            reservation.close()
        all_stopped = all(process.poll() is not None for process in processes)
        if not all_stopped:
            cleanup_failed = True
        if snapshot is not None and all_stopped:
            try:
                shutil.rmtree(snapshot)
            except OSError:
                cleanup_failed = True
        if previous_break_handler is not None:
            signal.signal(signal.SIGBREAK, previous_break_handler)
        for value, previous in previous_exit_handlers.items():
            signal.signal(value, previous)
        reader_complete = registration is None or registration.finish_reader()
        if not reader_complete:
            cleanup_failed = True
            if diagnostics is not None:
                diagnostics.defer_close()
        elif diagnostics is not None:
            cleanup_failed = not diagnostics.close() or cleanup_failed
        if registration is not None:
            print(json.dumps({'freeHostCleanup': registration.snapshot()}), file=sys.stderr, flush=True)
        if cleanup_failed:
            print('Owned service or asset snapshot cleanup was incomplete.', file=sys.stderr, flush=True)
            result_code = 1
    return result_code


if __name__ == '__main__':
    raise SystemExit(main())
