#!/usr/bin/env python3
"""Check this source handoff's hashes and publication boundaries; no services.

Python 3.10+, standard library only. This verifies the checked-out release,
not game playability or redistribution rights. Git metadata and Python bytecode
caches are ignored; all other files must appear in SOURCE-SHA256SUMS.txt.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
CAPTURE_INDEX = "b370176be5786afa4e5fb2f69558a9940b288718303672b2196b4438ea020fe2"
RECIPE = "8f31cfbb516617dc08268f7ada6365ba5abdccbb88c3aa7275f383a4a7926943"
SUFFIXES = {".py", ".js", ".cjs", ".css", ".html", ".json", ".md", ".txt", ".wat", ".svg", ".yml", ".command", ".cmd"}
FILENAMES = {".gitignore", ".gitattributes", ".dockerignore", "Dockerfile", "Caddyfile"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> str:
    parts = name.split("/")
    if (not name or any(p in ("", ".", "..") for p in parts)
            or "\\" in name or ":" in name or PurePosixPath(name).is_absolute()
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError("Unsafe manifest path")
    return name


def inventory() -> dict[str, bytes]:
    files = {}
    for parent, dirs, names in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in dirs + names:
            path = Path(parent) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400):
                raise ValueError("Symlink/reparse point refused: " + path.relative_to(ROOT).as_posix())
        for name in names:
            if name.endswith(".pyc"):
                continue
            path = Path(parent) / name
            relative = safe_name(path.relative_to(ROOT).as_posix())
            if not path.is_file() or (path.suffix not in SUFFIXES and name not in FILENAMES):
                raise ValueError("Unapproved file type: " + relative)
            data = path.read_bytes()
            content = data.decode("utf-8")
            if "\x00" in content:
                raise ValueError("Binary content refused: " + relative)
            # Local account paths and credential material must not enter a release.
            if re.search(r"/Users/[A-Za-z0-9_.-]+/|[A-Z]:\\Users\\[A-Za-z0-9_.-]+\\|-----BEGIN (?:[A-Z ]*PRIVATE KEY)|gh[pousr]_[A-Za-z0-9]{20,}", content):
                raise ValueError("Private path or credential pattern: " + relative)
            if path.suffix == ".svg":
                svg = ET.fromstring(data)
                if svg.tag != "{http://www.w3.org/2000/svg}svg":
                    raise ValueError("Expected standalone SVG: " + relative)
                for element in svg.iter():
                    if element.tag.rsplit("}", 1)[-1] in ("script", "image", "foreignObject"):
                        raise ValueError("SVG must contain authored geometry/type only")
                    if any(key.startswith("on") or key.endswith("href") for key in element.attrib):
                        raise ValueError("Active/external SVG reference refused")
            files[relative] = data
    return files


def main() -> None:
    if sys.version_info < (3, 10):
        raise ValueError("Python 3.10 or newer is required")
    files = inventory()
    entries = {}
    folded = set()
    for line in files["SOURCE-SHA256SUMS.txt"].decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("Malformed source checksum line")
        pin, name = match.groups()
        safe_name(name)
        if name.casefold() in folded:
            raise ValueError("Duplicate source checksum path")
        folded.add(name.casefold())
        entries[name] = pin
    expected = set(files) - {"SOURCE-SHA256SUMS.txt"}
    if set(entries) != expected:
        raise ValueError("Source manifest differs from tree: " + ", ".join(sorted(set(entries) ^ expected)))
    for name, pin in entries.items():
        if digest(files[name]) != pin:
            raise ValueError("Source hash mismatch: " + name)
    capture = files["preservation/SHA256SUMS.capture.txt"]
    if digest(capture) != CAPTURE_INDEX or len(capture.splitlines()) != 3656:
        raise ValueError("Original capture index changed")
    if digest(files["engine/engine-recipe.json"]) != RECIPE:
        raise ValueError("Frozen engine recipe changed")
    approved = json.loads(files["approved-sources.json"])
    actual_overlay = {name.removeprefix("overlay/") for name in files if name.startswith("overlay/")}
    if len(approved) != 52 or set(approved) != actual_overlay:
        raise ValueError("Approved overlay list differs from the 52-source preview")
    for name, pin in approved.items():
        safe_name(name)
        if digest(files["overlay/" + name]) != pin:
            raise ValueError("Approved overlay source changed: " + name)
    print(json.dumps({"result": "PASS", "public_files": len(files), "source_hashes_checked": len(entries),
                      "approved_overlay_sources": len(approved), "capture_index_sha256": CAPTURE_INDEX,
                      "payload_included": False, "gameplay_validated": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        raise SystemExit("Repository check failed: " + str(error)) from None
