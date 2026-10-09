#!/usr/bin/env python3
"""Experimental RAM-only BO1Z room/signaling service. Never serves game assets.

Run: python3 signaling.py --port 0
Default CORS: http://localhost:<port> and http://127.0.0.1:<port>.
Use repeatable --allow-origin to replace that default with exact origins.
Capabilities travel only in Authorization: Bearer headers, never URLs/logs.

API: POST /coop/api/rooms {metadata,transport}; POST .../{code}/join
{metadata,transport,invite?}.
Create/join return room, member, capability, cursor and leaseSeconds; create
also returns invite. Room codes are 30-bit locators, not authentication secrets.
Default code-only join is for a deliberately chosen LAN service; --require-invite
requires a separate 256-bit invitation. No TLS or external hosting is configured.

Bearer-authenticated routes: GET .../{code} (host roster), GET .../events with
?after=<cursor>&wait=0..20, POST .../signal {target,epoch,bundle}, /heartbeat {},
/ready {ready:bool,metadata,transport}, /start {metadata,transport},
/leave {}, and /close {} (host only).
All responses are JSON. Membership IDs are host/g1/g2/g3; identity and random
epoch appear in public member objects. Event cursors are private to each member.
Signals relay the RTC adapter's complete offer/answer bundle unchanged. A 409
event_cursor_expired_resync_room is a visible session fault, never silent loss.

Metadata requires exactly13 game fields used by this candidate. Rooms also pin
an explicit connection type: WebRTC (default) or experimental WebSocket relay.
Create/join require that choice, and ready/start recheck all13 fields and choice.
Relay tickets and first-frame auth bind it to exact Origin/member epoch/slot.
No mid-match switch, relay resume or silent fallback is available.
Readiness is client-declared; this service cannot verify native engine state.
Start requires at least two present members, all ready; broadcasts match-start
with increasing startEpoch. New joins are frozen after first start. Host leave
ends the room; no host migration. Clients heartbeat separately every ~10 seconds.
Guests expire after 45 seconds, host after 60 seconds, rooms after one hour.
Transient signaling and optional bounded WS packet queues exist only in RAM;
no packet persistence or gameplay state storage is provided.

Resume-lab v2: SDP bundles/hello bind generation1..3. Host POST /resume
{target,epoch} authorizes only two replacements after a started match and an
answered initial negotiation. Guest POST /resume-request {generation} requests
host review. Private resume-authorized events preserve member capability, epoch,
virtual address and startEpoch. This service cannot attest native ACTIVE state
or its timeout window; the caller must fail closed without verified admission.
"""
import argparse
import ipaddress
import collections
import copy
import base64
import hashlib
import hmac
import json
import math
import os
import socket
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from ws_relay import Relay,Rejected,websocket,MAX_WS_ROOMS,MAX_WS_SOCKETS
PROTOCOL = 'bo1z-native-rtc-resume-v2'
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
MAX_BODY = 160 * 1024
MAX_METADATA = 4096
MAX_SDP = 128 * 1024
MAX_QUEUE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 64
MAX_ROOMS = 128
GUEST_LEASE = 45
HOST_LEASE = 60
ROOM_LIFETIME = 3600
DIGESTS = ('baseWasmSha256', 'patchedWasmSha256', 'patchManifestSha256',
           'shellManifestSha256', 'mapManifestSha256', 'mapContentSha256')

class APIError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def fail(status, code):
    raise APIError(status, code)


def encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError):
        fail(400, 'invalid_json_value')


def exact_keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        fail(400, 'invalid_schema')


PEER_FIELDS = ('overlayBuildId', 'protocolVersion', 'bridgeAbiVersion', 'patchSchemaRevision', 'baseWasmSha256', 'patchedWasmSha256', 'patchManifestSha256', 'shellManifestSha256', 'mapManifestSha256', 'mapContentSha256', 'mapSlug', 'mode', 'maxPlayers')

