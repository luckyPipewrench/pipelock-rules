#!/bin/bash
# Compile individual rule YAML files into a single bundle.yaml.
# Rules are sorted by type then ID for deterministic output.
set -euo pipefail

cat <<'HEADER'
format_version: 1
name: pipelock-community
version: "2026.03.1"
author: pipelock
description: "Community detection rules for AI agent traffic"
homepage: "https://pipelab.org/rules/pipelock-community"
min_pipelock: "1.4.0"
license: "Apache-2.0"

rules:
HEADER

# Concatenate all rule files in sorted order (type dirs, then filenames)
for dir in rules/dlp rules/injection rules/tool-poison; do
  if [ -d "$dir" ]; then
    for f in $(ls "$dir"/*.yaml 2>/dev/null | sort); do
      cat "$f"
      echo ""
    done
  fi
done
