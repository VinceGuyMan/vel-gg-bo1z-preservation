#!/usr/bin/env python3
"""Bounded IPv4 LAN room discovery for the experimental BO1Z launcher.

The launcher owns this service. Browsers read it through their local asset
server; they never scan ports or receive room capabilities, invitations or ICE
credentials. UDP discovery is a hint: the normal room compatibility and join
checks still decide admission.
"""
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import ProxyHandler, build_opener

PROTOCOL = 'bo1z-lan-discovery-v1'
DISCOVERY_PORT = 28769
MAX_DATAGRAM = 12288
MAX_ROOMS = 32
SCAN_SECONDS = 0.7
CACHE_SECONDS = 3
HTTP = build_opener(ProxyHandler({}))
PUBLIC_METADATA = ('overlayBuildId', 'protocolVersion', 'bridgeAbiVersion',
                   'patchSchemaRevision', 'baseWasmSha256', 'patchedWasmSha256',
                   'patchManifestSha256', 'shellManifestSha256',
                   'mapManifestSha256', 'mapContentSha256', 'mapSlug', 'mode',
                   'maxPlayers', 'hostSettingsSha256')


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')


def private_ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
        return (address.is_private or address.is_loopback or address.is_link_local) and not (
            address.is_unspecified or address.is_multicast or address.is_reserved)
    except ValueError:
        return False


def broadcast_targets():
    """Read local IPv4 interface masks; no DNS or Internet route probe."""
    targets = {'255.255.255.255', '127.0.0.1'}
    try:
        if sys.platform == 'darwin':
            command = ['/sbin/ifconfig']
        elif sys.platform == 'win32':
            command = ['ipconfig']
        elif shutil.which('ip'):
            command = ['ip', '-4', 'address', 'show']
        else:
            return sorted(targets)
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, errors='replace')
        if sys.platform != 'win32':
            for value in re.findall(r'\b(?:broadcast|brd)\s+((?:\d{1,3}\.){3}\d{1,3})', result.stdout):
                address = ipaddress.IPv4Address(value)
                if not (address.is_loopback or address.is_multicast or address.is_unspecified):
                    targets.add(str(address))
        else:
            # IPv4 remains in Windows ipconfig labels on localized systems.
            # Its following mask line is parsed by its contiguous-mask value,
            # rather than by an English label.
            pending = None
            for line in result.stdout.splitlines():
                values = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', line)
                if 'IPv4' in line:
                    pending = values[0] if values and private_ipv4(values[0]) else None
                elif pending and values:
                    try:
                        network = ipaddress.IPv4Network(pending + '/' + values[0], strict=False)
                        if 1 <= network.prefixlen <= 30:
                            targets.add(str(network.broadcast_address))
                    except ValueError:
                        pass
                    pending = None
                elif not line.strip():
                    pending = None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return sorted(targets)[:16]


