#!/usr/bin/env python3
"""Validate the closed compatibility contract and its exact published bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FIELD_RE = re.compile(r"^(\s*)([a-z][a-z0-9_]*): ?(?:\"([^\"]*)\"|(.*\S))$")


def parse_contract(path: pathlib.Path) -> tuple[dict[int, dict[str, str]], list[dict[str, str]]]:
    """Parse the intentionally small YAML subset and reject every unknown field."""
    top_allowed = {"contract_version", "format_identities", "bundles"}
    identity_allowed = {"format_version", "schema_file", "schema_sha256", "reader"}
    bundle_allowed = {"name", "version", "bundle_sha256", "format_version", "min_pipelock", "tested_through_pipelock", "semantics", "rollback"}
    top_seen: set[str] = set()
    identities: list[dict[str, str]] = []
    bundles: list[dict[str, str]] = []
    section = ""
    current: dict[str, str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            list_key = re.fullmatch(r"([a-z][a-z0-9_]*):", line)
            if list_key:
                key = list_key.group(1)
                if key not in top_allowed or key in top_seen or key == "contract_version":
                    raise ValueError(f"unknown or duplicate contract field {key!r}")
                top_seen.add(key)
                section, current = key, None
                continue
            field = FIELD_RE.match(line)
            if field is None:
                raise ValueError(f"cannot parse contract line: {line}")
            key = field.group(2)
            if key not in top_allowed or key in top_seen:
                raise ValueError(f"unknown or duplicate contract field {key!r}")
            top_seen.add(key)
            value = field.group(3) or field.group(4)
            if key == "contract_version":
                if value != "1":
                    raise ValueError("contract_version must be exactly 1")
            elif value:
                raise ValueError(f"{key} must be a list")
            else:
                section, current = key, None
            continue
        item = re.match(r"\s+- ([a-z][a-z0-9_]*): ?(?:\"([^\"]*)\"|(\S+))$", line)
        if item:
            if section not in {"format_identities", "bundles"}:
                raise ValueError(f"unexpected list item: {line}")
            current = {item.group(1): item.group(2) or item.group(3)}
            (identities if section == "format_identities" else bundles).append(current)
            continue
        field = FIELD_RE.match(line)
        if field is None or current is None:
            raise ValueError(f"cannot parse contract line: {line}")
        key = field.group(2)
        allowed = identity_allowed if section == "format_identities" else bundle_allowed
        if key not in allowed or key in current:
            raise ValueError(f"unknown or duplicate {section} field {key!r}")
        current[key] = field.group(3) or field.group(4)
    if top_seen != top_allowed:
        raise ValueError(f"missing contract field(s): {', '.join(sorted(top_allowed - top_seen))}")
    by_format: dict[int, dict[str, str]] = {}
    for identity in identities:
        if set(identity) != identity_allowed:
            raise ValueError("format identity has missing fields")
        version = int(identity["format_version"])
        if version in by_format:
            raise ValueError(f"duplicate format_version {version}")
        by_format[version] = identity
    return by_format, bundles


def top_level_fields(path: pathlib.Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        list_key = re.fullmatch(r"([a-z][a-z0-9_]*):", raw)
        if list_key:
            fields[list_key.group(1)] = ""
            continue
        match = FIELD_RE.match(raw)
        if match and not match.group(1):
            key = match.group(2)
            if key in fields:
                raise ValueError(f"duplicate bundle field {key!r}")
            fields[key] = match.group(3) or match.group(4)
    return fields


def validate_schema(bundle_path: pathlib.Path, schema_path: pathlib.Path) -> list[str]:
    """Validate the schema's top-level contract without adding a YAML dependency."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("additionalProperties") is not False:
        return ["schema must set additionalProperties: false"]
    allowed = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    fields = top_level_fields(bundle_path)
    errors = [f"unknown reader field {field!r}" for field in sorted(set(fields) - allowed)]
    errors.extend(f"missing required field {field!r}" for field in sorted(required - set(fields)))
    if fields.get("format_version") != "1":
        errors.append("format_version must be 1")
    if not SEMVER_RE.fullmatch(fields.get("version", "")):
        errors.append("version must be CalVer major.minor.patch")
    if not SEMVER_RE.fullmatch(fields.get("min_pipelock", "")):
        errors.append("min_pipelock must be major.minor.patch")
    if fields.get("rules") != "":
        errors.append("rules must be a YAML sequence key")
    return errors


