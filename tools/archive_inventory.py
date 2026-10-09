#!/usr/bin/env python3
"""Read-only integrity inventory for the October 8, 2026 BO1Z capture.

Python 3.10+; standard library only. No downloads, extraction or game launch.
The known checksum index is pinned independently so replacing both a file and
its checksum does not silently create a successful preservation result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

CAPTURE_SHA256 = "b370176be5786afa4e5fb2f69558a9940b288718303672b2196b4438ea020fe2"
CAPTURE_FILES = 3656
CAPTURE_BYTES = 6351964605
MAPS = (
    ("five", "Five"), ("kino", "Kino der Toten"), ("riese", "Der Riese"),
    ("nacht", "Nacht der Untoten"), ("verruckt", "Verrückt"),
    ("shinonuma", "Shi No Numa"), ("ascension", "Ascension"),
    ("cotd", "Call of the Dead"), ("shangrila", "Shangri-La"), ("moon", "Moon"),
)
INDEXES = (
    "metadata/responses.json", "metadata/responses.jsonl",
    "metadata/transport-groups.json", "metadata/manifest-verification.json",
    "metadata/errors.json", "evidence/live-maps.json",
)


class VerificationError(ValueError):
    """A capture or path does not match the required integrity contract."""


def _plain_info(path: Path, directory: bool = False) -> os.stat_result:
    """Refuse symlinks and Windows reparse points before reading a path."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise VerificationError("Required file or directory is unavailable.") from exc
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise VerificationError("Symlinks and reparse points are refused.")
    required = stat.S_ISDIR if directory else stat.S_ISREG
    if not required(info.st_mode):
        raise VerificationError("Required path has the wrong file type.")
    return info


def _safe_path(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if (
        not relative or any(part in ("", ".", "..") for part in parts)
        or "\\" in relative or ":" in relative
        or any(ord(char) < 32 or ord(char) == 127 for char in relative)
        or PurePosixPath(relative).is_absolute()
    ):
        raise VerificationError("Unsafe checksum path.")
    current = root
    for part in parts[:-1]:
        current /= part
        _plain_info(current, directory=True)
    current /= parts[-1]
    _plain_info(current)
    return current


def _hash_file(path: Path) -> tuple[str, int]:
    before = _plain_info(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise VerificationError("File changed before it could be read.")
            digest = hashlib.sha256()
            size = 0
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
            after = os.fstat(stream.fileno())
            if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
                raise VerificationError("File changed while being read.")
            return digest.hexdigest(), size
    except OSError as exc:
        raise VerificationError("A required file could not be read.") from exc


def verify_manifest(
    root: Path,
    expected_index: str = CAPTURE_SHA256,
    expected_files: int = CAPTURE_FILES,
    expected_bytes: int = CAPTURE_BYTES,
) -> tuple[dict[str, str], int]:
    """Verify one independently pinned index; optional arguments enable fixtures."""
    _plain_info(root, directory=True)
    checksum = _safe_path(root, "SHA256SUMS.txt")
    actual, _ = _hash_file(checksum)
    if actual != expected_index:
        raise VerificationError("Checksum index does not match the preserved capture.")
    try:
        index_bytes = checksum.read_bytes()
        if hashlib.sha256(index_bytes).hexdigest() != expected_index:
            raise VerificationError("Checksum index changed before parsing.")
        lines = index_bytes.decode("utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise VerificationError("Checksum index is unreadable.") from exc
    entries: dict[str, str] = {}
    seen: set[str] = set()
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise VerificationError("Malformed checksum record.")
        digest, relative = match.groups()
        if relative.casefold() in seen:
            raise VerificationError("Duplicate checksum path.")
        seen.add(relative.casefold())
        _safe_path(root, relative)
        entries[relative] = digest
    if len(entries) != expected_files:
        raise VerificationError("Checksum index has the wrong file count.")
    total = 0
    for relative, expected in entries.items():
        actual, size = _hash_file(_safe_path(root, relative))
        if actual != expected:
            # Relative capture paths are safe to report; local machine paths are not.
            raise VerificationError(f"SHA-256 mismatch: {relative}")
        total += size
    if total != expected_bytes:
        raise VerificationError("Verified files have the wrong total byte count.")
    return entries, total


def inventory(root: Path) -> dict:
    entries, total = verify_manifest(root)

    def read_json(relative: str):
        # Every consumed metadata file was verified above against the pinned index.
        try:
            return json.loads(_safe_path(root, relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise VerificationError("Verified capture metadata is unreadable.") from exc

    responses = read_json("metadata/responses.json")
    manifests = read_json("metadata/manifest-verification.json")
    errors = read_json("metadata/errors.json")
    maps = read_json("evidence/live-maps.json")
    if len(responses) != 1808 or len(manifests) != 673 or len(errors) != 22:
        raise VerificationError("Capture metadata has an unexpected record count.")
    if {item["id"] for item in maps} != {slug for slug, _ in MAPS}:
        raise VerificationError("Captured map index does not match the ten-map snapshot.")
    return {
        "schema": "bo1z-preservation-inventory/v1",
        "origin": "https://vel.gg/bo1z/",
        "capture_date": "2026-10-08",
        "capture_timezone": "America/New_York",
        "capture_first_utc": min(item["captured_utc"] for item in responses),
        "capture_last_utc": max(item["captured_utc"] for item in responses),
        "integrity": {
            "all_listed_files_sha256_verified": True,
            "checksum_index_sha256": CAPTURE_SHA256,
            "listed_file_count": len(entries),
            "listed_file_bytes": total,
            "unlisted_files": "Not covered by the capture index; ignored.",
        },
        "captured_resources": {
            "successful_http_response_count": len(responses),
            "saved_response_body_bytes": sum(item["bytes"] for item in responses),
            "manifest_verification_record_count": len(manifests),
            "recorded_manifest_checks_all_passed": all(
                item.get("passed") is True and item.get("hash_verified") is True
                for item in manifests
            ),
            "recorded_source_error_count": len(errors),
            "recorded_source_error_statuses": sorted({str(item["status"]) for item in errors}),
        },
        "maps": [{"slug": slug, "name": name} for slug, name in MAPS],
        "capture_indexes": {relative: entries[relative] for relative in INDEXES},
        "scope": "Exact listed capture bytes; not proof of complete site history or gameplay.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path, help="Extracted original capture folder")
    args = parser.parse_args()
    try:
        result = inventory(args.archive.absolute())
    except (VerificationError, KeyError, TypeError) as exc:
        print(json.dumps({"schema": "bo1z-preservation-inventory/v1", "verified": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
