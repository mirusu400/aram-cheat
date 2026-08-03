#!/usr/bin/env python3
"""Check every catalog in this repository against the version 1 schema.

The emulator's parser rejects unknown fields and unmet constraints, so a
document that fails here would also fail in the product. Run it before opening
a pull request; CI runs the same checks.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TITLES = ROOT / "titles"
INDEX = ROOT / "index.json"

CATALOG_VERSION = 1
MAX_PATCH_BYTES = 1 << 20

SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHEAT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
HEX_BYTES = re.compile(r"^(?:[0-9a-f]{2})+$")

TITLE_FIELDS = {"sha256", "name", "carrier", "format", "profile_id"}
CHEAT_FIELDS = {
    "id",
    "name",
    "description",
    "category",
    "author",
    "reference",
    "freeze",
    "restore_on_disable",
    "patches",
}
PATCH_FIELDS = {"address", "value", "expected", "note"}
INDEX_ENTRY_FIELDS = {"sha256", "name", "carrier", "format", "cheats"}


class Failures(list):
    def check(self, condition: bool, message: str) -> bool:
        if not condition:
            self.append(message)
        return condition


def unknown_fields(where: str, value: dict, allowed: set, failures: Failures) -> None:
    for key in sorted(set(value) - allowed):
        failures.append(f"{where}: unknown field {key!r}")


def parse_address(where: str, value, failures: Failures) -> int | None:
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            number = int(text, 16 if text.lower().startswith("0x") else 10)
        except ValueError:
            failures.append(f"{where}: address {value!r} is not a number")
            return None
    else:
        failures.append(f"{where}: address must be a string or a number")
        return None
    if not 0 <= number <= 0xFFFFFFFF:
        failures.append(f"{where}: address {value!r} is outside the guest address space")
        return None
    return number


def parse_bytes(where: str, name: str, value, failures: Failures) -> bytes | None:
    if not isinstance(value, str):
        failures.append(f"{where}: {name} must be a hexadecimal string")
        return None
    text = value.replace(" ", "").lower()
    if not text or not HEX_BYTES.match(text):
        failures.append(f"{where}: {name} {value!r} is not an even-length hex string")
        return None
    return bytes.fromhex(text)


def validate_patch(where: str, patch, failures: Failures) -> None:
    if not failures.check(isinstance(patch, dict), f"{where}: patch must be an object"):
        return
    unknown_fields(where, patch, PATCH_FIELDS, failures)
    if "address" not in patch:
        failures.append(f"{where}: address is required")
    else:
        parse_address(where, patch["address"], failures)
    value = parse_bytes(where, "value", patch.get("value"), failures)
    expected = parse_bytes(where, "expected", patch.get("expected"), failures)
    if value is not None and not 0 < len(value) <= MAX_PATCH_BYTES:
        failures.append(f"{where}: value length {len(value)} is outside 1..{MAX_PATCH_BYTES}")
    if value is not None and expected is not None and len(value) != len(expected):
        failures.append(
            f"{where}: expected is {len(expected)} bytes but value writes {len(value)}"
        )
    if value is not None and expected is not None and value == expected:
        failures.append(f"{where}: value equals expected, so the patch changes nothing")


def validate_cheat(where: str, cheat, seen: set, failures: Failures) -> None:
    if not failures.check(isinstance(cheat, dict), f"{where}: cheat must be an object"):
        return
    unknown_fields(where, cheat, CHEAT_FIELDS, failures)
    identity = cheat.get("id")
    if not isinstance(identity, str) or not CHEAT_ID.match(identity):
        failures.append(f"{where}: id {identity!r} must match {CHEAT_ID.pattern}")
    elif identity in seen:
        failures.append(f"{where}: duplicate cheat id {identity!r}")
    else:
        seen.add(identity)
    if not isinstance(cheat.get("name"), str) or not cheat["name"].strip():
        failures.append(f"{where}: name is required")
    for field in ("description", "category", "author", "reference"):
        if field in cheat and not isinstance(cheat[field], str):
            failures.append(f"{where}: {field} must be a string")
    for field in ("freeze", "restore_on_disable"):
        if field in cheat and not isinstance(cheat[field], bool):
            failures.append(f"{where}: {field} must be true or false")
    patches = cheat.get("patches")
    if not isinstance(patches, list) or not patches:
        failures.append(f"{where}: patches must be a non-empty array")
        return
    for index, patch in enumerate(patches):
        validate_patch(f"{where} patch {index}", patch, failures)


def validate_catalog(path: pathlib.Path, failures: Failures) -> dict | None:
    where = path.relative_to(ROOT).as_posix()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"{where}: {error}")
        return None
    if not failures.check(isinstance(document, dict), f"{where}: must be an object"):
        return None
    unknown_fields(where, document, {"version", "title", "cheats"}, failures)
    if document.get("version") != CATALOG_VERSION:
        failures.append(f"{where}: version must be {CATALOG_VERSION}")

    title = document.get("title")
    if not isinstance(title, dict):
        failures.append(f"{where}: title must be an object")
        return None
    unknown_fields(f"{where} title", title, TITLE_FIELDS, failures)
    sha256 = title.get("sha256")
    if not isinstance(sha256, str) or not SHA256.match(sha256):
        failures.append(f"{where}: title sha256 must be 64 lowercase hex characters")
    elif path.stem != sha256:
        failures.append(f"{where}: file name does not match title sha256 {sha256}")

    cheats = document.get("cheats")
    if not isinstance(cheats, list) or not cheats:
        failures.append(f"{where}: cheats must be a non-empty array")
        return document
    seen: set = set()
    for index, cheat in enumerate(cheats):
        validate_cheat(f"{where} cheat {index}", cheat, seen, failures)
    return document


def validate_index(catalogs: dict, failures: Failures) -> None:
    where = INDEX.relative_to(ROOT).as_posix()
    try:
        document = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"{where}: {error}")
        return
    if not isinstance(document, dict) or document.get("version") != CATALOG_VERSION:
        failures.append(f"{where}: version must be {CATALOG_VERSION}")
        return
    unknown_fields(where, document, {"version", "titles"}, failures)
    titles = document.get("titles")
    if not isinstance(titles, list):
        failures.append(f"{where}: titles must be an array")
        return

    listed = set()
    for index, entry in enumerate(titles):
        entry_where = f"{where} entry {index}"
        if not isinstance(entry, dict):
            failures.append(f"{entry_where}: must be an object")
            continue
        unknown_fields(entry_where, entry, INDEX_ENTRY_FIELDS, failures)
        sha256 = entry.get("sha256")
        if not isinstance(sha256, str) or not SHA256.match(sha256):
            failures.append(f"{entry_where}: sha256 must be 64 lowercase hex characters")
            continue
        listed.add(sha256)
        catalog = catalogs.get(sha256)
        if catalog is None:
            failures.append(f"{entry_where}: no titles/{sha256}.json exists")
            continue
        count = entry.get("cheats")
        published = len(catalog.get("cheats", []))
        if count != published:
            failures.append(
                f"{entry_where}: cheats says {count!r} but the catalog publishes {published}"
            )
        for field in ("name", "carrier", "format"):
            if field in entry and entry[field] != catalog.get("title", {}).get(field):
                failures.append(f"{entry_where}: {field} disagrees with the catalog")

    for sha256 in sorted(set(catalogs) - listed):
        failures.append(f"{where}: titles/{sha256}.json is not listed")


def main() -> int:
    failures = Failures()
    catalogs = {}
    if TITLES.is_dir():
        for path in sorted(TITLES.glob("*.json")):
            document = validate_catalog(path, failures)
            if document is not None:
                catalogs[path.stem] = document
    if INDEX.exists():
        validate_index(catalogs, failures)
    else:
        failures.append("index.json is missing")

    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        print(f"\n{len(failures)} problem(s) found", file=sys.stderr)
        return 1
    print(f"validated {len(catalogs)} catalog(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
