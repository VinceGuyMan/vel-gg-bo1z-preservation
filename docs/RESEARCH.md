# Preservation and research record

## What was captured

The October 8, 2026 capture records **1,808 successful HTTP resources** and **6,344,680,777 bytes of response bodies**. Its checksum index covers **3,656 files / 6,351,964,605 bytes**, including provenance and capture evidence. These are different counts: response bodies are not the whole archive.

Maps: **Five, Kino der Toten, Der Riese, Nacht der Untoten, Verrückt, Shi No Numa, Ascension, Call of the Dead, Shangri-La and Moon**. Ten base manifests and six Horde manifests were saved, including listed transport/audio fallbacks and cinematics. All **673 unique manifest transports** passed decoded size and SHA-256 checks. Optional caches absent on the source site are recorded as capture errors; they are not silently reconstructed.

Offline page checks found ten map links, no missing responses and no JavaScript page errors. Five's WebGL2 engine reached its ready screen/cinematic; that initial headless check could not obtain pointer lock. Later experimental gameplay is separate evidence.

## Why there is an experimental overlay

The captured engine rejected numeric remote addresses and exposed loopback-limited packet paths. Matching complete deployed source/build inputs were not recovered. Bounded binary changes restore original address, packet and startup paths, preserving the original game's packets and scripts. A deterministic local recipe reconstructs the exact patched engine from the matching original archive. **This is binary reconstruction, not a full source build of the deployed game.**

| Engine | SHA-256 |
| --- | --- |
| Captured original | `61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98` |
| Ordinary experimental engine | `29c436447d467e63ae05346bdb5ed53c5f79ce0ab5e7493148200797b7129628` |

The original archive remained separate. A post-experiment full archive check verified all 3,656 indexed files with zero failures. Diagnostic instrumented engines, test harnesses and private raw logs are outside the public source package.

## Findings, including failed gates

| Experiment | Retained conclusion |
| --- | --- |
| Two original clients on one Mac | Native shared spawns and movement. Ordinary guest attacks changed host zombie health; kills/removal and point awards were observed. M14 purchase debited 500 points; original down state appeared. Doors, revive and later rounds remained unproved. |
| Physical Mac/Windows LAN | Distinct players and guest movement replicated to host. LAN7 recorded 24.52 game units of guest movement, but host backward input produced no completed movement commands. Both overall run verdicts stayed failed. A competing native event consumer is a static lead, not a proven cause. |
| Final diagnostic | Windows service readiness reached the existing 20-second timeout. Owned cleanup completed; no native diagnostic pair started. Further gameplay/network testing stopped at the preservation handoff. |
| Public relay fixture | 152 browser checks, 26 exact generated packet routes totaling 405,226 bytes; payload sizes included 1 / 1,200 / 65,536 bytes. Authentication, invalid routing, departure, host close and normal cleanup checks passed. Four managers on one Mac, no engine or separate-network match. |
| Final preview | Standard-pad mapping/lifecycle checks and desktop/mobile title QA. Final saved settings updated all 20 Solo/co-op stores. Source reconstruction reproduced all 55 runtime files byte for byte. Windows delivery checked 54 runtime and 62 source checksums; its launcher was not executed in that pass. |

Raw test reports are retained privately because they contain local machine details and native diagnostic state. The [public summary](../evidence/research-summary.json) records source-report hashes and narrow outcomes. A failed end-to-end test remains failed even when a useful sub-observation succeeded.

## What remains for a successor

First isolate the intermittent native input fault and prove a stable two-player Mac/Windows Five match. Then validate doors, revive, rounds, disconnect/rejoin, four native clients and separate-network play, including forced TURN. Extend runtime validation to the other nine maps. Controller hardware testing and matching-source/provenance work remain open. None of these is a promised feature or scheduled release.

The v0.1.0 public handoff changes documentation and adds preservation tools. Its overlay code and engine recipe remain the preview’s originals; the 55-file byte-for-byte reconstruction observation refers to that earlier frozen preview. A fresh local build of the public sources reproduced the same engine hash and peer identity and rehashed Five’s assets, without launching a game or service. [Publication checks](../evidence/publication-checks.json) establish packaging, not gameplay readiness.

The v0.1.1 launcher update changes shell/cache identity and automatic port selection. Fourteen checks included a real macOS service startup with both defaults occupied, correct browser/LAN addresses, exclusive reservations and owned cleanup. No browser/game was started; Windows runtime remains untested for this update.