def check(root: pathlib.Path) -> tuple[dict[int, dict[str, str]], list[dict[str, str]], list[str]]:
    identities, bundles = parse_contract(root / "compatibility" / "contract.yaml")
    errors: list[str] = []
    seen_names: set[str] = set()
    required = {"name", "version", "bundle_sha256", "format_version", "min_pipelock", "tested_through_pipelock", "semantics", "rollback"}
    for version, identity in identities.items():
        schema_path = root / identity["schema_file"]
        if not schema_path.is_file():
            errors.append(f"format {version}: schema file missing")
        elif hashlib.sha256(schema_path.read_bytes()).hexdigest() != identity["schema_sha256"]:
            errors.append(f"format {version}: schema_sha256 mismatch")
    for bundle in bundles:
        if set(bundle) != required:
            errors.append("bundle entry has missing or unknown fields")
            continue
        name = bundle["name"]
        if name in seen_names:
            errors.append(f"duplicate bundle entry {name}")
            continue
        seen_names.add(name)
        try:
            identity = identities[int(bundle["format_version"])]
        except (KeyError, ValueError):
            errors.append(f"{name}: no identity for format_version {bundle['format_version']}")
            continue
        if not SHA256_RE.fullmatch(bundle["bundle_sha256"]):
            errors.append(f"{name}: bundle_sha256 must be 64 lowercase hex characters")
        for field in ("min_pipelock", "tested_through_pipelock"):
            if not SEMVER_RE.fullmatch(bundle[field]):
                errors.append(f"{name}: {field} must be major.minor.patch")
        if SEMVER_RE.fullmatch(bundle["min_pipelock"]) and SEMVER_RE.fullmatch(bundle["tested_through_pipelock"]) and tuple(map(int, bundle["tested_through_pipelock"].split("."))) < tuple(map(int, bundle["min_pipelock"].split("."))):
            errors.append(f"{name}: tested_through_pipelock is below min_pipelock")
        bundle_path = root / "published" / name / "bundle.yaml"
        if not bundle_path.is_file():
            errors.append(f"{name}: published bundle missing")
            continue
        if hashlib.sha256(bundle_path.read_bytes()).hexdigest() != bundle["bundle_sha256"]:
            errors.append(f"{name}: bundle_sha256 does not match published bytes")
        fields = top_level_fields(bundle_path)
        for field in ("name", "version", "format_version", "min_pipelock"):
            if fields.get(field) != bundle[field]:
                errors.append(f"{name}: {field} does not match published bundle")
        errors.extend(f"{name}: schema: {error}" for error in validate_schema(bundle_path, root / identity["schema_file"]))
    published_names = {path.parent.name for path in (root / "published").glob("*/bundle.yaml")}
    if missing := sorted(published_names - seen_names):
        errors.append(f"published bundle(s) missing contract entry: {', '.join(missing)}")
    if extra := sorted(seen_names - published_names):
        errors.append(f"contract references unpublished bundle(s): {', '.join(extra)}")
    return identities, bundles, errors


def tested_through_for(bundles: list[dict[str, str]], name: str, actual_version: str | None = None) -> str:
    """Return a bundle's tested reader version, requiring an exact live match when supplied."""
    for bundle in bundles:
        if bundle["name"] != name:
            continue
        expected = bundle["tested_through_pipelock"]
        if actual_version is not None and actual_version != expected:
            raise ValueError(f"{name} tests v{actual_version}, contract pins v{expected}")
        return expected
    raise ValueError(f"unknown bundle {name!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--check-bundle-ceiling")
    parser.add_argument("--actual-version")
    args = parser.parse_args(argv)
    if bool(args.check_bundle_ceiling) != bool(args.actual_version):
        parser.error("--check-bundle-ceiling and --actual-version must be provided together")
    try:
        identities, bundles, errors = check(args.root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as err:
        print(f"compatibility contract: FAIL - {err}", file=sys.stderr)
        return 1
    if args.check_bundle_ceiling:
        if errors:
            print("compatibility contract: FAIL", file=sys.stderr)
            print("\n".join(f"  - {error}" for error in errors), file=sys.stderr)
            return 1
        try:
            print(tested_through_for(bundles, args.check_bundle_ceiling, args.actual_version))
        except ValueError as err:
            print(f"compatibility contract: FAIL - {err}", file=sys.stderr)
            return 1
        return 0
    if errors:
        print("compatibility contract: FAIL", file=sys.stderr)
        print("\n".join(f"  - {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"compatibility contract: PASS ({len(bundles)} bundles, {len(identities)} format identities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
