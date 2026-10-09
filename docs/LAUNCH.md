# Launch and join a LAN lobby

Use the same complete package on both computers. The original archive stays separate from the experimental build. A working lobby connection does not certify a finished co-op match; see [capabilities](CAPABILITIES.md).

## Before opening it

- Extract the ZIP completely. Keep the original `vel-gg-bo1z-2026-10-08` folder beside the built `bo1z-lan-lobby-v2` folder.
- Install Python 3.10+ and a Chromium browser: Chrome, Brave, Edge or Chromium. Windows also needs installed Node.js 22, 24 or 26. These dependencies are not bundled or installed automatically.
- For LAN play, connect both computers to the same local network. Keep each player's game assets on their own computer.

## Mac

1. Double-click **Launch Game.command**. In the consolidated BO1Z package, use the launcher in the top folder.
2. Keep its terminal open. The launcher selects free ports and opens the new title screen.
3. Choose **Solo**, **Multiplayer** or **Settings**. **Launch Game.command** supports both hosting and joining; **Launch LAN Host.command** remains an explicit host shortcut.

If Finder opens the file as text, open Terminal, type `bash `, drag **Launch Game.command** into the window, then press Return. If browser opening fails, copy the complete game URL printed in the terminal into Chrome or Edge. Do not open a saved HTML file directly.

The launcher starts the browser executable directly on macOS. This avoids a Brave launch-method failure observed during our LAN test and [reported to Brave](https://github.com/brave/brave-browser/issues/57323). If an already-running Brave session still shows `ERR_ADDRESS_UNREACHABLE`, save your browser work, quit Brave completely, and relaunch the game. No browser security flags need changing.

## Windows

1. Extract the ZIP first; do not run launchers from inside the ZIP viewer.
2. Double-click **Launch Game.cmd**. In the consolidated BO1Z package, use the launcher in the top folder.
3. Keep the command window open. **Launch Game.cmd** supports both hosting and joining; **Launch LAN Host.cmd** remains an explicit host shortcut.

If Windows cannot find Python or Node, run from PowerShell in the built folder with your actual paths:

```powershell
py -3 .\launch_coop.py --archive "F:\path\to\vel-gg-bo1z-2026-10-08" --node "C:\Program Files\nodejs\node.exe"
```

Add `--lan` when hosting. If `py` is unavailable but Python is installed, use `python` instead. Python must be 3.10 or newer.

## Host a LAN match

1. Open **Launch Game** or **Launch LAN Host** on the host computer. If the OS requests network access, allow the launcher on your trusted private/home network.
2. Choose **Multiplayer → Create lobby**.
3. Set **Lobby name**, **Map**, **Game mode** and **Player limit** (two to four). Classic is available for all ten captured maps; Horde is offered on the six maps with captured Horde support. Horde exposes **Starting round** (1–255), **Maximum active zombies** (24–1024), **Show enemy counter** and **No perks**. These are experimental engine options, not proof that each map/mode works in co-op.
4. Choose **Create lobby**. Keep the game and launcher open while guests join.
5. Once everyone has loaded and guests have selected **Ready**, the host selects **Start match**. A mouse click on the original Play/Resume control may still be required for pointer capture and audio.

Map and mode are fixed when the room is created. Leave it and create a new lobby to change them. Every player must use the same build; the host's map, mode and options are applied to joining players.

## Join without typing a room code

1. Open **Launch Game** on the other computer and choose **Multiplayer → Find LAN games**.
2. Select the host's lobby and choose **Join lobby**. The list shows its map, mode and player count; **Refresh** rescans.
3. Wait for the host connection, load the map when prompted, then choose **Ready**.

Discovery uses IPv4 UDP broadcast on port **28769**. It finds advertised lobbies on the same broadcast network; guest Wi-Fi isolation, VPNs or firewalls can prevent discovery. It does not search the Internet. LAN hosting also needs the host's actual signaling TCP port to be reachable. Ports for the game and signaling are selected automatically and can change after a restart.

## If the lobby does not appear

1. Confirm the host used **Launch Game** or **Launch LAN Host**, created a lobby, and left its terminal open. Refresh on the guest.
2. Expand **Join by address or Internet invite**. In **Signaling server**, enter the host's exact **LAN signaling address** printed by its launcher. Enter its **Room code**, keep the same transport as the host, then choose **Join room**.
3. The address must contain the host's LAN IP and printed port. `127.0.0.1` always means the computer you are currently using; it cannot point a Mac at a Windows host. Do not assume the signaling port is 8768.
4. If manual joining also fails, check both computers' private-network permissions and whether their network isolates devices. Keep the launcher error, browser URL and lobby status for diagnosis.

## Controller and stopping

Use the new title's **Settings → Controller**, or the added **Controller** panel while paused. The original game's greyed-out controller menu is a separate legacy entry. Focus the game tab and press a controller button for browser detection. Hardware controller gameplay remains unvalidated; see the [controller/profile guide](CONTROLS.md).

Close the game tab and press **Control-C** in each launcher terminal when finished. Restart through the launcher if needed. Automatic port selection leaves other applications running; explicit `--port` / `--signal-port` values stay strict.

For the unchanged captured interface, use the launch instructions inside the original archive. That launcher does not provide the new LAN browser or controller adapter. For source-only downloads, [build the experimental runtime first](EXPERIMENTAL.md#build-and-launch).

## Controller and player options

The title screen **Settings** view includes player profile and controller settings. Tune the left-stick activation threshold and diagonal assist, or adjust aim deadzone, response curve, ADS multiplier, vertical speed and smoothing. See the [controller/profile guide](CONTROLS.md) for ranges, saving behavior and limits. Left-stick movement remains digital WASD.
