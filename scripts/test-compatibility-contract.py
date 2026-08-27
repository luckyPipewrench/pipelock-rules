#!/usr/bin/env python3
"""Regression tests for compatibility contract validation."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr


ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("compatibility", ROOT / "scripts" / "check-compatibility-contract.py")
assert SPEC and SPEC.loader
compatibility = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compatibility)


class CompatibilityContractTests(unittest.TestCase):
    def copied_root(self) -> pathlib.Path:
        temp = pathlib.Path(tempfile.mkdtemp(prefix="pipelock-rules-contract-"))
        self.addCleanup(shutil.rmtree, temp)
        shutil.copytree(ROOT / "compatibility", temp / "compatibility")
        shutil.copytree(ROOT / "published", temp / "published")
        return temp

    def check(self, root: pathlib.Path) -> list[str]:
        _, _, errors = compatibility.check(root)
        return errors

    def replace_header(self, path: pathlib.Path, field: str, value: str) -> None:
        content = path.read_text(encoding="utf-8")
        updated, count = re.subn(rf"^{re.escape(field)}:.*$", f"{field}: {value}", content, count=1, flags=re.MULTILINE)
        self.assertEqual(count, 1)
        path.write_text(updated, encoding="utf-8")

    def test_current_contract_passes(self) -> None:
        self.assertEqual(self.check(self.copied_root()), [])

    def test_byte_mutation_fails(self) -> None:
        root = self.copied_root()
        path = root / "published" / "pipelock-community" / "bundle.yaml"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assertTrue(any("bundle_sha256" in error for error in self.check(root)))

    def test_ceiling_mutation_fails(self) -> None:
        root = self.copied_root()
        contract = root / "compatibility" / "contract.yaml"
        contract.write_text(contract.read_text(encoding="utf-8").replace('tested_through_pipelock: "3.4.0"', 'tested_through_pipelock: "1.3.9"', 1), encoding="utf-8")
        self.assertTrue(any("tested_through_pipelock" in error for error in self.check(root)))

    def test_actual_version_must_equal_tested_ceiling(self) -> None:
        _, bundles, errors = compatibility.check(self.copied_root())
        self.assertEqual(errors, [])
        self.assertEqual(compatibility.tested_through_for(bundles, "pipelock-community", "3.4.0"), "3.4.0")
        with self.assertRaisesRegex(ValueError, r"tests v999\.0\.0, contract pins v3\.4\.0"):
            compatibility.tested_through_for(bundles, "pipelock-community", "999.0.0")

    def test_bundle_ceiling_cli_requires_actual_version(self) -> None:
        for args in (
            ["--check-bundle-ceiling", "pipelock-community"],
            ["--actual-version", "3.4.0"],
        ):
            with self.subTest(args=args), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_error:
                    compatibility.main(args)
            self.assertEqual(exit_error.exception.code, 2)

    def test_contract_version_and_unknown_field_fail(self) -> None:
        for mutation in ('contract_version: 2', 'unknown_field: true'):
            with self.subTest(mutation=mutation):
                root = self.copied_root()
                contract = root / "compatibility" / "contract.yaml"
                content = contract.read_text(encoding="utf-8")
                contract.write_text(content.replace("contract_version: 1", mutation, 1), encoding="utf-8")
                with self.assertRaises(ValueError):
                    compatibility.check(root)

    def test_unknown_reader_field_fails(self) -> None:
        root = self.copied_root()
        path = root / "published" / "healthcare-phi-pii" / "bundle.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("format_version: 1", "format_version: 1\nunknown_reader_field: true", 1), encoding="utf-8")
        self.assertTrue(any("unknown reader field" in error for error in self.check(root)))

    def test_schema_rejects_required_header_wrong_types_and_empty_strings(self) -> None:
        for field, value, expected in (
            ("author", '""', "must not be empty"),
            ("author", "1", "must be a string"),
            ("description", '""', "must not be empty"),
            ("license", "false", "must be a string"),
            ("rules", '"not a sequence"', "must be a array"),
        ):
            with self.subTest(field=field, value=value):
                root = self.copied_root()
                path = root / "published" / "healthcare-phi-pii" / "bundle.yaml"
                self.replace_header(path, field, value)
                self.assertTrue(any(expected in error for error in self.check(root)))

        root = self.copied_root()
        path = root / "published" / "healthcare-phi-pii" / "bundle.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace(
            'license: "Apache-2.0"', 'license: "Apache-2.0"\nmonotonic_version: 0', 1,
        ), encoding="utf-8")
        self.assertTrue(any("monotonic_version must be at least 1" in error for error in self.check(root)))

    def test_schema_file_must_stay_beneath_compatibility(self) -> None:
        for path in ("/tmp/schema.json", "compatibility/../published/pipelock-community/bundle.yaml"):
            with self.subTest(path=path):
                root = self.copied_root()
                contract = root / "compatibility" / "contract.yaml"
                contract.write_text(contract.read_text(encoding="utf-8").replace(
                    "compatibility/pipelock-rules-format-v1.schema.json", path, 1,
                ), encoding="utf-8")
                self.assertTrue(any("schema_file must" in error for error in self.check(root)))

    def test_bundle_name_must_stay_beneath_published(self) -> None:
        for name in ("/tmp/bundle", "../compatibility"):
            with self.subTest(name=name):
                root = self.copied_root()
                contract = root / "compatibility" / "contract.yaml"
                contract.write_text(contract.read_text(encoding="utf-8").replace(
                    "name: pipelock-community", f"name: {name}", 1,
                ), encoding="utf-8")
                self.assertTrue(any("bundle name must" in error for error in self.check(root)))

    def test_schema_rejects_unsupported_keywords_and_types_without_crashing(self) -> None:
        root = self.copied_root()
        bundle = root / "published" / "healthcare-phi-pii" / "bundle.yaml"
        schema_path = root / "compatibility" / "pipelock-rules-format-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        schema["properties"]["author"]["enum"] = ["maintainer"]
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        self.assertTrue(any("unsupported keyword 'enum'" in error for error in compatibility.validate_schema(bundle, schema_path)))

        schema["properties"]["author"].pop("enum")
        schema["properties"]["author"]["type"] = ["string", "null"]
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        self.assertTrue(any("unsupported type" in error for error in compatibility.validate_schema(bundle, schema_path)))


if __name__ == "__main__":
    unittest.main()
