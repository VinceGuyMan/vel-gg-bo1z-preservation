#!/usr/bin/env python3
"""Generate deterministic peer compatibility metadata; never modify archive assets.

Default: trust prior capture SHA256SUMS for large assets, validate file sizes and
re-hash small manifests/indexes plus the actual patched engine and shell files.
--verify-content re-hashes the selected map's required saved assets if needed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from host_settings import default_settings, settings_hash

LAB = Path(__file__).resolve().parent
ARCHIVE = LAB.parent / 'vel-gg-bo1z-2026-10-08'
if not ARCHIVE.is_dir():
    ARCHIVE = LAB.parents[1] / 'outputs/vel-gg-bo1z-2026-10-08'
BASE_PIN = '61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98'
SHA_RE = re.compile(r'^[a-f0-9]{64}$')


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def object_hash(value):
    """Identity serialization: sorted keys, compact UTF-8 JSON, no trailing LF."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def generate(args):
    root = args.archive.resolve()
    checksums = {}
    for line in (root / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, relative = line.split('  ', 1)
        if not SHA_RE.fullmatch(digest) or relative in checksums:
            raise ValueError('Invalid or duplicate archive checksum: ' + relative)
        checksums[relative] = digest

    def archive_path(relative):
        rel = PurePosixPath(relative)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Unsafe archive path: ' + relative)
        path = root / relative
        if not path.resolve().is_relative_to(root):
            raise ValueError('Archive path escapes capture: ' + relative)
        return path

    def read_verified(relative):
        path = archive_path(relative)
        if checksums.get(relative) != file_hash(path):
            raise ValueError('Archive metadata checksum mismatch: ' + relative)
        return json.loads(path.read_text(encoding='utf-8'))

    responses = read_verified('metadata/responses.json')
    groups = read_verified('metadata/transport-groups.json')
    verification = read_verified('metadata/manifest-verification.json')
    records = {}
    for item in responses:
        relative = item['path']
        if relative in records and (records[relative]['sha256'], records[relative]['bytes']) != (item['sha256'], item['bytes']):
            raise ValueError('Conflicting response capture: ' + relative)
        records[relative] = item
    verified_decoded = {(x['slug'], x['path'], x['suffix'], x['sha256'])
                        for x in verification if x.get('passed') and x.get('hash_verified')}
    group_index = {}
    for item in groups:
        key = (item['slug'], item['path'], item['suffix'], item['sha256'])
        if key in group_index and group_index[key]['parts'] != item['parts']:
            raise ValueError('Conflicting transport group: ' + str(key))
        group_index[key] = item

    maps_source = archive_path('site/bo1z/maps.js')
    if file_hash(maps_source) != checksums['site/bo1z/maps.js']:
        raise ValueError('Map catalog checksum mismatch')
    maps_text = maps_source.read_text(encoding='utf-8')
    map_lines = re.findall(r"\{ zone: '([^']+)', slug: '([^']+)', name: '([^']+)'([^}]+)\}", maps_text)
    if len(map_lines) != 10:
        raise ValueError('Expected original 10-map catalog; review maps.js parser')

    def fingerprint(relative, rehash=False):
        record = records.get(relative)
        expected = checksums.get(relative)
        if not record or not expected or record['sha256'] != expected or record.get('status') != 200:
            raise ValueError('Missing or inconsistent successful capture: ' + relative)
        path = archive_path(relative)
        if not path.is_file() or path.stat().st_size != record['bytes']:
            raise ValueError('Required saved asset missing or wrong size: ' + relative)
        if rehash and file_hash(path) != expected:
            raise ValueError('Required saved asset SHA256 mismatch: ' + relative)
        return {'path': relative.removeprefix('site/'), 'bytes': record['bytes'], 'sha256': expected}

    def map_content(zone, slug, mode):
        directory = 'site/bo1z/' + ('' if slug == 'five' else slug + '/')
        relative = directory + ('manifest.json' if mode == 'classic' else 'pack/web-manifest-horde.json')
        manifest = read_verified(relative)
        if manifest['map'] != zone:
            raise ValueError('Map zone mismatch: ' + relative)
        assets = {}
        decoded = []
        selected_rehash = args.verify_content and slug == args.map and mode == args.mode
        def add(path):
            assets[path] = fingerprint(path, selected_rehash)
        add(relative)
        for entry in manifest['files']:
            path = entry['path']
            if not isinstance(path, str) or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
                raise ValueError('Unsafe game pack path')
            variants = [(('.kop' if entry.get('opus') else '.dxs' if entry.get('dxs') else ''), entry)]
            if entry.get('fallback'):
                variants.append(('', entry['fallback']))
            for suffix, descriptor in variants:
                digest = descriptor['sha256']
                if not SHA_RE.fullmatch(digest):
                    raise ValueError('Invalid content digest: ' + path)
                key = (slug, path, suffix, digest)
                if descriptor.get('br'):
                    group = group_index.get(key)
                    if not group or len(group['parts']) != len(descriptor['br']):
                        raise ValueError('Missing exact transport group: ' + str(key))
                    for part in group['parts']:
                        add('site/' + part)
                else:
                    local = directory + 'pack/' + path + suffix
                    add(local)
                    if assets[local]['sha256'] != digest:
                        raise ValueError('Loose file disagrees with manifest: ' + local)
                decoded.append({'path': path, 'transportSuffix': suffix, 'sha256': digest,
                                'size': descriptor['size'],
                                'decodedVerification': 'prior capture verified' if key in verified_decoded
                                else 'manifest declared; saved bytes fingerprinted'})
        for entry in manifest.get('streams', []):
            local = directory + 'pack/' + entry['path']
            add(local)
            if assets[local]['sha256'] != entry['sha256']:
                raise ValueError('Stream digest disagrees with manifest: ' + local)
        optional = []
        for kind in ['programs', 'pipelines']:
            local = 'site/bo1z/artifacts/' + slug + '-' + kind + '.json'
            if local in records:
                add(local)
                optional.append({'kind': kind, 'present': True})
            else:
                optional.append({'kind': kind, 'present': False, 'behavior': 'original engine accepts 404'})
        identities = sorted(assets.values(), key=lambda x: x['path'])
        payload = {'identitySchema': 1, 'mapSlug': slug, 'mapZone': zone, 'mode': mode,
                   'manifestSha256': checksums[relative], 'assets': identities, 'optionalArtifacts': optional}
        return {'mode': mode, 'mapManifestPath': relative.removeprefix('site/'),
                'mapManifestSha256': checksums[relative], 'mapContentSha256': object_hash(payload),
                'manifestVersion': manifest['version'], 'assetCount': len(identities),
                'savedBytes': sum(x['bytes'] for x in identities), 'assets': identities,
                'decodedContent': sorted(decoded, key=lambda x: (x['path'], x['transportSuffix'])),
                'optionalArtifacts': optional}

    catalog = []
    for zone, slug, label, tail in map_lines:
        modes = ['classic'] + (['horde'] if 'horde: true' in tail else [])
        catalog.append({'slug': slug, 'zone': zone, 'label': label,
                        'modes': {mode: map_content(zone, slug, mode) for mode in modes}})
    selected = next((x for x in catalog if x['slug'] == args.map), None)
    if not selected or args.mode not in selected['modes']:
        raise ValueError('Selected map/mode is not in archived map catalog')
    map_identity = selected['modes'][args.mode]

    patch_path = args.patch_manifest.resolve()
    patch = json.loads(patch_path.read_text(encoding='utf-8'))
    base = patch.get('base_sha256')
    if base != BASE_PIN or checksums.get('site/bo1z/artifacts/KisakBlack-web.wasm') != base:
        raise ValueError('Patch base does not match original archived engine pin')
    patched_hash = file_hash(args.patched_wasm)
    # Small source files are actually hashed, not assumed equal to the prior capture.
    shell_paths = {'archive/' + p.relative_to(root / 'site').as_posix(): p
                   for p in (root / 'site/bo1z').iterdir() if p.is_file() and p.suffix in ('.js', '.html', '.css')}
    shell_paths['archive/serve.py'] = root / 'serve.py'
    shell_paths['archive/bo1z/artifacts/KisakBlack-web.mjs'] = root / 'site/bo1z/artifacts/KisakBlack-web.mjs'
    for name in ['player_profile.py', 'player-profile.js', 'host_settings.py', 'host-settings.js', 'lan_discovery.py', 'lan-lobby.js', 'gamepad-input.js', 'ws-loader.js', 'ws-transport.js', 'ws_wire.py', 'ws_relay.py', 'peer-schema.js', 'bridge.js', 'rtc-transport.js', 'resume-controller.js', 'native-admission.js', 'runtime-attestation.js', 'status.js', 'status-ui.js', 'start-gate.js', 'request-policy.js', 'observer.js', 'lobby.js', 'lobby.css', 'serve_coop.py', 'export_assets.py', 'serve_assets.cjs', 'segmented_writer.py', 'portable_replay.py', 'launch_coop.py', 'free_host.py', 'signaling.py', 'ice_issuer.py', 'main-menu.html', 'main-menu.css', 'main-menu.js', 'network-config.json', 'build_metadata.py', 'verify.py', 'refresh_checksums.py', 'Launch Game.command', 'Launch Game.cmd', 'Launch Co-op.command', 'Launch Co-op.cmd', 'Launch LAN Host.command', 'Launch LAN Host.cmd', 'Launch Free Internet Host.command', 'Launch Free Internet Host.cmd']:
        if (LAB / name).is_file():
            shell_paths['coop/' + name] = LAB / name
    for value in args.shell:
        name, separator, path = value.partition('=')
        if not separator or not name or name.startswith('/') or '..' in PurePosixPath(name).parts:
            raise ValueError('--shell must be stable LOGICAL_NAME=PATH')
        shell_paths[name] = Path(path).resolve()
    shell = [{'path': name, 'bytes': path.stat().st_size, 'sha256': file_hash(path)}
             for name, path in sorted(shell_paths.items())]
    result = {'schemaVersion': 1, 'overlayBuildId': 'bo1z-lan-lobby-v2', 'protocolVersion': args.protocol_version,
              'bridgeAbiVersion': args.bridge_abi_version, 'patchSchemaRevision': args.patch_schema_revision,
              'baseWasmSha256': base, 'patchedWasmSha256': patched_hash,
              'patchManifestSha256': file_hash(patch_path), 'patchBuildId': patch.get('build_id'),
              'shellManifestSha256': object_hash(shell),
              'mapManifestSha256': map_identity['mapManifestSha256'],
              'mapContentSha256': map_identity['mapContentSha256'], 'mapSlug': args.map,
              'mapZone': selected['zone'], 'mapLabel': selected['label'], 'mode': args.mode,
              'maxPlayers': args.max_players, 'hostSettingsSha256': settings_hash(default_settings(args.mode, args.max_players)), 'shell': shell, 'maps': catalog,
              'provenance': {'assetHashSource': 'archive SHA256SUMS.txt cross-checked against capture responses.json',
                             'assetValidation': 'selected map content rehashed' if args.verify_content
                             else 'prior capture hashes reused; current existence/byte lengths checked',
                             'metadataValidation': 'indexes, map catalog and manifests rehashed now',
                             'engineAndShellValidation': 'actual patched WASM, patch manifest and shell rehashed now',
                             'archiveChecksumIndexSha256': file_hash(root / 'SHA256SUMS.txt'),
                             'identityEncoding': 'SHA256 of sorted-key compact UTF-8 JSON without trailing newline'},
              'limitations': ['Matching identities admit only the same experimental package; they do not prove gameplay compatibility.',
                              'Default asset validation detects absence/size changes, not same-size edits since capture. Use --verify-content for selected-map current-byte verification.',
                              'Include every final served overlay/UI/transport source using --shell LOGICAL_NAME=PATH and regenerate after any build change.',
                              'Horde identities describe archived content availability; co-op gameplay validation is separate.']}
    guard = ['overlayBuildId', 'protocolVersion', 'bridgeAbiVersion', 'patchSchemaRevision', 'baseWasmSha256',
             'patchedWasmSha256', 'patchManifestSha256', 'shellManifestSha256',
             'mapManifestSha256', 'mapContentSha256', 'mapSlug', 'mode', 'maxPlayers', 'hostSettingsSha256']
    result['peerGuardFields'] = guard
    result['compatibilitySha256'] = object_hash({key: result[key] for key in guard})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--patched-wasm', type=Path, default=LAB / 'KisakBlack-web.wasm')
    parser.add_argument('--patch-manifest', type=Path, default=LAB / 'patch-manifest.json')
    parser.add_argument('--output', type=Path, default=LAB / 'build-metadata.json')
    parser.add_argument('--map', default='five')
    parser.add_argument('--mode', choices=['classic', 'horde'], default='classic')
    parser.add_argument('--protocol-version', type=int, default=2)
    parser.add_argument('--bridge-abi-version', type=int, default=1)
    parser.add_argument('--patch-schema-revision', type=int, default=1)
    parser.add_argument('--max-players', type=int, choices=[2, 3, 4], default=4)
    parser.add_argument('--shell', action='append', default=[], metavar='LOGICAL_NAME=PATH')
    parser.add_argument('--verify-content', action='store_true')
    args = parser.parse_args()
    if min(args.protocol_version, args.bridge_abi_version, args.patch_schema_revision) < 1:
        parser.error('Protocol, ABI and patch schema revisions must be positive')
    try:
        result = generate(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'Compatibility metadata refused: ' + str(error) + '\n')
    output = args.output.resolve()
    if output.is_relative_to(args.archive.resolve()):
        parser.exit(1, 'Refusing to write into original archive\n')
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ['mapSlug', 'mode', 'compatibilitySha256', 'patchedWasmSha256']}))


if __name__ == '__main__':
    main()
