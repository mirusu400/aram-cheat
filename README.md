# aram-cheat

The cheat database for [ARAM](https://github.com/mirusu400/aram-emu). One
document per title, keyed by the SHA-256 of the *loaded image*, the mapped
sections of the program itself, not the archive that delivered it. Re-zipping a
package changes its file hash but not its image hash, so cheats survive
repackaging.

ARAM reads this repository directly. When the Cheat Manager opens, the product
fetches `titles/<image_sha256>.json` for the loaded title, caches it, and
applies the cheats through the emulator's guarded memory writes. Publishing a
cheat here is all that is needed to ship it; no product release is involved.

## Layout

```
titles/<image_sha256>.json  the catalog for one title
index.json                  generated: every published title, for browsing
aliases.json                generated: file hash and carrier-descriptor lookup
docs/schema.md              the catalog format
tools/validate.py           the checker CI runs, and the index generator
```

`index.json` and `aliases.json` are generated. Edit the catalogs and run the
validator to regenerate them.

## Adding a cheat

1. Get the title's identity. ARAM's Compatibility Report panel shows both
   **Image SHA-256** (the key) and **File SHA-256** (what a bug report quotes).
2. Create or edit `titles/<image_sha256>.json` following `docs/schema.md`, and
   list the container you worked from under `file_sha256`.
3. Record the original bytes in `expected` for every patch. The emulator
   applies a patch only when its expected bytes match guest memory, which
   keeps a cheat safe for the exact build it was authored against.
4. Run `python tools/validate.py`, which rewrites the generated indexes.

## Finding an entry

`aliases.json` maps container hashes and readable carrier keys such as
`lgt-00027baa-pd116132-01.00.06` to an image hash. It is a convenience for
people and tooling only, carrier identifiers are not unique. Measured across a
280-package corpus, one AID covers as many as twelve unrelated titles, and one
AID+PID pair still spans two builds with different code, so a descriptor key
that reaches more than one image is left out of the map entirely.

## Scope

Cheats here target long-dead WIPI services: authentication gates that call
servers switched off years ago, carrier billing prompts, and similar checks
that make an otherwise preserved game unplayable. Every entry names the
behavior it changes.

Do not commit game files, memory dumps, extracted assets, or any part of a
title's copyrighted content. A catalog stores addresses and the few bytes a
patch replaces, nothing more.
