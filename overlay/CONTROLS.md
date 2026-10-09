# Controller and player options

Open **Options** on the title screen.

- **Movement activation**: raise it if the left stick starts moving too easily; lower it if you must push too far. Default 42%, with a smaller release threshold to prevent jitter.
- **Straight-line assist**: raise it to reduce accidental sideways movement. Lower it for easier diagonals. Default 60%.
- **Aim deadzone**: raise it only enough to stop right-stick drift.
- **Horizontal aim speed**, **vertical multiplier** and **aim-down-sights multiplier**: tune look and precision separately. Mouse sensitivity also affects aim in the archived engine.
- **Response curve**: 1 is linear; higher values soften small motions. Default 1.8.
- **Smoothing**: optional; adds delay. Default off.
- **Restore gentle defaults** resets only controller preferences.

Movement still uses full-speed WASD keys. These controls improve activation and direction stability; they do **not** provide analog walking, native aim assist or native controller-menu integration. The original game's greyed controller submenu is unchanged. In-game, pause and press **View / Share** to open the separate Controller panel, or click it after releasing the cursor. Release sticks/buttons after changing settings to resume input.

In **Player profile**, enter a name and select **Save name**. Choose a PNG to set an icon; **Remove icon** restores an initial. Names accept 1–24 ASCII letters, numbers, spaces, dots, underscores and hyphens. PNGs up to 2 MB and 4096 × 4096 are center-cropped/re-encoded to a 64 × 64 thumbnail. Your original image is not uploaded. The thumbnail and name are shared with your joined lobby. No account or image hosting is required.

Changes apply to the next room/game. The name is also passed as the engine's `name` launch setting; in-game display is not runtime-certified for this build. The icon appears in the menu and co-op roster, not native scoreboards or character art. Host rosters show all admitted players; guests retain the existing host/self roster visibility.

**Multiplayer → Create lobby → Lobby name** sets the name shown by LAN discovery. Leaving it blank uses your player name plus “'s lobby”. Map/settings remain fixed after creation; leave and create a new room to rename or change them.

Preferences are stored in this browser's local storage, tied to its address/port. Clearing browser data, changing browsers or switching launcher ports can reset them. They are not embedded in the ZIP.

Input snapshots and browser UI/profile admission are tested separately. Physical controller feel, native in-game name rendering and a new complete Mac/PC gameplay session remain unverified. The archived game/assets and engine patch recipe are unchanged.
