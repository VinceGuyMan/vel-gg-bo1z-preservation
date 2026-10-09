# Transfer and prerequisites

Copy the complete original archive separately. Copy the entire runtime overlay separately, beside that archive or supply `--archive PATH`. Every peer must use the same overlay version. Do not merge files into the original archive or older experimental overlays.

Mac: Python 3.10+ and a Chromium browser. Windows: Python 3.10+, Chromium/Edge, and installed Node.js 22, 24 or 26. Launcher wrappers pass command-line arguments through. No tool is automatically downloaded or installed.

The optional free Internet host supports these exact official cloudflared 2026.10.0 builds:
- macOS ARM64: SHA256 `72edfd3eea463aef4d5cb89e2e209cecb048cc756c2b01915de2e0ad7cb39830`
- Windows AMD64: SHA256 `86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c`

Neither cloudflared nor Node nor game assets are bundled. Keep room invitations and temporary service addresses private. Close the launcher normally when finished.

Verify `SHA256SUMS.txt` / `verify.py` after extraction. The checksum file lists package files; no browser profile, raw log, room secret, test harness or tunnel binary belongs in the overlay.
