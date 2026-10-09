# Capabilities and limits

**Preservation first. Experimental improvements second.** This preserves the client deployment captured from [vel.gg/bo1z](https://vel.gg/bo1z/) on October 8, 2026. It does not claim authorship of the game or original browser port.

| Area | What exists or was observed | What is not established |
| --- | --- | --- |
| Archive | Ten map destinations, listed game files, cinematics, engine/worker files, artwork, audio, shaders and available caches were captured. All 673 unique manifest transports passed decoded size/hash checks. | Unpublished source, operator infrastructure, missing optional upstream caches, every map's engine startup or complete playthroughs. |
| Local replay | Original menu and ten map pages passed offline page checks. Five reached its original engine ready screen and cinematic. | That capture check did not enter interactive gameplay. Archive completeness does not certify every game mode. |
| New title | Solo / Multiplayer / Settings, ten preserved Solo destinations, saved options and desktop/mobile layouts. | This is a desktop browser game; the responsive menu does not establish phone gameplay. |
| Controller | Standard-mapped Xbox/PlayStation adapter, menu navigation, deadzone, look sensitivity, inversion and safe input release. | Physical controller gameplay. Left-stick movement maps to digital WASD; no rumble, platform-specific button artwork or unusual-pad compatibility is claimed. |
| Original-engine co-op | Earlier builds ran two isolated clients on one Mac: separate spawns, shared movement, zombie damage/death, points, M14 purchase and down state. | Reliable complete matches, doors, completed revive, natural round progression, reload/rejoin or recovery. |
| Physical Mac/PC LAN | Earlier runs established separate native players and guest movement received by the host. | Dependable control in both directions. A later host input test drained browser events without producing movement commands; cause remains unresolved. |
| Public WSS relay | A public HTTPS/WSS fixture passed 152 checks, carrying exact generated packets among one host and three guest browser managers. | Separate-network Internet gameplay, game latency or reliability. All managers ran on one Mac; no game engine ran in that fixture. |
| Four players / TURN | Four room slots, three synthetic guest routes and configurable WebRTC transport. | Four native players in a game, forced-TURN gameplay or a bundled TURN service. WSS/TCP is a separate optional transport, not TURN. |
| Other maps | All ten captured Solo routes remain accessible. | Co-op runtime profiles beyond Five / Classic, or all-map multiplayer validation. |

Launchers target macOS and Windows with a Chromium browser and Python 3.10+. Windows additionally needs installed Node.js 22, 24 or 26 for asset delivery. This is not a signed native app, console port or validated mobile game. The [research download](DOWNLOAD.md) includes the capture and built preview; Git source archives contain neither game assets nor prebuilt engines.

The host runs the original authoritative game. Each player supplies the same local assets and matching build; assets are not streamed between players. WebRTC is the default. Optional player-hosted WSS needs a separately obtained supported tunnel tool; dropped relay members are terminal. No automatic fallback or host migration is provided.

The final preview passed packaging and title checks. Gameplay and public relay observations belong to earlier frozen builds; **this exact menu/controller preview has not run a new native or Internet match**. See [research](RESEARCH.md) and the [sanitized evidence summary](../evidence/research-summary.json).
