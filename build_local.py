#!/usr/bin/env python3
"""Build a private BO1Z preview from reviewed sources and a local archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 or newer is required.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New local overlay directory outside the archive/source tree')
    args = parser.parse_args()
    archive = args.archive.expanduser().resolve(strict=True)
    output = args.output.expanduser().resolve()
    if output.exists() or output.is_relative_to(archive) or output.is_relative_to(ROOT) or not output.parent.is_dir():
        parser.error('Choose a new output directory outside the archive/source tree, with an existing parent.')
    approved = json.loads((ROOT / 'approved-sources.json').read_text())
    overlay = ROOT / 'overlay'
    files = {}
    for name, pin in approved.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name:
            raise ValueError('Unsafe approved source path')
        file = overlay.joinpath(*rel.parts)
        if file.is_symlink() or not file.resolve().is_relative_to(overlay) or not file.is_file():
            raise ValueError('Missing/outside source: ' + name)
        if hashlib.sha256(file.read_bytes()).hexdigest() != pin:
            raise ValueError('Edited source; restore the approved preview before building: ' + name)
        files[name] = file
    actual = {p.relative_to(overlay).as_posix() for p in overlay.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    if actual != set(files):
        raise ValueError('Overlay tree differs from the approved source list')
    base = archive / 'site/bo1z/artifacts/KisakBlack-web.wasm'
    if hashlib.sha256(base.read_bytes()).hexdigest() != '61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98':
        raise ValueError('The supplied archive is not the matching original; no output created')
    with tempfile.TemporaryDirectory(prefix='.bo1z-build-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'runtime'
        staged.mkdir()
        for name, file in files.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        commands = [
            [sys.executable, str(ROOT / 'engine/rebuild_engine.py'), '--archive-wasm', str(base), '--output', str(staged / 'KisakBlack-web.wasm')],
            [sys.executable, str(staged / 'build_metadata.py'), '--archive', str(archive)],
            [sys.executable, str(staged / 'refresh_checksums.py')],
            [sys.executable, str(staged / 'verify.py'), '--archive', str(archive), '--verify-map-content'],
        ]
        for command in commands:
            subprocess.run(command, env=env, check=True)
        # Reserve the final directory exclusively after successful validation.
        # New files also use exclusive creation, so a concurrent creator is
        # never silently replaced. An interrupted copy remains reviewable.
        output.mkdir()
        for file in sorted(staged.rglob('*')):
            target = output / file.relative_to(staged)
            if file.is_dir():
                target.mkdir(exist_ok=True)
            else:
                with file.open('rb') as source, target.open('xb') as destination:
                    shutil.copyfileobj(source, destination)
                shutil.copystat(file, target)
    print('Built private preview: ' + str(output))
    print('No game, browser or network service was launched. Original archive untouched.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit('Local build refused: ' + str(error)) from None
