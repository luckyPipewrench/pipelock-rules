#!/bin/bash
# Test all rule regexes against their fixture files.
# Each rule should have matching fixtures in fixtures/{type}/:
#   {rule-id}-true-positive.txt  — lines that MUST match
#   {rule-id}-false-positive.txt — lines that MUST NOT match
#
# Uses Go's regexp package via a small helper, or falls back to grep -P.
set -euo pipefail

PASS=0
FAIL=0
SKIP=0

# Extract rule ID and regex from compiled bundle
extract_rules() {
  local bundle="published/pipelock-community/bundle.yaml"
  if [ ! -f "$bundle" ]; then
    echo "ERROR: bundle not compiled. Run 'make compile' first." >&2
    exit 1
  fi
  # Parse rule IDs and regexes (simple grep, not a full YAML parser)
  grep -A20 '^\s*- id:' "$bundle" | \
    awk '/^\s*- id:/{id=$3} /^\s*regex:/{gsub(/^\s*regex:\s*/, ""); gsub(/^'\''|'\''$/, ""); print id " " $0}'
}

while IFS=' ' read -r rule_id regex; do
  # Determine rule type from directory
  type=""
  for t in dlp injection tool-poison; do
    if [ -f "fixtures/$t/${rule_id}-true-positive.txt" ]; then
      type="$t"
      break
    fi
  done

  if [ -z "$type" ]; then
    echo "SKIP: $rule_id (no fixtures)"
    SKIP=$((SKIP + 1))
    continue
  fi

  tp_file="fixtures/$type/${rule_id}-true-positive.txt"
  fp_file="fixtures/$type/${rule_id}-false-positive.txt"

  # Test true positives (each line must match)
  if [ -f "$tp_file" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      if echo "$line" | grep -qP "(?i)$regex" 2>/dev/null; then
        PASS=$((PASS + 1))
      else
        echo "FAIL: $rule_id true-positive did not match: $line"
        FAIL=$((FAIL + 1))
      fi
    done < "$tp_file"
  fi

  # Test false positives (each line must NOT match)
  if [ -f "$fp_file" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      if echo "$line" | grep -qP "(?i)$regex" 2>/dev/null; then
        echo "FAIL: $rule_id false-positive matched: $line"
        FAIL=$((FAIL + 1))
      else
        PASS=$((PASS + 1))
      fi
    done < "$fp_file"
  fi

done < <(extract_rules)

echo ""
echo "Results: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ] || exit 1
