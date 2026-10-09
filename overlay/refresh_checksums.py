#!/usr/bin/env python3
"""Refresh this overlay's checksums; never read or write the original archive."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def package_files():
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.name == 'SHA256SUMS.txt' or '__pycache__' in relative.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Refusing a symlink/outside file: ' + str(relative))
        yield path, relative.as_posix()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    lines = [file_hash(path) + '  ' + relative for path, relative in package_files()]
    (ROOT / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Recorded {len(lines)} overlay files. Original archive untouched.')


if __name__ == '__main__':
    main()
