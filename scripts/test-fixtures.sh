#!/bin/bash
# Test bundle regexes with Go's production RE2 engine.
set -euo pipefail

BUNDLE_NAME="${BUNDLE_NAME:-pipelock-community}"
BUNDLE_FILE="${BUNDLE_FILE:-published/$BUNDLE_NAME/bundle.yaml}"
FIXTURE_ROOT="fixtures/$BUNDLE_NAME"

if [ ! -f "$BUNDLE_FILE" ]; then
  echo "ERROR: bundle not compiled at $BUNDLE_FILE. Run 'make compile' first." >&2
  exit 1
fi

if [ ! -d "$FIXTURE_ROOT" ]; then
  echo "ERROR: no fixtures found for bundle '$BUNDLE_NAME' at $FIXTURE_ROOT" >&2
  exit 1
fi

go run ./scripts/test-fixtures.go "$BUNDLE_FILE" "$FIXTURE_ROOT"
