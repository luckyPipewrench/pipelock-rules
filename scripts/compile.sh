#!/bin/bash
# Compile individual rule YAML files into a single bundle.yaml.
# Rules are sorted by type then ID for deterministic output.
set -euo pipefail

BUNDLE_NAME="${BUNDLE_NAME:-pipelock-community}"
RULE_ROOT="rules/$BUNDLE_NAME"

if [ ! -d "$RULE_ROOT" ]; then
  echo "ERROR: no rules found for bundle '$BUNDLE_NAME' at $RULE_ROOT" >&2
  exit 1
fi

case "$BUNDLE_NAME" in
  pipelock-community)
    VERSION="2026.03.1"
    AUTHOR="pipelock"
    DESCRIPTION="Community detection rules for AI agent traffic"
    HOMEPAGE="https://pipelab.org/rules/pipelock-community"
    ;;
  healthcare-phi-pii)
    VERSION="2026.05.1"
    AUTHOR="BGASoft, Inc."
    DESCRIPTION="PHI/PII detection rules for healthcare AI agents covering regex-detectable entries from HIPAA Safe Harbor's 18 identifiers, financial PII, and clinical-lab identifiers"
    HOMEPAGE="https://github.com/luckyPipewrench/pipelock-rules"
    ;;
  *)
    VERSION="${BUNDLE_VERSION:-0.1.0}"
    AUTHOR="${BUNDLE_AUTHOR:-community}"
    DESCRIPTION="${BUNDLE_DESCRIPTION:-Community detection rules for Pipelock}"
    HOMEPAGE="${BUNDLE_HOMEPAGE:-https://github.com/luckyPipewrench/pipelock-rules}"
    ;;
esac

cat <<HEADER
format_version: 1
name: $BUNDLE_NAME
version: "$VERSION"
author: $AUTHOR
description: "$DESCRIPTION"
homepage: "$HOMEPAGE"
min_pipelock: "1.4.0"
license: "Apache-2.0"

rules:
HEADER

# Concatenate all rule files in sorted order (type dirs, then filenames)
{
for dir in "$RULE_ROOT"/dlp "$RULE_ROOT"/injection "$RULE_ROOT"/tool-poison; do
  if [ -d "$dir" ]; then
    for f in $(find "$dir" -maxdepth 1 -type f -name '*.yaml' | sort); do
      cat "$f"
      echo ""
    done
  fi
done
} | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}'