def public_room(value):
    """Copy only fields allowed in unauthenticated LAN advertisements."""
    if type(value) is not dict:
        raise ValueError('Invalid LAN room')
    code = value.get('roomCode')
    if not isinstance(code, str) or not re.fullmatch(r'[A-Z2-9]{6}', code):
        raise ValueError('Invalid LAN room code')
    meta = value.get('metadata')
    if type(meta) is not dict:
        raise ValueError('Invalid LAN metadata')
    clean = {key: meta[key] for key in PUBLIC_METADATA if key in meta}
    for key in ('overlayBuildId', 'mapSlug', 'mode'):
        if not isinstance(clean.get(key), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', clean[key]):
            raise ValueError('Invalid LAN metadata identity')
    maximum = clean.get('maxPlayers')
    if type(maximum) is not int or not 1 <= maximum <= 4:
        raise ValueError('Invalid LAN player limit')
    for key in PUBLIC_METADATA:
        if key not in clean:
            continue
        item = clean[key]
        if key.endswith('Sha256') and (not isinstance(item, str) or not re.fullmatch(r'[a-f0-9]{64}', item)):
            raise ValueError('Invalid LAN digest')
        if key in ('protocolVersion', 'bridgeAbiVersion', 'patchSchemaRevision') and (type(item) is not int or not 1 <= item <= 16):
            raise ValueError('Invalid LAN protocol revision')
    if len(encoded(clean)) > 3072:
        raise ValueError('LAN metadata too large')
    count = value.get('memberCount')
    if type(count) is not int or not 1 <= count <= maximum:
        raise ValueError('Invalid LAN member count')
    if value.get('transport') not in ('webrtc', 'websocket-relay'):
        raise ValueError('Invalid LAN transport')
    if type(value.get('started')) is not bool or type(value.get('closed')) is not bool:
        raise ValueError('Invalid LAN room state')
    result = {'roomCode': code, 'metadata': clean, 'transport': value['transport'],
              'memberCount': count, 'started': value['started'], 'closed': value['closed']}
    title = value.get('title')
    if isinstance(title, str):
        result['title'] = ''.join(c for c in title if ord(c) >= 32 and ord(c) != 127)[:64]
    settings = value.get('settings')
    if settings is not None:
        fields = {'mode', 'maxPlayers', 'startRound', 'enemyCount', 'counter', 'noPerks'}
        if type(settings) is not dict or set(settings) != fields:
            raise ValueError('Invalid LAN game settings fields')
        if settings['mode'] != clean['mode'] or type(settings['maxPlayers']) is not int or settings['maxPlayers'] != maximum:
            raise ValueError('Invalid LAN game settings identity')
        if type(settings['startRound']) is not int or not 1 <= settings['startRound'] <= 1000000 or type(settings['enemyCount']) is not int or not 0 <= settings['enemyCount'] <= 1000000:
            raise ValueError('Invalid LAN game settings numbers')
        if type(settings['counter']) is not bool or type(settings['noPerks']) is not bool:
            raise ValueError('Invalid LAN game settings flags')
        result['settings'] = dict(settings)
    return result


def parse_query(raw):
    if len(raw) > 256:
        raise ValueError('Oversized query')
    value = json.loads(raw)
    if type(value) is not dict or set(value) != {'protocol', 'kind', 'nonce'} or value['protocol'] != PROTOCOL or value['kind'] != 'query' or not isinstance(value['nonce'], str) or not re.fullmatch('[a-f0-9]{32}', value['nonce']):
        raise ValueError('Invalid LAN query')
    return value['nonce']


def parse_response(raw, source, nonce, discovery_port):
    if len(raw) > MAX_DATAGRAM or source[1] != discovery_port or not private_ipv4(source[0]):
        raise ValueError('Invalid LAN response source or size')
    value = json.loads(raw)
    if type(value) is not dict or set(value) != {'protocol', 'kind', 'nonce', 'hostId', 'signalPort', 'rooms'} or value['protocol'] != PROTOCOL or value['kind'] != 'rooms' or value['nonce'] != nonce or not isinstance(value['hostId'], str) or not re.fullmatch('[a-f0-9]{32}', value['hostId']):
        raise ValueError('Invalid LAN response')
    port = value['signalPort']
    if type(port) is not int or not 1 <= port <= 65535 or type(value['rooms']) is not list or len(value['rooms']) > 8:
        raise ValueError('Invalid LAN response fields')
    rooms = []
    for item in value['rooms']:
        room = public_room(item)
        if room['closed']:
            continue
        room['signalingUrl'] = f'http://{source[0]}:{port}'
        room['hostId'] = value['hostId']
        rooms.append(room)
    return rooms


def scan_rooms(*, targets=None, discovery_port=DISCOVERY_PORT, duration=SCAN_SECONDS):
    """Broadcast a single query; collect bounded responses on an ephemeral socket."""
    nonce = secrets.token_hex(16)
    packet = encoded({'protocol': PROTOCOL, 'kind': 'query', 'nonce': nonce})
    found, warnings = {}, []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as query:
        query.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        query.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 1)
        query.bind(('0.0.0.0', 0))
        sent = 0
        for target in (broadcast_targets() if targets is None else targets)[:16]:
            try:
                query.sendto(packet, (target, discovery_port))
                sent += 1
            except OSError:
                pass
        if not sent:
            warnings.append('LAN broadcast could not be sent. Check the network adapter or firewall; manual joining remains available.')
        deadline = time.monotonic() + min(max(duration, 0.01), SCAN_SECONDS)
        received = 0
        while received < 64 and len(found) < MAX_ROOMS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            query.settimeout(remaining)
            try:
                raw, source = query.recvfrom(MAX_DATAGRAM + 1)
                received += 1
                for room in parse_response(raw, source, nonce, discovery_port):
                    # One local host can answer through loopback and multiple
                    # adapters. Keep one row, preferring a LAN address over its
                    # loopback answer; room codes and ports remain locators.
                    key = (room['hostId'], room['roomCode'])
                    previous = found.get(key)
                    if previous is None or previous['signalingUrl'].startswith('http://127.') and not room['signalingUrl'].startswith('http://127.'):
                        found[key] = room
            except socket.timeout:
                break
            except (OSError, ValueError, UnicodeError, RecursionError):
                continue
    return sorted(found.values(), key=lambda room: (room['signalingUrl'], room['roomCode']))[:MAX_ROOMS], warnings


def signaling_rooms(signal_port):
    with HTTP.open(f'http://127.0.0.1:{signal_port}/coop/lan/rooms', timeout=0.25) as response:
        raw = response.read(131073)
        if response.status != 200 or len(raw) > 131072:
            raise ValueError('Invalid local room summary response')
        value = json.loads(raw)
        if type(value) is not dict or type(value.get('rooms')) is not list:
            raise ValueError('Invalid local room summary')
        rooms = []
        for item in value['rooms'][:MAX_ROOMS]:
            try:
                room = public_room(item)
                if not room['closed']:
                    rooms.append(room)
            except ValueError:
                continue
        return rooms


class DiscoveryHTTP(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, owner):
        self.owner = owner
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', 0), DiscoveryHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class DiscoveryHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, *args):
        pass

    def do_GET(self):
        port = self.server.server_address[1]
        if self.path != '/coop/lan/rooms' or self.headers.get('Host') != f'127.0.0.1:{port}' or self.headers.get('Origin') is not None:
            self.send_error(403, 'Local asset proxy required')
            return
        raw = encoded(self.server.owner.rooms())
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)


