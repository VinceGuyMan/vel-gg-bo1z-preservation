# Install preview v0.2.0

The [v0.2.0 preview release](https://github.com/VinceGuyMan/vel-gg-bo1z-preservation/releases/tag/v0.2.0) contains the `bo1z-lan-lobby-v2.zip` runtime overlay, source archive and SHA-256 manifest. It reuses the original capture from the [v0.1.0 research download](DOWNLOAD.md); it does not contain another copy of the 6.35 GB capture.

1. Restore the complete capture using the [v0.1.0 download instructions](DOWNLOAD.md), or use your already verified `vel-gg-bo1z-2026-10-08` folder.
2. Download and extract `bo1z-lan-lobby-v2.zip` beside that original capture. The extracted `bo1z-lan-lobby-v2` folder is separate from the archive and any older previews.
3. Use the included source archive or clone this repository. Build the preview from your original capture with Python 3.10+:

   ```sh
   python3 build_local.py --archive "/path/to/vel-gg-bo1z-2026-10-08" --output "/path/to/bo1z-lan-lobby-v2"
   ```

   Run the command from the repository/source directory. Choose a new, empty output directory outside the source and capture folders. The builder checks the archived engine identity, rebuilds the bounded overlay patch and verifies package identities. This verifies package provenance, not gameplay readiness.
4. Open **Launch Game.command** / **Launch Game.cmd** in the v2 folder, or the top-level wrapper in the consolidated package. Keep that folder beside the original capture. If the capture is elsewhere, follow the explicit launcher command in [launch instructions](LAUNCH.md).
5. Install v2 on both computers. Older previews use different build identities and cannot join a v2 lobby. Read [launch instructions](LAUNCH.md) and [controller/profile controls](CONTROLS.md).

The full consolidated ZIP is about 5.8 GB. GitHub's per-file release limit is 2 GiB, so the release publishes the small runtime overlay and source separately; the already-published three-part v0.1.0 research archive remains the download for the complete capture. You can also rebuild the v2 runtime from that capture and the repository sources.

The original archive and native engine are unchanged. Controller movement remains digital WASD. Lobby PNGs are display thumbnails, not native game emblems. Native name rendering, physical controller feel and complete multiplayer gameplay are not certified. See [capabilities and limits](CAPABILITIES.md).