def metadata(value):
    if type(value) is not dict or set(value) != set(PEER_FIELDS) or len(encoded(value)) > MAX_METADATA:
        fail(400, 'invalid_metadata')
    for key in PEER_FIELDS:
        item = value[key]
        if key in DIGESTS:
            valid = isinstance(item, str) and re.fullmatch('[0-9a-f]{64}', item)
        elif key == 'overlayBuildId':
            valid = item == 'bo1z-portfix-v1'
        elif key == 'mapSlug':
            valid = item == 'five'
        elif key == 'mode':
            valid = item == 'classic'
        elif key == 'maxPlayers':
            valid = type(item) is int and item == 4
        else:
            valid = type(item) is int and item == 1
        if not valid:
            fail(400, 'invalid_metadata')
    return copy.deepcopy(value)


def new_member(member_id, index, now):
    return {'id': member_id, 'role': 'host' if index == 0 else 'guest',
            'identity': {'ip': '10.0.0.' + str(index + 1), 'port': 3074},
            'epoch': secrets.token_urlsafe(16), 'capability': secrets.token_urlsafe(32),
            'engineReady': False, 'last': now, 'events': collections.deque(), 'bytes': 0, 'cursor': 0,
            'discardedThrough': 0, 'rate': collections.deque(), 'resumeAttempts': 0,
            'iceRate': collections.deque()}


class TransientICE:
    """No network calls. Optional coturn REST credentials; secret stays server-side."""
    def __init__(self, urls=(), secret=None, ttl=3600, policy='all', wall_clock=time.time, stun_urls=()):
        if type(ttl) is not int or not 60 <= ttl <= 3600 or policy not in ('all', 'relay'):
            raise ValueError('Invalid ICE lifetime or policy')
        if len(urls) > 8 or bool(urls) != bool(secret):
            raise ValueError('TURN URLs and server-only secret must be configured together')
        if secret is not None and (not isinstance(secret, str) or not 32 <= len(secret) <= 4096):
            raise ValueError('TURN secret must contain 32..4096 characters')
        for url in urls:
            match = re.fullmatch(r'turns?:([A-Za-z0-9.-]{1,253}|\[[0-9A-Fa-f:]{2,45}\])(?::([0-9]{1,5}))?(?:\?transport=(udp|tcp))?', url)
            if not match or match[2] and not 1 <= int(match[2]) <= 65535:
                raise ValueError('Invalid TURN URL')
        if policy == 'relay' and not urls:
            raise ValueError('Relay policy requires a configured TURN service')
        if not isinstance(stun_urls, (tuple, list)) or len(stun_urls) > 8 or any(not isinstance(url, str) for url in stun_urls) or len(set(stun_urls)) != len(stun_urls):
            raise ValueError('Invalid STUN URL list')
        for url in stun_urls:
            if not isinstance(url, str):
                raise ValueError('Invalid STUN URL')
            match = re.fullmatch(r'stuns?:([A-Za-z0-9.-]{1,253}|\[[0-9A-Fa-f:]{2,45}\])(?::([0-9]{1,5}))?', url)
            if not match or match[2] and not 1 <= int(match[2]) <= 65535:
                raise ValueError('Invalid STUN URL')
            host = match[1]
            try:
                if host.startswith('['):
                    ipaddress.IPv6Address(host[1:-1])
                elif re.fullmatch(r'[0-9.]+', host):
                    ipaddress.IPv4Address(host)
                elif any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in host.split('.')):
                    raise ValueError('Invalid STUN hostname')
            except ValueError:
                raise ValueError('Invalid STUN URL') from None
        self.stun_urls = tuple(stun_urls)
        self.urls, self._secret = tuple(urls), secret
        self.ttl, self.policy, self.wall_clock = ttl, policy, wall_clock

    def issue(self):
        # Round up to the credential's second granularity, so the default
        # lifetime covers the remaining one-hour room rather than ending early.
        issued = math.ceil(self.wall_clock())
        expiry = issued + self.ttl
        servers = [{'urls': list(self.stun_urls)}] if self.stun_urls else []
        if self.urls:
            # Opaque unique identifier; never embed a capability, room or IP.
            username = str(expiry) + ':' + secrets.token_urlsafe(16)
            credential = base64.b64encode(hmac.new(self._secret.encode(), username.encode(), hashlib.sha1).digest()).decode()
            servers.append({'urls': list(self.urls), 'username': username, 'credential': credential})
        return {'schemaVersion': 1, 'issuedAtMs': issued * 1000, 'expiresAtMs': expiry * 1000,
                'iceServers': servers, 'iceTransportPolicy': self.policy}


