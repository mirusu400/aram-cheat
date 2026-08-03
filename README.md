# aram-cheat

The cheat database for [ARAM](https://github.com/mirusu400/aram-emu). One
document per title, keyed by the SHA-256 of the input file the emulator loads.

ARAM reads this repository directly. When the Cheat Manager opens, the product
fetches `titles/<sha256>.json` for the loaded title, caches it, and applies the
cheats through the emulator's guarded memory writes. Publishing a cheat here
is all that is needed to ship it; no product release is involved.

## Layout

```
index.json            every published title, for browsing and tooling
titles/<sha256>.json  the catalog for one title
docs/schema.md        the catalog format
tools/validate.py     the checker CI runs on every change
```

## Adding a cheat

1. Get the title's SHA-256. ARAM shows it in the Compatibility Report panel,
   and an issue filed from the product includes it in the diagnostics block.
2. Create or edit `titles/<sha256>.json` following `docs/schema.md`.
3. Record the original bytes in `expected` for every patch. The emulator
   refuses a patch whose expected bytes do not match guest memory, so this is
   what keeps a cheat from corrupting a build it was not authored against.
4. Add the title to `index.json` if it is new.
5. Run `python tools/validate.py`.

## Scope

Cheats here target long-dead WIPI services: authentication gates that call
servers switched off years ago, carrier billing prompts, and similar checks
that make an otherwise preserved game unplayable. Every entry names the
behavior it changes.

Do not commit game files, memory dumps, extracted assets, or any part of a
title's copyrighted content. A catalog stores addresses and the few bytes a
patch replaces, nothing more.
