# Catalog schema

Version 1. The emulator's parser lives in `aram-core/cheat/catalog.go` and
rejects unknown fields, so a document that a newer schema produced fails
loudly instead of losing data.

## Document

`titles/<sha256>.json`, where `<sha256>` is the lowercase SHA-256 of the input
file. The `sha256` inside the document must match the file name.

```json
{
  "version": 1,
  "title": {
    "sha256": "3cc7a9b4cb15818cdd5a66f7e520c7b9b36f1df8d2df096aafa961b1cb2b682c",
    "name": "제노니아 1",
    "carrier": "lgt",
    "format": "raptor-wipi-c",
    "profile_id": "wipi-1.2.1/lgt/raptor"
  },
  "cheats": [
    {
      "id": "skip-server-authentication",
      "name": "Skip server authentication",
      "description": "Starts the game without the Gamevil SMS authentication.",
      "category": "bypass",
      "author": "aram",
      "reference": "https://github.com/mirusu400/aram-emu/issues/4",
      "restore_on_disable": true,
      "patches": [
        {
          "address": "0x0004a1c8",
          "value": "0000a0e1",
          "expected": "feffffeb",
          "note": "replace the authentication call with a no-op"
        }
      ]
    }
  ]
}
```

## Fields

### title

| Field | Required | Meaning |
| --- | --- | --- |
| `sha256` | yes | Lowercase SHA-256 of the input file, 64 hexadecimal characters. |
| `name` | no | Human-readable title. |
| `carrier` | no | `lgt`, `ktf`, `sktt`, or another carrier tag. |
| `format` | no | The loader format ARAM reports, such as `raptor-wipi-c`. |
| `profile_id` | no | The compatibility profile ARAM reports. |

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
| `address` | yes | Guest address, `"0x0004a1c8"`. A plain number is accepted. |
| `value` | yes | Replacement bytes, lowercase hexadecimal, in guest order. |
| `expected` | yes | The original bytes at that address, same length as `value`. |
| `note` | no | Why this patch exists. |

## Rules

- `expected` is mandatory and must be the same length as `value`. The catalog is
  keyed by the input hash, so the original bytes are known exactly; a mismatch
  means the patch is reaching memory it was not authored against and the
  emulator refuses it.
- Every patch of a cheat applies together. If one fails its check, the patches
  already applied are rolled back.
- Cheat IDs must be unique within a document and stable across edits. The
  emulator derives its internal code names from them.
- Addresses are guest addresses after loading, not file offsets. For a Raptor
  module, that is the ELF section address the loader maps.
- A patch may target executable memory. Code sections are mapped writable and
  the interpreter keeps no decoded-instruction cache, so a patched branch takes
  effect on the next fetch.