class Registry:
    def __init__(self, clock=time.monotonic, require_invite=False, ice_issuer=None):
        self.clock = clock
        self.require_invite = require_invite
        self.ice_issuer = ice_issuer or TransientICE()
        self.join_rates = collections.OrderedDict()
        self.rooms = {}
        self.create_rates = collections.OrderedDict()
        self.condition = threading.Condition(threading.RLock())
        self.relay = Relay(self)

    def public_member(self, member):
        return {k: copy.deepcopy(member[k]) for k in ('id', 'role', 'identity', 'epoch', 'engineReady')}

    def push_group(self, peers, event):
        snapshots = [(peer, peer['events'].copy(), peer['bytes'], peer['cursor'], peer['discardedThrough']) for peer in peers]
        try:
            for peer in peers:
                self.push(peer, event)
        except Exception:
            for peer, events, size, cursor, discarded in snapshots:
                peer.update(events=events, bytes=size, cursor=cursor, discardedThrough=discarded)
            raise

    def view(self, room, member):
        members = list(room['members'].values())
        if member['role'] != 'host':
            members = [m for m in members if m['role'] == 'host' or m is member]
        return {'code': room['code'], 'metadata': copy.deepcopy(room['metadata']),
                'transport': room['transport'], 'closed': room['closed'], 'startEpoch': room['startEpoch'], 'nativeStarted': room['nativeStarted'], 'members': [self.public_member(m) for m in members]}

    def joined(self, room, member, include_invite=False):
        result = {'room': self.view(room, member), 'member': self.public_member(member),
                  'capability': member['capability'], 'cursor': member['cursor'],
                  'leaseSeconds': HOST_LEASE if member['role'] == 'host' else GUEST_LEASE}
        if include_invite:
            result['invite'] = room['invite']
        return result

    def total_bytes(self):
        return sum(m['bytes'] for r in self.rooms.values() for m in r['members'].values())

    def push(self, member, event):
        event = copy.deepcopy(event)
        event['cursor'] = member['cursor'] + 1
        size = len(encoded(event))
        if size > MAX_QUEUE_BYTES:
            fail(413, 'event_too_large')
        evicted_bytes = 0
        evicted_count = 0
        for _, old_size in member['events']:
            if len(member['events']) - evicted_count < MAX_EVENTS and member['bytes'] - evicted_bytes + size <= MAX_QUEUE_BYTES:
                break
            evicted_bytes += old_size
            evicted_count += 1
        budget = MAX_TOTAL_BYTES + (0 if event.get('type') == 'signal' else 128 * 1024)
        if self.total_bytes() - evicted_bytes + size > budget:
            fail(503, 'signaling_storage_full')
        for _ in range(evicted_count):
            old, old_size = member['events'].popleft()
            member['bytes'] -= old_size
            member['discardedThrough'] = old['cursor']
        member['cursor'] += 1
        member['events'].append((event, size))
        member['bytes'] += size
        self.condition.notify_all()

    def prune(self):
        now = self.clock()
        for code, room in list(self.rooms.items()):
            host = room['members']['host']
            if now - host['last'] >= HOST_LEASE or now - room['created'] >= ROOM_LIFETIME:
                self.relay.close_room(room)
                del self.rooms[code]
                continue
            for mid, member in list(room['members'].items()):
                if mid != 'host' and now - member['last'] >= GUEST_LEASE:
                    self.relay.remove_member(room,member)
                    del room['members'][mid]
                    room['offers'].pop(mid, None)
                    self.push(host, {'type': 'member-left', 'member': self.public_member(member), 'reason': 'expired'})
        for rates in (self.create_rates, self.join_rates):
            for ip, rate in list(rates.items()):
                if not rate or now - rate[-1] > 60:
                    del rates[ip]

    def authenticate(self, room, token):
        if not isinstance(token, str) or not re.fullmatch('[A-Za-z0-9_-]{43}', token):
            fail(401, 'member_capability_required')
        for member in room['members'].values():
            if secrets.compare_digest(member['capability'], token):
                return member
        fail(401, 'invalid_member_capability')

    def rate(self, member):
        now = self.clock()
        rate = member['rate']
        while rate and now - rate[0] >= 60:
            rate.popleft()
        if len(rate) >= 120:
            fail(429, 'member_rate_limit')
        rate.append(now)

    def create(self, body, ip):
        exact_keys(body, ('metadata','transport'))
        if body['transport'] not in ('webrtc','websocket-relay'):
            fail(400,'invalid_room_transport')
        if body['transport']=='websocket-relay' and sum(r.get('transport')=='websocket-relay' and not r['closed'] for r in self.rooms.values())>=MAX_WS_ROOMS:
            fail(503,'relay_room_capacity')
        meta = metadata(body['metadata'])
        now = self.clock()
        rate = self.create_rates.setdefault(ip, collections.deque())
        while rate and now - rate[0] >= 60:
            rate.popleft()
        if len(rate) >= 10:
            fail(429, 'creation_rate_limit')
        if len(self.create_rates) > 256:
            self.create_rates.popitem(last=False)
        if len(self.rooms) >= MAX_ROOMS:
            fail(503, 'room_capacity_reached')
        rate.append(now)
        while True:
            code = ''.join(secrets.choice(ALPHABET) for _ in range(6))
            if code not in self.rooms:
                break
        host = new_member('host', 0, now)
        room = {'code': code, 'metadata': meta, 'transport':body['transport'], 'created': now, 'closed': False,
                'startEpoch': 0, 'nativeStarted': False, 'startedMembers': None, 'invite': secrets.token_urlsafe(32), 'members': {'host': host}, 'offers': {}}
        self.rooms[code] = room
        return self.joined(room, host, True)

    def join(self, room, body):
        if type(body) is not dict or set(body) not in ({'metadata','transport'}, {'invite', 'metadata','transport'}):
            fail(400, 'invalid_schema')
        if body['transport']!=room['transport']:
            fail(409,'room_transport_mismatch')
        invite = body.get('invite')
        if (self.require_invite or invite is not None) and (not isinstance(invite, str) or not re.fullmatch('[A-Za-z0-9_-]{43}', invite) or not secrets.compare_digest(room['invite'], invite)):
            fail(403, 'invalid_invite')
        meta = metadata(body['metadata'])
        if encoded(meta) != encoded(room['metadata']):
            fail(409, 'build_map_metadata_mismatch')
        if room['closed']:
            fail(410, 'room_closed')
        if room['startEpoch']:
            fail(409, 'match_already_started')
        if len(room['members']) >= room['metadata']['maxPlayers']:
            fail(409, 'room_full')
        index = next(i for i in range(1, 4) if 'g' + str(i) not in room['members'])
        member = new_member('g' + str(index), index, self.clock())
        self.push(room['members']['host'], {'type': 'member-joined', 'member': self.public_member(member)})
        room['members'][member['id']] = member
        return self.joined(room, member)

    def signal(self, room, member, body):
        exact_keys(body, ('target', 'epoch', 'bundle'))
        target = room['members'].get(body['target']) if isinstance(body['target'], str) else None
        if target is None or target is member or member['role'] == target['role']:
            fail(400, 'invalid_signal_target')
        if body['epoch'] != target['epoch']:
            fail(409, 'stale_membership_epoch')
        bundle = body['bundle']
        exact_keys(bundle, ('protocol', 'type', 'sdp', 'local', 'remote', 'metadata', 'generation'))
        signal_type = 'offer' if member['role'] == 'host' else 'answer'
        if bundle['protocol'] != PROTOCOL or bundle['type'] != signal_type:
            fail(400, 'invalid_signal_role_protocol')
        if bundle['local'] != member['identity'] or bundle['remote'] != target['identity']:
            fail(400, 'signal_identity_mismatch')
        if encoded(bundle['metadata']) != encoded(room['metadata']):
            fail(409, 'build_map_metadata_mismatch')
        sdp = bundle['sdp']
        if not isinstance(sdp, str) or not sdp.isascii() or not sdp.startswith('v=0') or len(sdp.encode()) > MAX_SDP:
            fail(400, 'invalid_sdp')
        guest = target if member['role'] == 'host' else member
        generation = bundle['generation']
        if type(generation) is not int or not 1 <= generation <= 3:
            fail(400, 'invalid_negotiation_generation')
        current = room['offers'].get(guest['id'])
        if signal_type == 'offer':
            if current is None:
                if generation != 1 or room['startEpoch']:
                    fail(409, 'resume_not_authorized')
            elif current['epoch'] != guest['epoch'] or current['generation'] != generation or current['offered']:
                fail(409, 'stale_or_duplicate_offer')
        elif current is None or current['epoch'] != guest['epoch'] or current['generation'] != generation or not current['offered'] or current['answered']:
            fail(409, 'stale_or_duplicate_answer')
        self.push(target, {'type': 'signal', 'from': member['id'], 'fromEpoch': member['epoch'],
                           'epoch': target['epoch'], 'bundle': bundle})
        if signal_type == 'offer':
            room['offers'][guest['id']] = {'epoch': guest['epoch'], 'generation': generation, 'offered': True, 'answered': False}
        else:
            current['answered'] = True
        return {'ok': True}

    def resume(self, room, member, body):
        if room['closed']:
            fail(410, 'room_closed')
        if not room['startEpoch']:
            fail(409, 'match_not_started')
        if not room['nativeStarted']:
            fail(409, 'native_start_not_settled')
        if member['role'] != 'host':
            fail(403, 'host_capability_required')
        exact_keys(body, ('target', 'epoch'))
        guest = room['members'].get(body['target']) if isinstance(body['target'], str) else None
        if guest is None or guest['role'] != 'guest':
            fail(400, 'invalid_resume_target')
        if body['epoch'] != guest['epoch']:
            fail(409, 'stale_membership_epoch')
        old = room['offers'].get(guest['id'])
        if old is None or old['epoch'] != guest['epoch'] or not old['answered']:
            fail(409, 'previous_negotiation_not_complete')
        if guest['resumeAttempts'] >= 2:
            fail(409, 'resume_attempts_exhausted')
        generation = old['generation'] + 1
        event = {'type': 'resume-authorized', 'member': self.public_member(guest), 'generation': generation,
                 'startEpoch': room['startEpoch']}
        # Both recipients and the generation form one authorization. Storage
        # failure must not publish an uncommitted generation to either peer.
        # The registry condition lock prevents readers observing this rollback.
        snapshots = [(peer, peer['events'].copy(), peer['bytes'], peer['cursor'], peer['discardedThrough'])
                     for peer in (member, guest)]
        try:
            self.push(member, event)
            self.push(guest, event)
        except Exception:
            for peer, events, size, cursor, discarded in snapshots:
                peer['events'] = events
                peer['bytes'] = size
                peer['cursor'] = cursor
                peer['discardedThrough'] = discarded
            raise
        guest['resumeAttempts'] += 1
        room['offers'][guest['id']] = {'epoch': guest['epoch'], 'generation': generation, 'offered': False, 'answered': False}
        return {'ok': True, **event}

    def request(self, method, path, body=None, token=None, ip='127.0.0.1', query=None,origin=None):
        with self.condition:
            self.prune()
            if method == 'GET' and path == '/coop/health':
                return {'ok': True, 'service': 'bo1z-local-signaling', 'protocolVersion': 1,
                        'transportProtocol': PROTOCOL, 'roomTransports':['webrtc','websocket-relay'],'gameAssets': False}
            if method == 'POST' and path == '/coop/api/rooms':
                return self.create(body, ip)
            match = re.fullmatch('/coop/api/rooms/([A-Z2-9]{6})(?:/(join|signal|events|heartbeat|leave|close|ready|start|native-started|resume-request|resume|ice|ws-ticket))?', path)
            if not match:
                fail(404, 'endpoint_not_found')
            if method == 'POST' and match[2] == 'join':
                now = self.clock()
                rate = self.join_rates.setdefault(ip, collections.deque())
                while rate and now - rate[0] >= 60:
                    rate.popleft()
                if len(rate) >= 30:
                    fail(429, 'join_rate_limit')
                rate.append(now)
                if len(self.join_rates) > 256:
                    self.join_rates.popitem(last=False)
            room = self.rooms.get(match[1])
            if room is None:
                fail(404, 'room_not_found_or_expired')
            action = match[2]
            if method == 'POST' and action == 'join':
                return self.join(room, body)
            member = self.authenticate(room, token)
            self.rate(member)
            if action == 'ws-ticket':
                if method!='POST':fail(405,'method_not_allowed')
                try:
                    metadata(body.get('metadata') if type(body)is dict else None)
                    return self.relay.ticket(room,member,body,origin)
                except Rejected:fail(403,'relay_ticket_refused')
            if action in ('signal','resume','resume-request')and room['transport']!='webrtc':
                fail(409,'room_transport_mismatch')
            if method=='POST'and action in ('ready','start'):
                keys=('ready','metadata','transport')if action=='ready'else('metadata','transport')
                exact_keys(body,keys)
                checked=metadata(body['metadata'])
                if encoded(checked)!=encoded(room['metadata'])or body['transport']!=room['transport']:
                    fail(409,'build_map_transport_mismatch')
                body={'ready':body['ready']}if action=='ready'else{}
            if action == 'ice':
                if method != 'POST':
                    fail(405, 'method_not_allowed')
                exact_keys(body, ())
                if room['closed']:
                    fail(410, 'room_closed')
                rate = member['iceRate']
                now = self.clock()
                while rate and now - rate[0] >= 60:
                    rate.popleft()
                if len(rate) >= 12:
                    fail(429, 'ice_issuance_rate_limit')
                rate.append(now)
                return self.ice_issuer.issue()
            if method == 'GET' and action is None:
                if member['role'] != 'host':
                    fail(403, 'host_capability_required')
                return {'room': self.view(room, member)}
            if method == 'GET' and action == 'events':
                query = query or {}
                if set(query) - {'after', 'wait'} or any(len(v) != 1 for v in query.values()):
                    fail(400, 'invalid_event_query')
                try:
                    after = int(query.get('after', ['0'])[0])
                    wait = float(query.get('wait', ['0'])[0])
                except (ValueError, TypeError):
                    fail(400, 'invalid_event_query')
                if after < 0 or after > member['cursor'] or not 0 <= wait <= 20:
                    fail(400, 'invalid_event_cursor_wait')
                deadline = time.monotonic() + wait
                while True:
                    if after < member['discardedThrough']:
                        fail(409, 'event_cursor_expired_resync_room')
                    events = [copy.deepcopy(e) for e, _ in member['events'] if e['cursor'] > after]
                    if events or room['closed'] or time.monotonic() >= deadline:
                        return {'events': events, 'cursor': member['cursor'], 'closed': room['closed']}
                    self.condition.wait(min(1, deadline - time.monotonic()))
                    self.prune()
                    if self.rooms.get(room['code']) is not room or room['members'].get(member['id']) is not member:
                        fail(410, 'membership_expired')
            if method != 'POST' or action not in ('signal', 'heartbeat', 'leave', 'close', 'ready', 'start', 'native-started', 'resume-request', 'resume'):
                fail(405, 'method_not_allowed')
            if action in ('close', 'heartbeat', 'leave', 'start'):
                exact_keys(body, ())
            if action == 'resume':
                return self.resume(room, member, body)
            if action == 'native-started':
                exact_keys(body, ('startEpoch',))
                if room['closed']:
                    fail(410, 'room_closed')
                if member['role'] != 'host':
                    fail(403, 'host_capability_required')
                if not room['startEpoch']:
                    fail(409, 'match_not_started')
                if type(body['startEpoch']) is not int or body['startEpoch'] != room['startEpoch']:
                    fail(409, 'stale_match_epoch')
                if room['nativeStarted']:
                    return {'ok': True, 'startEpoch': room['startEpoch'], 'nativeStarted': True}
                current = [self.public_member(m) for m in room['members'].values()]
                identity = lambda members: encoded([{k: m[k] for k in ('id', 'epoch', 'identity')} for m in members])
                if len(current) < 2 or identity(current) != identity(room['startedMembers']):
                    fail(409, 'started_membership_changed')
                self.push_group(list(room['members'].values()), {'type': 'native-started', 'startEpoch': room['startEpoch'],
                    'members': copy.deepcopy(room['startedMembers'])})
                room['nativeStarted'] = True
                return {'ok': True, 'startEpoch': room['startEpoch'], 'nativeStarted': True}
            if action == 'resume-request':
                exact_keys(body, ('generation',))
                if room['closed']:
                    fail(410, 'room_closed')
                if member['role'] != 'guest' or not room['startEpoch']:
                    fail(409, 'invalid_resume_request_phase')
                if not room['nativeStarted']:
                    fail(409, 'native_start_not_settled')
                current = room['offers'].get(member['id'])
                if type(body['generation']) is not int or current is None or current['generation'] != body['generation']:
                    fail(409, 'stale_resume_request')
                if member['resumeAttempts'] >= 2:
                    fail(409, 'resume_attempts_exhausted')
                self.push(room['members']['host'], {'type': 'resume-request', 'member': self.public_member(member), 'generation': body['generation'], 'startEpoch': room['startEpoch']})
                return {'ok': True}
            if action == 'heartbeat':
                if room['closed']:
                    fail(410, 'room_closed')
                member['last'] = self.clock()
                return {'ok': True}
            if action in ('close', 'leave'):
                if action == 'close' and member['role'] != 'host':
                    fail(403, 'host_capability_required')
                if member['role'] == 'host':
                    if not room['closed']:
                        room['closed'] = True
                        self.relay.close_room(room)
                        for peer in room['members'].values():
                            self.push(peer, {'type': 'room-closed'})
                    return {'ok': True, 'closed': True}
                self.relay.remove_member(room,member)
                del room['members'][member['id']]
                room['offers'].pop(member['id'], None)
                self.push(room['members']['host'], {'type': 'member-left', 'member': self.public_member(member), 'reason': 'left'})
                return {'ok': True}
            if room['closed']:
                fail(410, 'room_closed')
            if action == 'ready':
                exact_keys(body, ('ready',))
                if type(body['ready']) is not bool:
                    fail(400, 'ready_boolean_required')
                if body['ready'] and not self.relay.ready(room,member):
                    fail(409,'relay_not_ready')
                member['engineReady'] = body['ready']
                for peer in room['members'].values():
                    self.push(peer, {'type': 'member-ready', 'member': self.public_member(member)})
                return {'ok': True, 'member': self.public_member(member)}
            if action == 'start':
                if member['role'] != 'host':
                    fail(403, 'host_capability_required')
                if room['startEpoch']:
                    return {'ok': True, 'startEpoch': room['startEpoch']}
                if len(room['members']) < 2 or not all(peer['engineReady'] for peer in room['members'].values()):
                    fail(409, 'members_not_ready')
                members = [self.public_member(m) for m in room['members'].values()]
                try:
                    self.relay.start(room)
                    self.push_group(list(room['members'].values()), {'type': 'match-start', 'startEpoch': 1, 'members': members,'transport':room['transport'],'metadata':copy.deepcopy(room['metadata'])})
                except Rejected:
                    room['closed']=True;self.relay.close_room(room);fail(503,'relay_start_delivery_failed')
                except APIError:
                    if room['transport']=='websocket-relay':room['closed']=True;self.relay.close_room(room)
                    raise
                room['startEpoch'] = 1
                room['startedMembers'] = copy.deepcopy(members)
                return {'ok': True, 'startEpoch': room['startEpoch']}
            return self.signal(room, member, body)


class SignalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, registry=None, allowed_origins=None):
        self.registry = registry or Registry()
        self.allowed_origins = None if allowed_origins is None else frozenset(allowed_origins)
        self.workers = threading.BoundedSemaphore(48)
        self.ws_upgrades = threading.BoundedSemaphore(MAX_WS_SOCKETS)
        super().__init__(address, Handler)

    def server_bind(self):
        if os.name == 'nt':
            self.allow_reuse_address = False
            self.allow_reuse_port = False
            exclusive = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
            if exclusive is None:
                raise RuntimeError('This Python runtime lacks exclusive Windows socket binding')
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()

    def process_request(self, request, address):
        if not self.workers.acquire(blocking=False):
            try:
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.workers.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.workers.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'BO1ZSignal/1'

    def log_message(self, *args):
        pass  # No URLs, capabilities, invitations or SDP in access logs.

    def setup(self):
        super().setup()
        self.connection.settimeout(25)

    def origin(self):
        origin = self.headers.get('Origin')
        if origin is not None and self.headers.get_all('Origin') != [origin]:
            fail(403,'origin_not_allowed')
        if origin is None:
            return None
        if self.server.allowed_origins is not None:
            valid = origin in self.server.allowed_origins
        else:
            valid = re.fullmatch(r'http://(?:localhost|127\.0\.0\.1):([0-9]{1,5})', origin)
            valid = bool(valid and 1 <= int(valid[1]) <= 65535)
        if not valid:
            fail(403, 'origin_not_allowed')
        return origin

    def respond(self, status, value, origin=None):
        data = encoded(value)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Vary', 'Origin')
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(data)

    def route(self):
        origin = None
        try:
            origin = self.origin()
            if self.command=='GET'and self.path=='/coop/ws':
                return websocket(self)
            if len(self.path) > 2048:
                fail(414, 'url_too_long')
            parsed = urlsplit(self.path)
            if self.command == 'OPTIONS':
                if self.headers.get('Access-Control-Request-Method', 'POST') not in ('GET', 'POST'):
                    fail(405, 'method_not_allowed')
                self.respond(200, {'ok': True}, origin)
                return
            if self.headers.get('Transfer-Encoding'):
                fail(400, 'transfer_encoding_not_supported')
            body = None
            if self.command == 'POST':
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    fail(415, 'application_json_required')
                try:
                    size = int(self.headers.get('Content-Length', '-1'))
                except ValueError:
                    fail(400, 'invalid_content_length')
                if not 0 <= size <= MAX_BODY:
                    fail(413, 'request_too_large')
                try:
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        fail(400, 'incomplete_body')
                    body = json.loads(raw.decode('utf-8'), parse_constant=lambda _: fail(400, 'invalid_json_value'))
                except (ValueError, UnicodeError, RecursionError):
                    fail(400, 'invalid_json')
            auth = self.headers.get('Authorization', '')
            token = auth[7:] if auth.startswith('Bearer ') else None
            result = self.server.registry.request(self.command, parsed.path, body, token,
                                                  self.client_address[0], parse_qs(parsed.query, keep_blank_values=True), origin=origin)
            if parsed.path == '/coop/health':
                result['launchId'] = getattr(self.server, 'launch_id', None)
            self.respond(200, result, origin)
        except APIError as error:
            self.respond(error.status, {'error': error.code}, origin)
        except (TimeoutError, ConnectionError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            self.respond(500, {'error': 'internal_error'}, origin)

    do_GET = route
    do_POST = route
    do_OPTIONS = route


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1', help='Explicit LAN address or 0.0.0.0 to allow LAN connections')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--launch-id')
    parser.add_argument('--require-invite', action='store_true', help='Require the private invite token as well as room code for joins')
    parser.add_argument('--allow-origin', action='append', default=None, help='Exact permitted origin; repeat to replace default localhost origins')
    parser.add_argument('--stun-url', action='append', default=[], help='Optional credential-free STUN URL; no relay or paid TURN fallback')
    parser.add_argument('--turn-url', action='append', default=[], help='Optional coturn REST URL; requires server-only BO1Z_TURN_SECRET environment variable')
    parser.add_argument('--turn-ttl', type=int, default=3600, help='Transient TURN lifetime in seconds (60..3600); default covers the one-hour room')
    parser.add_argument('--ice-policy', choices=('all', 'relay'), default='all')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('port must be 0..65535')
    for origin in args.allow_origin or []:
        if not re.fullmatch(r'https?://[^/?#]+', origin) or origin == 'null':
            parser.error('allow-origin must be an exact HTTP(S) origin')
    try:
        ice_issuer = TransientICE(args.turn_url, os.environ.get('BO1Z_TURN_SECRET'), args.turn_ttl, args.ice_policy, stun_urls=args.stun_url)
    except ValueError:
        parser.error('Invalid ICE configuration; check STUN/TURN URLs, lifetime, policy and server-only TURN secret')
    server = SignalServer((args.bind, args.port), Registry(require_invite=args.require_invite, ice_issuer=ice_issuer), allowed_origins=args.allow_origin)
    server.launch_id = args.launch_id
    stop = threading.Event()
    def reaper():
        while not stop.wait(1):
            with server.registry.condition:
                server.registry.prune()
    thread = threading.Thread(target=reaper, daemon=True)
    thread.start()
    print(json.dumps({'service': 'bo1z-local-signaling', 'bind': server.server_address[0],
                      'port': server.server_address[1], 'gameAssets': False}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.registry.relay.close_all()
        server.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    main()
