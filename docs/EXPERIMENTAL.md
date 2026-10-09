# Optional preview: setup and controls

The [unchanged original archive](PRESERVATION.md) is the preservation baseline. This overlay adds controls and networking; [capabilities](CAPABILITIES.md) lists its unfinished gates.

## Build and launch

From this repository, with Python 3.10+:

```sh
python3 build_local.py --archive "/path/to/archive" --output "../bo1z-preview-local"
```

Windows uses `py -3`. Keep the archive outside the repository. The output must be new, outside both the source and archive, with an existing parent directory.

In the built folder, open **Launch Game.command** on macOS or **Launch Game.cmd** on Windows. Chromium and Python 3.10+ are required; Windows also needs installed Node.js 22/24/26. If the archive is not its sibling, pass its path:

```sh
python3 launch_coop.py --archive "/path/to/archive"
```

```powershell
py -3 launch_coop.py --archive "F:\path\to\archive" --node "C:\Program Files\nodejs\node.exe"
```

Keep the terminal open; Control-C stops owned services. Default ports are 8767/8768; occupied ports are refused. All game assets remain on 127.0.0.1. Use the title’s Solo, Multiplayer or Settings controls. Solo retains ten original destinations; multiplayer starts Five / Classic.

## Controller

| Action | Standard Xbox / PlayStation mapping |
| --- | --- |
| Menu | Stick/D-pad navigate · A/Cross select · B/Circle back |
| Move / look | Left stick = digital WASD · right stick = relative look |
| Fire / aim | RT/R2 · LT/L2 |
| Jump / crouch / reload / switch | A/Cross · B/Circle · X/Square · Y/Triangle |
| Use / revive · pause | D-pad Up · Start/Options |

Click the original Play/Resume control with the mouse for browser pointer/audio permission. Deadzone, aim sensitivity, inversion and enable/disable are available. Input releases on disconnect/focus changes. View/Share in the original pause menu opens controller settings. Physical-controller gameplay is unvalidated.

## Experimental joining

The host opens **Launch LAN Host**, chooses Multiplayer and creates a room. Friends run their own matching local archive/overlay, enter the host signaling address and join using the room code/invitation. Build/map identities and chosen transport must match. Four slots are implemented; four native gameplay clients are unvalidated.

WebRTC is the default. An optional player-hosted WSS/TCP relay can use a separately supplied pinned cloudflared 2026.10.0 executable:

```sh
python3 launch_coop.py --free-internet-host --cloudflared "/path/to/cloudflared" --archive "/path/to/archive"
```

Windows also supplies `--node`. See [supported binary hashes](../overlay/TRANSFER.md). Select Experimental WebSocket relay explicitly before creating/joining. No paid server/domain is required by this mode; provider availability is not guaranteed. No tool is installed automatically.

This relay is separate from TURN. TCP loss can delay later packets; the host/tunnel provider can see relayed traffic. Room transport cannot switch; relay disconnect is terminal. No automatic fallback, host migration or reload/rejoin restoration is provided. Public packet tests passed; separate-network gameplay did not run. [Architecture](ARCHITECTURE.md)
