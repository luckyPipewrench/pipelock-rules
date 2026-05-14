#!/bin/bash
# Test all rule regexes against their bundle fixture files.
set -euo pipefail

BUNDLE_NAME="${BUNDLE_NAME:-pipelock-community}"
BUNDLE_FILE="${BUNDLE_FILE:-published/$BUNDLE_NAME/bundle.yaml}"
FIXTURE_ROOT="fixtures/$BUNDLE_NAME"
export BUNDLE_FILE FIXTURE_ROOT

if [ ! -f "$BUNDLE_FILE" ]; then
  echo "ERROR: bundle not compiled at $BUNDLE_FILE. Run 'make compile' first." >&2
  exit 1
fi

if [ ! -d "$FIXTURE_ROOT" ]; then
  echo "ERROR: no fixtures found for bundle '$BUNDLE_NAME' at $FIXTURE_ROOT" >&2
  exit 1
fi

python3 <<'PY'
import os
import pathlib
import re
import sys

bundle = pathlib.Path(os.environ["BUNDLE_FILE"])
fixture_root = pathlib.Path(os.environ["FIXTURE_ROOT"])
text = bundle.read_text()

rules = []
current_id = None
for line in text.splitlines():
    m_id = re.match(r"^\s*- id:\s*(\S+)\s*$", line)
    if m_id:
        current_id = m_id.group(1)
        continue
    m_rx = re.match(r"^\s*regex:\s*'(.*)'\s*$", line)
    if m_rx and current_id:
        pattern = m_rx.group(1).replace("''", "'")
        rules.append((current_id, pattern))
        current_id = None

passes = 0
fails = 0
skipped = 0


def find_type(rule_id):
    for rule_type in ("dlp", "injection", "tool-poison"):
        if (fixture_root / rule_type / f"{rule_id}-true-positive.txt").exists():
            return rule_type
        if (fixture_root / rule_type / f"{rule_id}-false-positive.txt").exists():
            return rule_type
    return None


for rule_id, pattern in rules:
    rule_type = find_type(rule_id)
    if rule_type is None:
        print(f"SKIP: {rule_id} (no fixtures)")
        skipped += 1
        continue

    try:
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as exc:
        print(f"FAIL: {rule_id} bad regex: {exc}")
        fails += 1
        continue

    tp_file = fixture_root / rule_type / f"{rule_id}-true-positive.txt"
    fp_file = fixture_root / rule_type / f"{rule_id}-false-positive.txt"

    if tp_file.exists():
        for line in tp_file.read_text().splitlines():
            if not line.strip():
                continue
            if compiled.search(line):
                passes += 1
            else:
                print(f"FAIL: {rule_id} true-positive did not match: {line}")
                fails += 1

    if fp_file.exists():
        for line in fp_file.read_text().splitlines():
            if not line.strip():
                continue
            if compiled.search(line):
                print(f"FAIL: {rule_id} false-positive matched: {line}")
                fails += 1
            else:
                passes += 1

print()
print(f"Results: {passes} passed, {fails} failed, {skipped} skipped")
sys.exit(0 if fails == 0 else 1)
PY
