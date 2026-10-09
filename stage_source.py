#!/usr/bin/env python3
"""Stage only explicitly reviewed text sources; never commit, push or publish."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

# This is a concrete allowlist, not a recursive copy or extension-only filter.
# New product files require deliberate review and a source-map update.
ALLOWED = {
    "bridge.js", "observer.js", "rtc-transport.js", "resume-controller.js",
    "native-admission.js", "runtime-attestation.js", "status.js", "status-ui.js",
    "start-gate.js", "request-policy.js", "peer-schema.js", "lobby.js", "lobby.css",
    "gamepad-input.js", "main-menu.html", "main-menu.css", "main-menu.js",
    "serve_coop.py", "export_assets.py", "serve_assets.cjs", "segmented_writer.py",
    "portable_replay.py", "launch_coop.py", "free_host.py", "signaling.py", "ice_issuer.py",
    "build_metadata.py", "verify.py", "refresh_checksums.py", "network-config.json",
    "ws-loader.js", "ws-transport.js", "ws_relay.py", "ws_wire.py",
    "Launch Game.command", "Launch Game.cmd", "Launch Co-op.command", "Launch Co-op.cmd",
    "Launch LAN Host.command", "Launch LAN Host.cmd",
    "Launch Free Internet Host.command", "Launch Free Internet Host.cmd",
    "patch-manifest.json", "compile-report.json",
    "README.md", "TRANSFER.md", "CAPABILITIES.md", "PROVENANCE.md", "PACKAGING-NOTES.md",
    "deployment/README.md", "deployment/Dockerfile", "deployment/Caddyfile", "deployment/.dockerignore",
}
KIT_FILES = {
    "stage_source.py", ".gitignore", "SOURCE-DISTRIBUTION.md", "PROVENANCE.md",
    "engine/rebuild_engine.py", "engine/engine-recipe.json", "engine/helpers.wat",
}
MAX_FILE_BYTES = 1048576


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_text(root, name, expected=None):
    if not isinstance(name, str) or "\\" in name:
        raise ValueError("Only portable POSIX source paths are admitted")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe source path")
    file = root.joinpath(*relative.parts)
    for i in range(1, len(relative.parts) + 1):
        if root.joinpath(*relative.parts[:i]).is_symlink():
            raise ValueError("Source symlinks are excluded")
    if not file.is_file() or not file.resolve().is_relative_to(root):
        raise ValueError("Missing source or outside source root")
    if not 0 < file.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("Source size is outside the text-file bound")
    data = file.read_bytes()
    if b"\0" in data or data.startswith(b"\0asm"):
        raise ValueError("Binary content is excluded")
    data.decode("utf-8")
    if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or digest(data) != expected):
        raise ValueError("Approved source hash mismatch")
    return data


def collect(runtime, source_map, kit):
    if not isinstance(source_map, dict) or not source_map or len(source_map) > len(ALLOWED):
        raise ValueError("Invalid approved source map")
    if set(source_map) - ALLOWED:
        raise ValueError("Unapproved paths are excluded: " + ", ".join(sorted(set(source_map) - ALLOWED)))
    result = {"overlay/" + name: checked_text(runtime, name, pin) for name, pin in sorted(source_map.items())}
    if "overlay/network-config.json" in result:
        config = json.loads(result["overlay/network-config.json"])
        if config.get("iceServers") != []:
            raise ValueError("Static ICE URLs/credentials are excluded from this source distribution")
    result.update({name: checked_text(kit, name) for name in sorted(KIT_FILES)})
    return dict(sorted(result.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-source", required=True, type=Path)
    parser.add_argument("--approved-source-map", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only and args.output is None:
        parser.error("--output or --check-only is required")
    try:
        runtime = args.runtime_source.resolve(strict=True)
        kit = Path(__file__).resolve().parent
        source_map = json.loads(args.approved_source_map.read_bytes())
        files = collect(runtime, source_map, kit)
        if args.check_only:
            print(json.dumps({"sourceFiles": len(files), "bytes": sum(map(len, files.values())), "staged": False, "published": False}))
            return
        output = args.output.resolve()
        if output.exists() or output.is_relative_to(runtime) or output.is_relative_to(kit):
            raise ValueError("Output must be a new separate staging directory")
        output.mkdir(parents=False)
        try:
            for name, data in files.items():
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o755 if target.suffix in (".command", ".py") else 0o644)
            sums = "".join(digest(data) + "  " + name + "\n" for name, data in files.items())
            (output / "SOURCE-SHA256SUMS.txt").write_text(sums, encoding="utf-8")
        except BaseException:
            shutil.rmtree(output)
            raise
        print(json.dumps({"sourceFiles": len(files), "bytes": sum(map(len, files.values())), "sourceManifestSha256": digest(sums.encode()), "published": False, "gameAssetsIncluded": False, "wasmBinariesIncluded": False}))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Source staging refused: {exc}\n")


if __name__ == "__main__":
    main()
