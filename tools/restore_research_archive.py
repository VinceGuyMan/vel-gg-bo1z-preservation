#!/usr/bin/env python3
"""Join and verify downloaded BO1Z research ZIP parts; optionally extract safely.

Python 3.10+, standard library only. Parts must sit beside their JSON manifest.
No downloading or game execution. Existing output files/folders are never replaced.
A failure after creation leaves the partial output for inspection; it is not deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile
import zlib

SCHEMA = "bo1z-research-download/v1"
CHUNK = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PARTS = 4096
MAX_BYTES = 1024**4
MAX_ZIP_ENTRIES = 100_000
HASH = re.compile(r"[0-9a-f]{64}\Z")
RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)


class RestoreError(ValueError):
    """An input or destination is unsafe or fails its integrity check."""


def _component(name: str) -> None:
    if (
        not isinstance(name, str) or not name or name in (".", "..")
        or len(name) > 255 or name.endswith((".", " "))
        or any(c in name for c in '/\\:<>"|?*')
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
        or RESERVED.fullmatch(name)
    ):
        raise RestoreError("Unsafe or nonportable file name.")


def _plain(path: Path, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise RestoreError("Symlinks and Windows reparse points are refused.")
    if not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode):
        raise RestoreError("A required path has the wrong file type.")
    return info


def _walk(path: Path, directory: bool = False) -> os.stat_result:
    for parent in reversed(path.parents):
        _plain(parent, directory=True)
    return _plain(path, directory)


def _destination(path: Path) -> None:
    _component(path.name)
    _walk(path.parent, directory=True)
    if os.path.lexists(path):
        raise RestoreError("Output already exists; choose a new destination.")


def _read_file(path: Path):
    before = _walk(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    stream = os.fdopen(descriptor, "rb")
    opened = os.fstat(stream.fileno())
    if (
        not stat.S_ISREG(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
    ):
        stream.close()
        raise RestoreError("Input changed before reading.")
    return stream, opened


def _unchanged(stream, opened: os.stat_result) -> None:
    after = os.fstat(stream.fileno())
    if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
        raise RestoreError("Input changed while reading.")


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RestoreError("Duplicate JSON key.")
        result[key] = value
    return result


def _count(value) -> bool:
    return type(value) is int and 0 < value <= MAX_BYTES


def _digest(value) -> bool:
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def read_manifest(path: Path) -> dict:
    stream, opened = _read_file(path)
    with stream:
        if opened.st_size > MAX_MANIFEST_BYTES:
            raise RestoreError("Manifest exceeds the 1 MiB limit.")
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
        _unchanged(stream, opened)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise RestoreError("Manifest exceeds the 1 MiB limit.")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise RestoreError("Unsupported manifest schema.")
    _component(data.get("archiveName"))
    if not _count(data.get("archiveBytes")) or not _digest(data.get("archiveSha256")):
        raise RestoreError("Invalid archive size or SHA-256.")
    parts = data.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        raise RestoreError("Manifest must list between 1 and 4096 parts.")
    seen = set()
    total = 0
    for part in parts:
        if not isinstance(part, dict):
            raise RestoreError("Invalid part record.")
        _component(part.get("name"))
        name = part["name"]
        if name.casefold() in seen or name.casefold() == path.name.casefold():
            raise RestoreError("Duplicate part name or manifest/part collision.")
        seen.add(name.casefold())
        if not _count(part.get("bytes")) or not _digest(part.get("sha256")):
            raise RestoreError("Invalid part size or SHA-256.")
        if _walk(path.parent / name).st_size != part["bytes"]:
            raise RestoreError(f"Part size mismatch: {name}")
        total += part["bytes"]
    if total != data["archiveBytes"]:
        raise RestoreError("Part byte counts do not equal the archive byte count.")
    return data


def _zip_members(archive: zipfile.ZipFile):
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise RestoreError("ZIP exceeds the 100,000-entry limit.")
    seen, prefixes = set(), {}
    total = 0
    members = []
    for info in infos:
        if info.orig_filename != info.filename or info.flag_bits & 1:
            raise RestoreError("NUL-containing or encrypted ZIP member refused.")
        directory = info.is_dir()
        relative = info.filename[:-1] if directory else info.filename
        parts = relative.split("/")
        for component in parts:
            _component(component)
        key = relative.casefold()
        if key in seen:
            raise RestoreError("Duplicate ZIP member, including case-only variants.")
        seen.add(key)
        mode = (info.external_attr >> 16) & 0xFFFF
        kind = stat.S_IFMT(mode)
        if (
            kind not in (0, stat.S_IFDIR if directory else stat.S_IFREG)
            or info.external_attr & 0x400
        ):
            raise RestoreError("ZIP links, reparse points or special files refused.")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            is_dir = index < len(parts) or directory
            prior = prefixes.get(prefix.casefold())
            if prior and prior != (prefix, is_dir):
                raise RestoreError("ZIP file/directory or case collision.")
            prefixes[prefix.casefold()] = (prefix, is_dir)
        if info.file_size < 0 or (directory and info.file_size != 0):
            raise RestoreError("Invalid ZIP member size.")
        total += info.file_size
        if total > MAX_BYTES:
            raise RestoreError("ZIP extraction exceeds the 1 TiB limit.")
        members.append((info, parts, directory, mode & 0o777))
    return members, total


def extract_zip(stream, target: Path) -> dict:
    with zipfile.ZipFile(stream, "r", allowZip64=True) as archive:
        members, total = _zip_members(archive)
        _destination(target)
        target.mkdir(mode=0o700)
        permissions = []
        files = 0
        for info, parts, directory, mode in members:
            destination = target
            for component in parts[:-1]:
                destination /= component
                if not os.path.lexists(destination):
                    destination.mkdir(mode=0o700)
                _plain(destination, directory=True)
            destination /= parts[-1]
            if directory:
                if not os.path.lexists(destination):
                    destination.mkdir(mode=0o700)
                _plain(destination, directory=True)
            else:
                _walk(destination.parent, directory=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                with os.fdopen(os.open(destination, flags, 0o600), "wb") as output:
                    written = 0
                    with archive.open(info, "r") as source:
                        for block in iter(lambda: source.read(CHUNK), b""):
                            written += len(block)
                            if written > info.file_size:
                                raise RestoreError("ZIP member exceeded its declared size.")
                            output.write(block)
                    if written != info.file_size:
                        raise RestoreError("ZIP member size mismatch.")
                files += 1
            if mode:
                permissions.append((destination, directory, mode))
        # Keep original execute permissions without setuid/setgid/sticky bits.
        # Apply only after all writes so permissive archive modes do not affect extraction.
        for destination, directory, mode in sorted(
            permissions, key=lambda item: (item[1], -len(item[0].parts))
        ):
            _walk(destination, directory)
            os.chmod(destination, mode)
        return {"extractedFiles": files, "extractedBytes": total}


def restore(manifest: Path, output: Path, extract: Path | None = None) -> dict:
    _destination(output)
    if extract is not None:
        _destination(extract)
        if output == extract:
            raise RestoreError("ZIP and extraction destination must differ.")
    data = read_manifest(manifest)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    _walk(output.parent, directory=True)
    with os.fdopen(os.open(output, flags, 0o600), "w+b") as joined:
        whole = hashlib.sha256()
        written = 0
        for part in data["parts"]:
            source, opened = _read_file(manifest.parent / part["name"])
            with source:
                digest = hashlib.sha256()
                size = 0
                for block in iter(lambda: source.read(CHUNK), b""):
                    size += len(block)
                    if size > part["bytes"]:
                        raise RestoreError(f"Part exceeded declared size: {part['name']}")
                    digest.update(block)
                    whole.update(block)
                    joined.write(block)
                _unchanged(source, opened)
            if size != part["bytes"] or digest.hexdigest() != part["sha256"]:
                raise RestoreError(f"Part SHA-256 or size mismatch: {part['name']}")
            written += size
        if written != data["archiveBytes"] or whole.hexdigest() != data["archiveSha256"]:
            raise RestoreError("Whole ZIP SHA-256 or size mismatch.")
        joined.flush()
        os.fsync(joined.fileno())
        result = {
            "schema": SCHEMA, "verified": True, "archiveName": data["archiveName"],
            "archiveBytes": written, "archiveSha256": whole.hexdigest(),
            "partsVerified": len(data["parts"]), "output": str(output),
        }
        if extract is not None:
            result.update(extract_zip(joined, extract))
            result["extract"] = str(extract)
        else:
            with zipfile.ZipFile(joined, "r", allowZip64=True):
                pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New reconstructed ZIP")
    parser.add_argument("--extract", type=Path, help="Optional new extraction folder")
    args = parser.parse_args()
    output = args.output.absolute()
    extract = args.extract.absolute() if args.extract is not None else None
    try:
        result = restore(args.manifest.absolute(), output, extract)
    except (RestoreError, OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile,
            RuntimeError, NotImplementedError, zlib.error, EOFError, KeyboardInterrupt) as exc:
        print(json.dumps({
            "schema": SCHEMA, "verified": False, "error": str(exc) or "Interrupted.",
            "outputExists": os.path.lexists(output),
            "extractExists": extract is not None and os.path.lexists(extract),
            "note": "Any newly created partial output remains for inspection; no existing files were replaced.",
        }))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
