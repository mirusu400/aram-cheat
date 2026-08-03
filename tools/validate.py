#!/usr/bin/env python3
"""Check every catalog in this repository and regenerate the browse indexes.

The emulator's parser rejects unknown fields and unmet constraints, so a
document that fails here would also fail in the product. Run it before opening
a pull request; CI runs the same checks with --check, which fails when a
generated index is out of date.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TITLES = ROOT / "titles"
INDEX = ROOT / "index.json"
ALIASES = ROOT / "aliases.json"

CATALOG_VERSION = 2
MAX_PATCH_BYTES = 1 << 20

SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHEAT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
HEX_BYTES = re.compile(r"^(?:[0-9a-f]{2})+$")

TITLE_FIELDS = {
    "image_sha256",
    "file_sha256",
    "name",
    "carrier",
    "format",
    "profile_id",
    "aid",
    "pid",
    "version",
    "vendor",
}
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

# Fields copied from a catalog title into the browse index.
INDEX_TITLE_FIELDS = ("name", "carrier", "format", "aid", "pid", "version", "vendor")


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

    image = title.get("image_sha256")
    if not isinstance(image, str) or not SHA256.match(image):
        failures.append(f"{where}: image_sha256 must be 64 lowercase hex characters")
    elif path.stem != image:
        failures.append(f"{where}: file name does not match image_sha256 {image}")

    files = title.get("file_sha256", [])
    if not isinstance(files, list):
        failures.append(f"{where}: file_sha256 must be an array")
    else:
        for index, value in enumerate(files):
            if not isinstance(value, str) or not SHA256.match(value):
                failures.append(
                    f"{where}: file_sha256[{index}] must be 64 lowercase hex characters"
                )
    for field in ("name", "carrier", "format", "profile_id", "aid", "pid", "version", "vendor"):
        if field in title and not isinstance(title[field], str):
            failures.append(f"{where} title: {field} must be a string")

    cheats = document.get("cheats")
    if not isinstance(cheats, list) or not cheats:
        failures.append(f"{where}: cheats must be a non-empty array")
        return document
    seen: set = set()
    for index, cheat in enumerate(cheats):
        validate_cheat(f"{where} cheat {index}", cheat, seen, failures)
    return document


def build_index(catalogs: dict) -> dict:
    titles = []
    for image in sorted(catalogs):
        title = catalogs[image].get("title", {})
        entry = {"image_sha256": image}
        for field in INDEX_TITLE_FIELDS:
            if title.get(field):
                entry[field] = title[field]
        entry["file_sha256"] = list(title.get("file_sha256", []))
        entry["cheats"] = len(catalogs[image].get("cheats", []))
        titles.append(entry)
    return {"version": CATALOG_VERSION, "titles": titles}


def descriptor_alias(title: dict) -> str | None:
    """A readable key from the carrier descriptor.

    Carrier identifiers are not unique: across a 280-package corpus one AID
    covers as many as twelve unrelated titles. Aliases exist so a person can
    find an entry, never so the product can authorize a patch, and a key that
    reaches more than one image is dropped from the map rather than guessed at.
    """
    carrier = (title.get("carrier") or "").strip().lower()
    aid = (title.get("aid") or "").strip().lower()
    pid = (title.get("pid") or "").strip().lower()
    version = (title.get("version") or "").strip().lower()
    if not carrier or not aid:
        return None
    parts = [carrier, aid]
    if pid:
        parts.append(pid)
    if version:
        parts.append(version)
    return "-".join(parts)


def build_aliases(catalogs: dict, failures: Failures) -> dict:
    by_file: dict[str, str] = {}
    by_descriptor: dict[str, set] = {}
    for image, catalog in sorted(catalogs.items()):
        title = catalog.get("title", {})
        for file_hash in title.get("file_sha256", []):
            if by_file.get(file_hash, image) != image:
                failures.append(
                    f"file_sha256 {file_hash} is claimed by two images: "
                    f"{by_file[file_hash]} and {image}"
                )
                continue
            by_file[file_hash] = image
        alias = descriptor_alias(title)
        if alias:
            by_descriptor.setdefault(alias, set()).add(image)

    ambiguous = sorted(key for key, images in by_descriptor.items() if len(images) > 1)
    for key in ambiguous:
        print(
            f"note: descriptor alias {key!r} covers "
            f"{len(by_descriptor[key])} images and is omitted",
            file=sys.stderr,
        )
    return {
        "version": CATALOG_VERSION,
        "note": (
            "Lookup aid for humans and tooling. The product resolves catalogs by "
            "image_sha256; these keys are not authoritative."
        ),
        "by_file_sha256": dict(sorted(by_file.items())),
        "by_descriptor": {
            key: sorted(images)[0]
            for key, images in sorted(by_descriptor.items())
            if len(images) == 1
        },
    }


def write_generated(path: pathlib.Path, document: dict, check: bool, failures: Failures) -> None:
    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    where = path.relative_to(ROOT).as_posix()
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != rendered:
            failures.append(f"{where} is out of date; run python tools/validate.py")
        return
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of rewriting index.json and aliases.json",
    )
    arguments = parser.parse_args()

    failures = Failures()
    catalogs = {}
    if TITLES.is_dir():
        for path in sorted(TITLES.glob("*.json")):
            document = validate_catalog(path, failures)
            if document is not None:
                catalogs[path.stem] = document

    write_generated(INDEX, build_index(catalogs), arguments.check, failures)
    write_generated(ALIASES, build_aliases(catalogs, failures), arguments.check, failures)

    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        print(f"\n{len(failures)} problem(s) found", file=sys.stderr)
        return 1
    print(f"validated {len(catalogs)} catalog(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