class LanDiscovery:
    def __init__(self, *, signal_port=None, advertise=False, discovery_port=DISCOVERY_PORT,
                 targets=None, provider=None):
        if advertise and (type(signal_port) is not int or not 1 <= signal_port <= 65535):
            raise ValueError('A LAN advertiser requires its actual signaling port')
        self.signal_port, self.advertise = signal_port, advertise
        self.host_id = secrets.token_hex(16)  # Public discovery identity, never an admission credential.
        self.discovery_port = discovery_port
        self.targets = broadcast_targets() if targets is None else targets
        self.provider = provider or (lambda: signaling_rooms(self.signal_port))
        self.warnings, self.rate = [], {}
        self.total_rate = deque()
        self.stop_event = threading.Event()
        self.scan_lock = threading.Lock()
        self.cached = None
        self.cache_time = 0
        self.udp = None
        self.udp_thread = None
        self.http = DiscoveryHTTP(self)
        self.http_thread = threading.Thread(target=self.http.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
        self.url = f'http://127.0.0.1:{self.http.server_address[1]}'

    def start(self):
        if self.advertise:
            responder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                if os.name == 'nt':
                    exclusive = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
                    if exclusive is None:
                        raise OSError('Exclusive UDP ownership unavailable')
                    responder.setsockopt(socket.SOL_SOCKET, exclusive, 1)
                responder.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 1)
                responder.bind(('0.0.0.0', self.discovery_port))
                responder.settimeout(0.2)
                self.udp = responder
                self.udp_thread = threading.Thread(target=self.respond, daemon=True)
                self.udp_thread.start()
            except OSError:
                responder.close()
                self.warnings.append(f'LAN advertising could not bind UDP {self.discovery_port}. Another host launcher or the firewall may own it. Browsing and manual joining remain available.')
        self.http_thread.start()
        return self

    def allowed(self, ip):
        now = time.monotonic()
        if not private_ipv4(ip):
            return False
        for queue in (self.total_rate, self.rate.setdefault(ip, deque())):
            while queue and now - queue[0] >= 60:
                queue.popleft()
        if len(self.rate[ip]) >= 96 or len(self.total_rate) >= 256:
            return False
        if len(self.rate) > 256:
            self.rate.pop(next(iter(self.rate)))
        self.rate[ip].append(now)
        self.total_rate.append(now)
        return True

    def respond(self):
        while not self.stop_event.is_set():
            try:
                raw, source = self.udp.recvfrom(257)
                nonce = parse_query(raw)
                if not self.allowed(source[0]):
                    continue
                rooms = []
                for item in self.provider()[:MAX_ROOMS]:
                    try:
                        room = public_room(item)
                        if not room['closed']:
                            rooms.append(room)
                    except ValueError:
                        continue
                batch = []
                for room in rooms:
                    candidate = batch + [room]
                    packet = encoded({'protocol': PROTOCOL, 'kind': 'rooms', 'nonce': nonce, 'hostId': self.host_id,
                                      'signalPort': self.signal_port, 'rooms': candidate})
                    if batch and (len(candidate) > 8 or len(packet) > MAX_DATAGRAM):
                        self.udp.sendto(encoded({'protocol': PROTOCOL, 'kind': 'rooms', 'nonce': nonce, 'hostId': self.host_id,
                                                'signalPort': self.signal_port, 'rooms': batch}), source)
                        batch = [room]
                    else:
                        batch = candidate
                if batch:
                    self.udp.sendto(encoded({'protocol': PROTOCOL, 'kind': 'rooms', 'nonce': nonce, 'hostId': self.host_id,
                                            'signalPort': self.signal_port, 'rooms': batch}), source)
            except socket.timeout:
                continue
            except (OSError, ValueError, UnicodeError, RecursionError):
                if self.stop_event.is_set():
                    break
                continue

    def rooms(self):
        with self.scan_lock:
            now = time.monotonic()
            if self.cached is None or now - self.cache_time >= CACHE_SECONDS:
                try:
                    rooms, warnings = scan_rooms(targets=self.targets, discovery_port=self.discovery_port)
                except OSError:
                    rooms, warnings = [], ['LAN scanning could not start. Check the network adapter or firewall; manual joining remains available.']
                self.cached = {'ok': True, 'protocol': PROTOCOL, 'rooms': rooms,
                               'warnings': self.warnings + warnings, 'scannedAt': time.time()}
                self.cache_time = time.monotonic()
            return self.cached

    def stop(self):
        self.stop_event.set()
        if self.http_thread.is_alive():
            self.http.shutdown()
        self.http.server_close()
        if self.udp is not None:
            self.udp.close()
        for thread in (self.http_thread, self.udp_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1)
        return not self.http_thread.is_alive() and (self.udp_thread is None or not self.udp_thread.is_alive())

    def check(self):
        if not self.http_thread.is_alive():
            raise RuntimeError('The owned LAN discovery service stopped.')
