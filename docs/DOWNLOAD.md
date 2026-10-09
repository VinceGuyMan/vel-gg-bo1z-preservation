# Download the complete research package

Use the **[v0.1.0 release](https://github.com/VinceGuyMan/vel-gg-bo1z-preservation/releases/tag/v0.1.0)**. It includes the actual captured website/game resources; you do not need to capture vel.gg yourself.

GitHub limits each release file to under [2 GiB](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases). This is **one ZIP split into three parts**, not three independent ZIPs. Download these five files into one folder:

- `bo1z-research-2026-10-08.zip.001`
- `bo1z-research-2026-10-08.zip.002`
- `bo1z-research-2026-10-08.zip.003`
- `research-download.json`
- `restore_research_archive.py`

Allow about **20 GB free disk space** for the parts, joined ZIP and extracted files. With Python 3.10+, run from that download folder:

```sh
python3 restore_research_archive.py --manifest research-download.json --output bo1z-research-2026-10-08.zip --extract bo1z-research
```

Windows PowerShell uses `py -3` in place of `python3`. Choose new output/extraction paths. The tool checks each part and the joined ZIP against SHA-256, then safely extracts; it downloads nothing and starts no game. Keep the terminal open until it finishes. If you omit `--extract`, open the joined ZIP with a ZIP64-capable extractor. Do not try to open individual parts as ZIPs.

| Extracted item | Purpose |
| --- | --- |
| `READ_FIRST.md` | Credits, boundaries and launch directions |
| `vel-gg-bo1z-2026-10-08/` | Original capture, unchanged; all 3,656 indexed files plus its checksum index |
| `bo1z-preview-local/` | Separately built experimental title/controller/network overlay |
| `vel-gg-bo1z-preservation/` | Source, tools, documentation and sanitized research summary |

For the original replay, run `python3 serve.py --open-browser` (Windows: `py -3`) **inside the original capture folder**. Use Chromium, keep the terminal open, and stop with Control-C. For the optional preview, open its Launch Game.command / Launch Game.cmd. [Original replay details](PRESERVATION.md) · [Preview prerequisites](EXPERIMENTAL.md)

The release is a research archive, **not a finished co-op game**. No dependable Internet match, four-player gameplay or physical-controller gameplay is certified. Existing game/third-party rights remain; this distribution is not an official release or license grant. [Credits](../CREDITS.md) · [Capabilities](CAPABILITIES.md)

GitHub’s automatic **“Source code (zip)”** and `vel-gg-bo1z-preservation-v0.1.0-source.zip` are source-only alternatives. They do not contain the game payload. `SHA256SUMS.release.txt` records the manually attached release files.
