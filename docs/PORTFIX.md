# Automatic-port launcher update — v0.1.1

Download `bo1z-portfix-v1.zip` from the [v0.1.1 release](https://github.com/VinceGuyMan/vel-gg-bo1z-preservation/releases/tag/v0.1.1). It contains the complete updated experimental overlay; the original archive is reused.

1. Close earlier launchers with Control-C in their own terminals.
2. Extract the new folder beside `vel-gg-bo1z-2026-10-08`. Do not merge it into the archive or old preview.
3. Use this update on **both Mac and PC**. Its new build/cache/peer identity rejects older previews.
4. On the PC, open **Launch LAN Host.cmd** normally. On Mac, open **Launch Game.command** normally. No port arguments are needed.
5. The PC prints the actual LAN signaling address. Use that address, room code and invitation on the Mac.

The launcher prefers game port 8767 and signaling port 8768. If either is unavailable, the OS chooses a free alternative. It keeps sockets reserved until their owned services start, prints selected ports and builds the browser/invitation URLs from them. It never kills or reuses another program. Explicit `--port` / `--signal-port` requests stay strict. macOS reservations no longer enable address reuse, which could let a wildcard LAN socket overlap an existing loopback listener.

Temporary Internet hosting uses the signaling service's normal HTTP loopback-origin policy for different guest asset ports; invitation/ticket authentication remains unchanged. External website origins remain rejected.

Fourteen checks passed, including an actual macOS startup with both default ports occupied and clean owned shutdown. The selected Five assets and reconstructed engine passed package verification. **No Windows runtime, new gameplay, controller or Internet match was run for this update.** All [existing co-op limits](CAPABILITIES.md) still apply.
