# Continuing the work

This is a preservation handoff, not a maintained multiplayer service. Forks and specific corrections are welcome; there is no promised completion schedule.

1. Keep the original capture unchanged and outside the repository. Verify it first.
2. Keep experiments separate from original replay. Preserve original credits and distinguish additions.
3. State what a test actually proved: source/build checks, synthetic packets, native gameplay, physical machines and separate networks are different gates.
4. Retain failed results. A successful sub-observation does not turn a failed match test into a pass.
5. Publish small sanitized evidence. Do not attach game assets, prebuilt engines, browser profiles, raw heap/player state, room invitations, private paths or credentials.

The [research record](docs/RESEARCH.md) gives the next unresolved gates. For attribution corrections, include a primary source. For bugs, include OS/browser/runtime versions, build identity, map/mode, reproduction and expected/actual behavior.

The frozen builder refuses changed overlay sources. Deliberate changes require updating the approved overlay map, relevant build/cache/adapter identities and metadata/checksums; validate them against a separate local copy. Source checks alone do not certify playability.

Run `python3 tools/check_repository.py` before publishing. Keep dependency/tool installs, service costs and deployment separate from the game archive. No public TURN service, hosted infrastructure or support obligation comes with this repository.
