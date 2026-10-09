# What this preview establishes

| Area | Evidence | Remaining |
| --- | --- | --- |
| Original engine co-op | Two native clients on one Mac exchanged packets, spawned separately and shared movement, zombie health/death, points, a weapon purchase and down state in earlier frozen builds. | Reliable end-to-end physical Mac/PC match, doors, revive, natural rounds and reconnect. |
| Physical LAN | Earlier Mac/PC runs established distinct native players and replicated guest movement. One host-input attempt worked; a later one consumed browser events without producing backward native commands. | Dependable bidirectional control; input fault cause unresolved. The final diagnostic attempt stopped at Windows service readiness before gameplay. |
| Public relay | Actual HTTPS/WSS browser fixture passed 152 checks: three guest star routes, unchanged 1/1200/65536-byte packets, authentication/route refusals, departure/host-close and cleanup. | These were packet fixtures on one Mac, not game sessions on separate networks. No Internet gameplay or latency claim. |
| Four players | Room and transport slot capacity is four. Synthetic routing exercised three guests. | Four native game clients in one shared match. |
| TURN | Configurable WebRTC path exists. | Separate-network forced-TURN gameplay; no TURN service is bundled or deployed. |
| Maps | Ten captured Solo destinations and artwork are present. Five / Classic is the co-op starting profile. | Runtime validation of all ten maps; co-op profiles for the other nine. |
| Title and controller | Solo/Multiplayer/Settings implemented; scoped source/unit and title-only browser checks are recorded in release validation. | Physical Xbox/PlayStation gameplay and full user-session testing. |

Networking/gameplay research is paused at the user's request. This packaging pass changes menus, controller input and build/cache identity; it does not repair the archived engine's intermittent input fault. The ordinary proof8 engine is preserved; the diagnostic instrumented engine is excluded.

No completion claim is made for the original goal of dependable four-player Internet Zombies on all ten maps.

Gameplay and public-relay observations above belong to earlier frozen experimental builds. The final preview adds menus/controller input and changes identity labels; no new native or public-relay execution is claimed for this exact preview.
