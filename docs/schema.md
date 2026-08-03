# Catalog schema

Version 2. The emulator's parser lives in `aram-core/cheat/catalog.go` and
rejects unknown fields, so a document that a newer schema produced fails
loudly instead of losing data.

## Document

`titles/<image_sha256>.json`, where `<image_sha256>` is the identity of the
loaded executable image. The `image_sha256` inside the document must match the
file name.

```json
{
  "version": 2,
  "title": {
    "image_sha256": "c1d814a9325e5285c547d1d9d3906e0bee45bdfe576e705c9a727747d4680b49",
    "file_sha256": [
      "3cc7a9b4cb15818cdd5a66f7e520c7b9b36f1df8d2df096aafa961b1cb2b682c"
    ],
    "name": "제노니아 1",
    "carrier": "lgt",
    "format": "raptor-wipi-c",
    "profile_id": "wipi-1.2.1/lgt/raptor",
    "aid": "00027BAA",
    "pid": "PD116132",
    "version": "01.00.06",
    "vendor": "게임빌"
  },
  "cheats": [
    {
      "id": "skip-server-authentication",
      "name": "Skip server authentication",
      "description": "Starts the game without the Gamevil authentication server.",
      "category": "bypass",
      "author": "aram",
      "reference": "https://github.com/mirusu400/aram-emu/issues/4",
      "restore_on_disable": true,
      "patches": [
        {
          "address": "0x00056710",
          "value": "10207047",
          "expected": "30b5041c",
          "note": "return the already-authenticated result"
        }
      ]
    }
  ]
}
```

## Why the image hash

A patch replaces bytes at an address in the loaded program. The archive that
delivered that program is irrelevant to whether the patch is correct, and its
hash changes whenever anyone re-zips the package. `image_sha256` digests what
the emulator actually maps — each section's address, size, permissions, and
initialized bytes — so it is stable across repackaging and sensitive to every
difference that could move a patch target.

## Fields

### title

| Field | Required | Meaning |
| --- | --- | --- |
| `image_sha256` | yes | Identity of the loaded image, 64 lowercase hex characters. The primary key. |
| `file_sha256` | no | Container hashes known to carry this image. Used to find an entry from a bug report, and as a fallback lookup. |
| `name` | no | Human-readable title. |
| `carrier` | no | `lgt`, `ktf`, `sktt`, or another carrier tag. |
| `format` | no | The loader format ARAM reports, such as `raptor-wipi-c`. |
| `profile_id` | no | The compatibility profile ARAM reports. |
| `aid` | no | Carrier application ID from the package descriptor. |
| `pid` | no | Carrier product ID from the package descriptor. |
| `version` | no | Package version string from the descriptor. |
| `vendor` | no | Publisher from the descriptor. |

`aid`, `pid`, `version`, and `vendor` are recorded for browsing. They are never
keys: measured across a 280-package corpus, one AID covers as many as twelve
unrelated titles, and one AID+PID pair still spans two builds with different
code.

### cheats[]

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable identity, at most 64 characters of `a-z`, `0-9`, `-`, `.`, `_`. |
| `name` | yes | Label shown in the Cheat Manager. |
| `description` | no | One line explaining what changes. |
| `category` | no | Free tag, such as `bypass`, `progression`, or `resources`. |
| `author` | no | Who authored the entry. |
| `reference` | no | Issue or write-up URL. |
| `freeze` | no | Rewrite the patch after every emulated frame. Use for values the game overwrites, not for code. |
| `restore_on_disable` | no | Put the original bytes back when the cheat is turned off. Set it for code patches so a cheat can be toggled. |
| `patches` | yes | At least one patch, all applied as one unit. |

### patches[]

| Field | Required | Meaning |
| --- | --- | --- |
| `address` | yes | Guest address, `"0x00056710"`. A plain number is accepted. |
| `value` | yes | Replacement bytes, lowercase hexadecimal, in guest order. |
| `expected` | yes | The original bytes at that address, same length as `value`. |
| `note` | no | Why this patch exists. |

## Rules

- `expected` is mandatory and must be the same length as `value`. The catalog is
  keyed by the image identity, so the original bytes are known exactly; a
  mismatch means the patch is reaching memory it was not authored against and
  the emulator refuses it.
- Every patch of a cheat applies together. If one fails its check, the patches
  already applied are rolled back.
- Cheat IDs must be unique within a document and stable across edits. The
  emulator derives its internal code names from them.
- Addresses are guest addresses after loading, not file offsets. For a Raptor
  module, that is the ELF section address the loader maps.
- A patch may target executable memory. Code sections are mapped writable and
  the interpreter keeps no decoded-instruction cache, so a patched branch takes
  effect on the next fetch.

## Generated files

`index.json` lists every published title with its descriptor fields and cheat
count. `aliases.json` maps container hashes and readable carrier keys such as
`lgt-00027baa-pd116132-01.00.06` to an image hash; a key that would reach more
than one image is omitted rather than guessed at. Both are produced by
`tools/validate.py`, and CI runs it with `--check` to reject a stale index.
