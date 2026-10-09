"""Deterministic room options backed by the captured Zombies/Horde scripts."""
import hashlib
import json

MAPS = frozenset(('five', 'kino', 'riese', 'nacht', 'verruckt', 'shinonuma', 'ascension', 'cotd', 'shangrila', 'moon'))
HORDE_MAPS = frozenset(('five', 'kino', 'riese', 'nacht', 'verruckt', 'shinonuma'))
FIELDS = frozenset(('mode', 'maxPlayers', 'startRound', 'enemyCount', 'counter', 'noPerks'))


def normalize_settings(value, map_slug=None):
    if type(value) is not dict or set(value) != FIELDS:
        raise ValueError('Invalid host settings schema')
    if value['mode'] not in ('classic', 'horde'):
        raise ValueError('Invalid game mode')
    for key, lower, upper in [('maxPlayers', 2, 4), ('startRound', 1, 255), ('enemyCount', 24, 1024)]:
        if type(value[key]) is not int or not lower <= value[key] <= upper:
            raise ValueError('Invalid host setting: ' + key)
    if type(value['counter']) is not bool or type(value['noPerks']) is not bool:
        raise ValueError('Host toggles must be booleans')
    if map_slug is not None and (map_slug not in MAPS or value['mode'] == 'horde' and map_slug not in HORDE_MAPS):
        raise ValueError('Map does not include the selected mode')
    result = dict(value)
    if result['mode'] == 'classic':
        result.update(startRound=1, enemyCount=128, counter=False, noPerks=False)
    return result


def default_settings(mode='classic', max_players=4):
    return normalize_settings(dict(mode=mode, maxPlayers=max_players, startRound=1, enemyCount=128, counter=False, noPerks=False))


def settings_hash(value):
    normalized = normalize_settings(value)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
