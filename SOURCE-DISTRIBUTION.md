# Source distribution and engine reconstruction

The public source release contains preservation records/tools and an optional overlay. It excludes the captured game, original/patched WASM, generated Emscripten glue and private test data. [Rights and attribution](PROVENANCE.md) remain separate from technical reproducibility.

## Build a private overlay

```sh
python3 build_local.py --archive "/path/to/vel-gg-bo1z-2026-10-08" --output "../bo1z-preview-local"
```

Python 3.10+ and the complete matching capture are required. Windows uses `py -3`. Choose a new output outside both the archive and repository, with an existing parent directory.

The standard-library builder checks approved overlay sources, reconstructs the experimental engine, regenerates compatibility metadata/checksums and verifies Five’s saved asset bytes. It launches no game, browser or service and never modifies the archive. Existing outputs and edited overlay sources are refused. An interrupted final copy may leave a partial output; inspect it and choose a new destination.

| Engine | Required SHA-256 |
| --- | --- |
| Supplied original | `61192df377020627f52fa7e9fd28047bd53662aa46e5e3cd6e7fad0c5c35cc98` |
| Reconstructed experiment | `29c436447d467e63ae05346bdb5ed53c5f79ce0ab5e7493148200797b7129628` |

`engine/engine-recipe.json` copies unchanged sections/instructions from that original, splices the bounded co-op changes and generates the reviewed debug-name encoding. `engine/helpers.wat` is readable added helper source. The recipe/tool reject a wrong base, changed recipe or final hash mismatch. The diagnostic instrumented engine is excluded.

**This is deterministic binary reconstruction, not a full source compilation of the deployed game.** Identical bytes do not prove dependable co-op.

## Integrity and development

```sh
python3 tools/check_repository.py
```

`SOURCE-SHA256SUMS.txt` covers the public tree; `approved-sources.json` pins the overlay inputs. `.gitattributes` preserves exact bytes on Windows/macOS checkouts. The capture has its own independent index. For changes, preserve the original capture, update identities deliberately, then regenerate the approved map, metadata and checksums. See [CONTRIBUTING.md](CONTRIBUTING.md).

`stage_source.py` is the original allowlisted overlay stager; it does not package this repository’s extra documentation or preservation records and never performs Git operations.
