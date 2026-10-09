# Optional preview: setup and controls

The [unchanged original archive](PRESERVATION.md) is the preservation baseline. This overlay adds controls and networking; [capabilities](CAPABILITIES.md) lists its unfinished gates. The [full download](DOWNLOAD.md) includes both folders separately, so building is optional.

## Build and launch

For the extracted complete package, follow [Mac, Windows and LAN launch steps](LAUNCH.md). The commands below are for building from source or supplying a different archive path.

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

Keep the terminal open; Control-C stops owned services. Default ports prefer 8767/8768 and automatically select free alternatives when occupied. Explicit --port / --signal-port choices stay strict. All game assets remain on 127.0.0.1. Use the title’s Solo, Multiplayer or Settings controls. Solo retains ten original destinations; the experimental lobby offers captured maps and their available Classic/Horde options. Five / Classic is the first gameplay test target; other combinations remain unvalidated.

## Controller

| Action | Standard Xbox / PlayStation mapping |
| --- | --- |
| Menu | Stick/D-pad navigate · A/Cross select · B/Circle back |
| Move / look | Left stick = digital WASD · right stick = relative look |
| Fire / aim | RT/R2 · LT/L2 |
| Jump / crouch / reload / switch | A/Cross · B/Circle · X/Square · Y/Triangle |
| Use / revive · pause | D-pad Up · Start/Options |

Click the original Play/Resume control with the mouse for browser pointer/audio permission. The new title Options include independent movement activation, diagonal assist, aim deadzone and speed, vertical/ADS multipliers, response curve, smoothing and inversion. View/Share opens the separate controller panel after the original game releases the pointer. Movement maps to digital WASD; analog walking and physical-controller gameplay remain unvalidated. See [CONTROLS.md](CONTROLS.md).

## Experimental joining

The host opens **Launch Game** or **Launch LAN Host**, chooses **Multiplayer → Create lobby**, then selects map, mode and player limit. Friends run their own matching package and use **Multiplayer → Find LAN games → Join lobby**. A manual host signaling address plus room code/invitation remains available when UDP discovery is blocked. Use the host's LAN IP and actual printed port; `127.0.0.1` points to the player's own computer. [Step-by-step LAN instructions and troubleshooting](LAUNCH.md#host-a-lan-match)

Build/map identities and chosen transport must match. Four slots are implemented; four native gameplay clients and co-op across all maps/modes remain unvalidated.

WebRTC is the default. An optional player-hosted WSS/TCP relay can use a separately supplied pinned cloudflared 2026.10.0 executable:

```sh
python3 launch_coop.py --free-internet-host --cloudflared "/path/to/cloudflared" --archive "/path/to/archive"
```

Windows also supplies `--node`. See [supported binary hashes](../overlay/TRANSFER.md). Select Experimental WebSocket relay explicitly before creating/joining. No paid server/domain is required by this mode; provider availability is not guaranteed. No tool is installed automatically.

This relay is separate from TURN. TCP loss can delay later packets; the host/tunnel provider can see relayed traffic. Room transport cannot switch; relay disconnect is terminal. No automatic fallback, host migration or reload/rejoin restoration is provided. Public packet tests passed; separate-network gameplay did not run. [Architecture](ARCHITECTURE.md)
