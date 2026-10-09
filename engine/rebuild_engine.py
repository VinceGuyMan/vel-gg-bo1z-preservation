#!/usr/bin/env python3
"""Reconstruct one exact experimental engine from an independently supplied archive.

Python standard library only. This does not compile or execute the game. No
archive file is changed, no artifact is downloaded, and output must be new.
"""
import argparse
import hashlib
import json
from pathlib import Path

BASE_SHA256 = "61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98"
TARGET_SHA256 = "29c436447d467e63ae05346bdb5ed53c5f79ce0ab5e7493148200797b7129628"
RECIPE_SHA256 = "8f31cfbb516617dc08268f7ada6365ba5abdccbb88c3aa7275f383a4a7926943"
MAX_RECIPE_BYTES = 262144
MAX_TARGET_BYTES = 10000000


class RebuildError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def uleb(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise RebuildError("Invalid unsigned 32-bit value")
    result = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


def read_uleb(data, offset):
    start, value = offset, 0
    for shift in range(0, 35, 7):
        if offset >= len(data):
            raise RebuildError("Truncated WASM integer")
        byte = data[offset]
        offset += 1
        if shift == 28 and byte > 15:
            raise RebuildError("WASM integer exceeds 32 bits")
        value |= (byte & 127) << shift
        if byte < 128:
            if data[start:offset] != uleb(value):
                raise RebuildError("Noncanonical WASM integer")
            return value, offset
    raise RebuildError("Invalid WASM integer")


def inspect_sections(data):
    if data[:8] != b"\0asm\1\0\0\0":
        raise RebuildError("Not a WASM v1 binary")
    offset, seen, result = 8, set(), []
    while offset < len(data):
        kind = data[offset]
        length, payload = read_uleb(data, offset + 1)
        end = payload + length
        if end > len(data) or kind > 13 or kind != 0 and kind in seen:
            raise RebuildError("Invalid or truncated WASM section")
        seen.add(kind)
        result.append((kind, offset, payload, end))
        offset = end
    return result


def load_recipe(data, expected_sha=RECIPE_SHA256):
    if not 0 < len(data) <= MAX_RECIPE_BYTES:
        raise RebuildError("Recipe size is outside the fixed bound")
    if sha(data) != expected_sha:
        raise RebuildError("Recipe SHA256 mismatch")
    try:
        recipe = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise RebuildError("Recipe is not valid JSON") from exc
    if not isinstance(recipe, dict) or recipe.get("schemaVersion") != 1:
        raise RebuildError("Unsupported recipe schema")
    if recipe.get("baseSha256") != BASE_SHA256 or recipe.get("targetSha256") != TARGET_SHA256:
        raise RebuildError("Recipe engine identity mismatch")
    return recipe


def name_local_maps(count, entries):
    if type(count) is not int or count != 11702 or not isinstance(entries, dict):
        raise RebuildError("Invalid local-name map identity")
    result = bytearray(uleb(count))
    if set(entries) != {str(i) for i in range(11695, 11702)}:
        raise RebuildError("Unexpected helper local-name map")
    for index in range(count):
        names = entries.get(str(index), [])
        if not isinstance(names, list) or len(names) > 16:
            raise RebuildError("Invalid helper name count")
        result.extend(uleb(index))
        result.extend(uleb(len(names)))
        for local, name in enumerate(names):
            if not isinstance(name, str) or not name.isascii() or not name.isidentifier() or len(name) > 32:
                raise RebuildError("Invalid helper name")
            encoded = name.encode("ascii")
            result.extend(uleb(local) + uleb(len(encoded)) + encoded)
    return bytes(result)


def name_functions(original, bounds, appended):
    if not isinstance(bounds, list) or len(bounds) != 2 or any(type(x) is not int for x in bounds):
        raise RebuildError("Invalid function-name source range")
    start, length = bounds
    if start < 0 or length <= 0 or start + length > len(original):
        raise RebuildError("Function-name source range exceeds archive")
    data = original[start:start + length]
    count, pos = read_uleb(data, 0)
    if count != 11693 or not isinstance(appended, list) or len(appended) != 9:
        raise RebuildError("Function-name identity mismatch")
    allowed = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'*+./:<=>?@\\^_`|~-"
    result = bytearray(uleb(count + len(appended)))
    for index in range(count):
        actual, pos = read_uleb(data, pos)
        size, pos = read_uleb(data, pos)
        if actual != index or pos + size > len(data):
            raise RebuildError("Invalid original function-name map")
        # Reproduce wasm2wat's identifier spelling used by the reviewed proof8
        # rebuild. Original symbol strings are supplied solely by the archive.
        name = bytes(char if char in allowed else 95 for char in data[pos:pos + size])
        pos += size
        result.extend(uleb(index) + uleb(len(name)) + name)
    if pos != len(data):
        raise RebuildError("Trailing function-name source bytes")
    for index, text in enumerate(appended, count):
        if not isinstance(text, str) or not text.startswith("Coop_") or not text.isascii() or not text.isidentifier() or len(text) > 64:
            raise RebuildError("Invalid appended helper function name")
        name = text.encode("ascii")
        result.extend(uleb(index) + uleb(len(name)) + name)
    return b"\1" + uleb(len(result)) + bytes(result)


def render(parts, original, depth=0):
    if not isinstance(parts, list) or len(parts) > 4096 or depth > 4:
        raise RebuildError("Invalid or excessive recipe operations")
    result = bytearray()
    for part in parts:
        if not isinstance(part, dict):
            raise RebuildError("Invalid recipe operation")
        keys = set(part)
        if keys == {"copy"}:
            bounds = part["copy"]
            if not isinstance(bounds, list) or len(bounds) != 2:
                raise RebuildError("Invalid copy range")
            offset, length = bounds
            if any(type(x) is not int for x in bounds) or offset < 0 or length <= 0 or offset + length > len(original):
                raise RebuildError("Copy range is outside the verified archive")
            value = original[offset:offset + length]
        elif keys == {"hex"}:
            text = part["hex"]
            if not isinstance(text, str) or len(text) > MAX_RECIPE_BYTES or len(text) % 2:
                raise RebuildError("Invalid inserted bytes")
            try:
                value = bytes.fromhex(text)
            except ValueError as exc:
                raise RebuildError("Invalid inserted bytes") from exc
        elif keys == {"section", "parts"}:
            kind = part["section"]
            if type(kind) is not int or not 0 <= kind <= 13:
                raise RebuildError("Invalid section id")
            payload = render(part["parts"], original, depth + 1)
            value = bytes([kind]) + uleb(len(payload)) + payload
        elif keys == {"locals", "entries"}:
            payload = name_local_maps(part["locals"], part["entries"])
            value = b"\2" + uleb(len(payload)) + payload
        elif keys == {"functionNames", "append"}:
            value = name_functions(original, part["functionNames"], part["append"])
        else:
            raise RebuildError("Unsupported recipe operation")
        result.extend(value)
        if len(result) > MAX_TARGET_BYTES:
            raise RebuildError("Rebuild output exceeds the fixed bound")
    return bytes(result)


def rebuild(original, recipe):
    if len(original) != 9618325 or sha(original) != BASE_SHA256:
        raise RebuildError("Archive WASM SHA256/size mismatch; archive is untouched")
    inspect_sections(original)
    if recipe.get("baseBytes") != len(original) or recipe.get("targetBytes") != 9655130:
        raise RebuildError("Recipe byte-count identity mismatch")
    if recipe.get("schemaVersion") != 1 or recipe.get("baseSha256") != BASE_SHA256 or recipe.get("targetSha256") != TARGET_SHA256:
        raise RebuildError("Recipe engine identity mismatch")
    result = render(recipe.get("operations"), original)
    if len(result) != recipe["targetBytes"] or sha(result) != TARGET_SHA256:
        raise RebuildError("Reconstructed WASM does not match the fixed target")
    inspect_sections(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-wasm", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.archive_wasm.resolve(strict=True), args.output.resolve()
    if source == output or output.exists():
        parser.error("Output must be a new file separate from the archive")
    if source.parts[-4:] == ("site", "bo1z", "artifacts", "KisakBlack-web.wasm") and output.is_relative_to(source.parents[3]):
        parser.error("Output must be outside the preservation archive")
    try:
        recipe_path = Path(__file__).with_name("engine-recipe.json")
        result = rebuild(source.read_bytes(), load_recipe(recipe_path.read_bytes()))
        # Exclusive creation also refuses a symlink/racing preexisting path.
        with output.open("xb") as stream:
            stream.write(result)
        print(json.dumps({"baseSha256": BASE_SHA256, "targetSha256": sha(result), "bytes": len(result), "archiveChanged": False, "engineExecuted": False}))
    except (OSError, RebuildError) as exc:
        parser.exit(1, f"Engine rebuild refused: {exc}\n")


if __name__ == "__main__":
    main()
