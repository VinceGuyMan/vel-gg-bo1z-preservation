#!/usr/bin/env python3
"""Verify this experimental overlay and archive-backed peer identity read-only."""
import sys
if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10 or newer is required.')
import argparse
import json
from pathlib import Path
import re
from types import SimpleNamespace
from launch_coop import archive_path
from refresh_checksums import file_hash, package_files
import build_metadata

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', help='Complete original capture directory')
    parser.add_argument('--verify-map-content', action='store_true', help='Rehash selected map assets rather than reuse capture digests')
    args = parser.parse_args()
    try:
        failures, expected = [], {}
        for line in (ROOT / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
            digest, relative = line.split('  ', 1)
            if not re.fullmatch('[0-9a-f]{64}', digest) or relative in expected or '..' in Path(relative).parts or Path(relative).is_absolute():
                raise ValueError('Invalid or duplicate checksum entry')
            expected[relative] = digest
        actual = dict((relative, path) for path, relative in package_files())
        for name in sorted(set(actual) | set(expected)):
            if name not in expected:
                failures.append('Unlisted package file: ' + name)
            elif name not in actual:
                failures.append('Missing package file: ' + name)
            elif file_hash(actual[name]) != expected[name]:
                failures.append('Package digest mismatch: ' + name)
        if failures:
            raise ValueError('\n'.join(failures))
        # Check the browser's source pins independently of the package manifest.
        # A self-consistent manifest can still describe stale runtime references.
        attestation = (ROOT / 'runtime-attestation.js').read_text(encoding='utf-8')
        layout = (ROOT / 'status.js').read_text(encoding='utf-8')
        for key, name in [('bridgeSourceSha256', 'bridge.js'), ('observerSourceSha256', 'observer.js'),
                          ('nativeAdmissionSourceSha256', 'native-admission.js'), ('patchedWasmSha256', 'KisakBlack-web.wasm')]:
            actual_pin = file_hash(ROOT / name)
            for text in ([attestation, layout] if key in ('bridgeSourceSha256', 'observerSourceSha256', 'patchedWasmSha256') else [attestation]):
                match = re.search(key + r"\s*:\s*['\"]([0-9a-f]{64})['\"]", text)
                if not match or match.group(1) != actual_pin:
                    raise ValueError('Browser runtime pin mismatch: ' + key)
        archive = archive_path(args.archive)
        stored = json.loads((ROOT / 'build-metadata.json').read_text(encoding='utf-8'))
        options = SimpleNamespace(archive=archive, patch_manifest=ROOT / 'patch-manifest.json',
                                  patched_wasm=ROOT / 'KisakBlack-web.wasm', map=stored['mapSlug'],
                                  mode=stored['mode'], verify_content=args.verify_map_content, shell=[],
                                  protocol_version=stored['protocolVersion'], bridge_abi_version=stored['bridgeAbiVersion'],
                                  patch_schema_revision=stored['patchSchemaRevision'], max_players=stored['maxPlayers'])
        derived = build_metadata.generate(options)
        fields = stored['peerGuardFields']
        if fields != derived['peerGuardFields'] or any(stored.get(field) != derived.get(field) for field in fields):
            raise ValueError('Package build/map/shell metadata is stale or differs from this archive')
        if stored['compatibilitySha256'] != derived['compatibilitySha256']:
            raise ValueError('Combined peer identity mismatch')
        compile_report = json.loads((ROOT / 'compile-report.json').read_text(encoding='utf-8'))
        if compile_report.get('validated') is not True or compile_report.get('sha256') != derived['patchedWasmSha256'] or compile_report.get('bytes') != (ROOT / 'KisakBlack-web.wasm').stat().st_size:
            raise ValueError('Compiled engine report does not match actual packaged WASM')
        print(f'PASS: {len(expected)} overlay files, actual compiled engine, archive metadata, required asset sizes and peer identity.')
        print('Archive: ' + str(archive))
        print('Compatibility identity: ' + stored['compatibilitySha256'])
        print('Selected map bytes rehashed.' if args.verify_map_content else 'Large archive hashes reused from prior capture; same-size edits are not detected by this default check.')
        print('This verifies package identity, not gameplay readiness.')
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print('Verification FAILED: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
