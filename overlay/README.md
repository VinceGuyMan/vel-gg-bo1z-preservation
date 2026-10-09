# BO1Z preserved co-op preview

A title screen, controller adapter and experimental networking overlay for the captured BO1Z game. Build: `bo1z-shipping-preview-v1`.

**This is a feasibility preview.** Original-engine co-op has been demonstrated, and the optional public WebSocket relay passed browser packet tests. Reliable Mac/Windows matches, four-player gameplay and Internet gameplay are unfinished. See [CAPABILITIES.md](CAPABILITIES.md) before sharing.

## Start on Mac or Windows

Each player needs their own complete `vel-gg-bo1z-2026-10-08` archive, this same overlay, a Chromium browser and Python 3.10+. Windows also needs an installed Node.js 22, 24 or 26 executable for local asset delivery. Game assets are not included.

1. Extract this overlay beside the original archive folder. Preserve the archive; do not copy these files into it.
2. Open **Launch Game.command** on Mac or **Launch Game.cmd** on Windows.
3. Choose **Solo**, **Multiplayer** or **Settings**. Solo exposes all ten preserved map destinations. Multiplayer currently starts Five / Classic and remains experimental.
4. Keep the launcher terminal open. Stop it with Control-C when finished.

If the archive is elsewhere:

```sh
python3 launch_coop.py --archive "/path/to/vel-gg-bo1z-2026-10-08"
```

Windows PowerShell:

```powershell
py -3 launch_coop.py --archive "F:\path\to\vel-gg-bo1z-2026-10-08" --node "C:\Program Files\nodejs\node.exe"
```

Use your actual paths. Ports 8767/8768 must be free; the launcher refuses existing listeners. To select others, supply `--port` and `--signal-port`. The game page and all assets stay on 127.0.0.1.

## Controller

Standard browser-mapped Xbox and PlayStation controllers are supported by the adapter. Press a controller button after connecting it. The title menu supports stick/D-pad navigation, A/Cross select and B/Circle back.

In game: left stick moves (digital WASD), right stick looks, RT/R2 fires, LT/L2 aims, A/Cross jumps, B/Circle crouches, X/Square reloads, Y/Triangle switches weapons and D-pad Up interacts/revives. Start/Options pauses; View/Share in the original pause menu opens controller settings. The browser still requires a real mouse click on Play/Resume for pointer capture and audio.

Settings include deadzone, look sensitivity, inversion and enable/disable. Input releases on focus loss, disconnect and mode changes. Controller settings also appear while loading or with the cursor released. **Physical-controller gameplay has not been validated.** Automated checks cover mapping, navigation, ownership and key release.

## Experimental local co-op

The host opens **Launch LAN Host**. This exposes only the lobby/signaling service to the LAN. Choose Multiplayer, create a room, then privately share the signaling address shown in the terminal, room code and invitation.

Other players launch their own copy, choose Multiplayer, enter the host's signaling address and join the same room. Both copies must match the full build/map identity. WebRTC is the default; every player must choose the same transport. Room capacity is four; this is not a four-player gameplay certification.

A host runs the original authoritative game. Guests exchange its existing game packets; no assets are streamed between players. Current limitations include intermittent native host input and incomplete doors, revive, rounds and recovery validation. Expect investigation rather than a dependable session.

## Optional temporary Internet lobby

The player can host the signaling and optional WebSocket relay service on their own computer. An explicit temporary HTTPS tunnel supplies a public address; no paid server or domain is required by this launcher.

Supply the separately obtained, exact supported official cloudflared 2026.10.0 binary:

```sh
python3 launch_coop.py --free-internet-host --cloudflared "/path/to/cloudflared" --archive "/path/to/archive"
```

Windows adds `--node "C:\Program Files\nodejs\node.exe"`. Supported binary digests are listed in [TRANSFER.md](TRANSFER.md). The launcher does not install/download tools, create accounts or change DNS/router settings. Provider availability and connection quality are outside this preview.

To use the relay, explicitly select **Experimental WebSocket relay** before creating/joining a room. Friends use the displayed public signaling address with their own local matching assets. The host must keep the game and terminal open. A room cannot switch transports; a relay disconnect is terminal. There is no automatic fallback, host migration or reload recovery.

The relay carries original packets over WSS/TCP. It is separate from WebRTC TURN. Public relay packet tests passed; gameplay across separate Internet networks and forced TURN remain unvalidated. The host service and tunnel provider can see relayed traffic; TCP loss can delay later packets.

## Verify

```sh
python3 verify.py --archive "/path/to/archive"
```

Add `--verify-map-content` to rehash the selected Five map's saved content. Default verification reuses capture hashes for large assets and checks their current sizes; it cannot detect same-size asset edits. Verification proves package identity, not gameplay readiness.

The locally built runtime includes the patched experimental WASM and is bundled separately in the full research download. The GitHub source bundle excludes game assets and prebuilt engines, and rebuilds this exact patch locally from the original archive. Review [PROVENANCE.md](PROVENANCE.md). The public handoff is [vel-gg-bo1z-preservation](https://github.com/VinceGuyMan/vel-gg-bo1z-preservation). See its preservation record and credits first.
