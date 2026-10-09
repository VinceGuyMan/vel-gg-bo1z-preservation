# Preservation comes first

This project documents the **October 8, 2026 capture of [vel.gg/bo1z](https://vel.gg/bo1z/)**. The original website and its contributors made the browser game; this repository preserves knowledge about it and adds optional experiments.

**The [full research release](DOWNLOAD.md) includes the captured game resources and original engine, a separate built experimental preview, and these source/docs.** No recapture is needed. The Git tree and automatic source ZIP contain tools, documentation and integrity records; cloning alone does not download the game.

## The captured snapshot

| Record | Preserved scope |
| --- | --- |
| Original capture index | 3,656 listed files; 6,351,964,605 bytes |
| Successful HTTP resources | 1,808 responses; 6,344,680,777 response-body bytes |
| Map coverage | Ten published map pages and base manifests; six Horde manifests |
| Manifest verification | 673 recorded transport checks passed against declared decoded sizes and SHA-256 hashes |
| Source omissions | 22 recorded HTTP 404s, including optional graphics caches and speculative crawler matches |

Maps: Five, Kino der Toten, Der Riese, Nacht der Untoten, Verrückt, Shi No Numa, Ascension, Call of the Dead, Shangri-La and Moon.

The capture retains public pages, JavaScript/WebAssembly, workers, pack parts, cinematic streams, audio variants, map art, available graphics caches, original response headers, source indexes and browser evidence. All manifest-listed game downloads and streams were captured. Unpublished source, operator infrastructure, prior versions and future changes were not captured.

## Verify your copy

From this repository, using Python 3.10 or newer:

```sh
python3 tools/archive_inventory.py --archive "/path/to/vel-gg-bo1z-2026-10-08"
```

On Windows, use `py -3` in place of `python3`. Successful verification prints a portable JSON inventory and exits with code `0`; failure exits with code `1`. The tool hashes every listed file, pins the original checksum index, rejects unsafe paths and symlinks/reparse points, and writes nothing to the archive. It does not download missing content or repair a changed copy. Unlisted files such as local caches are outside the integrity claim.

The [published inventory](../evidence/preservation-inventory.json) contains counts and index hashes, without local machine paths or game data. Matching these hashes proves that the listed bytes match this capture, not that the capture contains every resource the website ever offered.

## Open the unchanged archive

Use the **original archive folder**, separate from the experimental preview:

- macOS: double-click its `Launch Archive.command`.
- macOS/Linux terminal: run `python3 serve.py --open-browser` from that folder.
- Windows PowerShell: run `py -3 serve.py --open-browser` from that folder.

Keep the terminal open, use a Chromium browser and visit `http://127.0.0.1:8765/bo1z/`. If the port is occupied, add `--port 8766`. Stop with Control-C. Opening HTML directly does not supply the shared-memory headers, worker paths or pack/video handling the original needs. The original local server acknowledges telemetry locally.

The original archive's offline checks covered the menu, ten map pages and Five reaching the engine ready/cinematic screen. They were **not ten-map gameplay certification**. The later multiplayer preview uses a separate patched engine; its evidence does not retroactively certify the unchanged archive.

Keep the original ZIP, its checksum and an independent backup. Run experiments against a separate copy. Preservation and verification do not confer redistribution rights; see [credits](../CREDITS.md).
