#!/usr/bin/env bash
# Exercise the current Pipelock install reader at the tested ceiling and prove
# that incompatible format/minimum claims are rejected before installation.
set -euo pipefail

parse_pipelock_core_version() {
	local output="$1"
	local semver_core='(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
	local prerelease='(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*'
	local version_re="^pipelock version v?(${semver_core})(-${prerelease})?$"

	[[ "$output" =~ $version_re ]] || return 1
	printf '%s\n' "${BASH_REMATCH[1]}"
}

if [[ "${1:-}" == "--parse-version" ]]; then
	[[ $# -eq 2 ]] || { printf 'usage: %s --parse-version OUTPUT\n' "$0" >&2; exit 2; }
	parse_pipelock_core_version "$2"
	exit
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_root="${TMPDIR:-/tmp}"
mkdir -p "$tmp_root"
tmp="$(mktemp -d "$tmp_root/pipelock-rules-compat.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
version_output="$(pipelock --version)" || {
	printf 'compatibility install: FAIL - cannot read pipelock version\n' >&2
	exit 1
}
actual_version="$(parse_pipelock_core_version "$version_output")" || {
	printf 'compatibility install: FAIL - cannot read pipelock version\n' >&2
	exit 1
}

install_case() {
	local name="$1" source="$2" expected="$3"
	local source_dir="$tmp/$name"
	mkdir -p "$source_dir"
	cp "$source" "$source_dir/bundle.yaml"
	if pipelock rules install --path "$source_dir" --allow-unsigned --rules-dir "$tmp/installed" >"$tmp/$name.out" 2>"$tmp/$name.err"; then
		if [[ "$expected" != "pass" ]]; then
			printf 'compatibility install: FAIL - %s installed unexpectedly\n' "$name" >&2
			return 1
		fi
		return 0
	fi
	if [[ "$expected" == "pass" ]]; then
		printf 'compatibility install: FAIL - %s did not install\n' "$name" >&2
		cat "$tmp/$name.err" >&2
		return 1
	fi
}

for bundle in pipelock-community healthcare-phi-pii; do
	python3 "$root/scripts/check-compatibility-contract.py" --check-bundle-ceiling "$bundle" --actual-version "$actual_version" >/dev/null
	positive="$tmp/$bundle-positive.yaml"
	sed "s/^name: .*/name: compatibility-${bundle}-positive/" "$root/published/$bundle/bundle.yaml" >"$positive"
	install_case "$bundle-positive" "$positive" pass
done

same_version_different_digest="$tmp/same-version-different-digest.yaml"
python3 - "$tmp/healthcare-phi-pii-positive.yaml" "$same_version_different_digest" <<'PY'
from pathlib import Path
import sys

source, dest = map(Path, sys.argv[1:])
dest.write_text(source.read_text(encoding="utf-8").replace(
    "Detects labeled 9-digit US bank routing (ABA RTN) numbers.",
    "Detects a deliberately changed routing-number description.",
    1,
), encoding="utf-8")
PY
install_case same-version-different-digest "$same_version_different_digest" fail
grep -q 'already installed with different digest' "$tmp/same-version-different-digest.err"

v1_optional_fields="$tmp/v1-optional-fields.yaml"
python3 - "$root/published/healthcare-phi-pii/bundle.yaml" "$v1_optional_fields" <<'PY'
from pathlib import Path
import sys

source, dest = map(Path, sys.argv[1:])
text = source.read_text(encoding="utf-8").replace(
    "name: healthcare-phi-pii", "name: compatibility-v1-optional-fields", 1,
)
text = text.replace(
    'license: "Apache-2.0"',
    'license: "Apache-2.0"\n'
    'tier: community\n'
    'monotonic_version: 1\n'
    'published_at: "2026-01-01T00:00:00Z"\n'
    'expires_at: "2027-01-01T00:00:00Z"\n'
    'required_features:\n'
    '  - mcp_tool_policy\n'
    'key_id: "sha256:compatibility-v1-optional-fields"',
    1,
)
dest.write_text(text, encoding="utf-8")
PY
install_case v1-optional-fields "$v1_optional_fields" pass

unknown_format="$tmp/unknown-format.yaml"
sed -e 's/^name: .*/name: compatibility-unknown-format/' -e 's/^format_version: .*/format_version: 99/' "$root/published/healthcare-phi-pii/bundle.yaml" >"$unknown_format"
install_case unknown-format "$unknown_format" fail
grep -q 'format_version' "$tmp/unknown-format.err"

future_minimum="$tmp/future-minimum.yaml"
sed -e 's/^name: .*/name: compatibility-future-minimum/' -e 's/^min_pipelock: .*/min_pipelock: "999.0.0"/' "$root/published/healthcare-phi-pii/bundle.yaml" >"$future_minimum"
install_case future-minimum "$future_minimum" fail
grep -q 'below minimum' "$tmp/future-minimum.err"

unknown_reader_field="$tmp/unknown-reader-field.yaml"
python3 - "$root/published/healthcare-phi-pii/bundle.yaml" "$unknown_reader_field" <<'PY'
from pathlib import Path
import sys

source, dest = map(Path, sys.argv[1:])
text = source.read_text(encoding="utf-8").replace(
    "name: healthcare-phi-pii", "name: compatibility-unknown-reader-field", 1,
)
text = text.replace("format_version: 1\n", "format_version: 1\nunknown_reader_field: true\n", 1)
dest.write_text(text, encoding="utf-8")
PY
install_case unknown-reader-field "$unknown_reader_field" fail
grep -q 'field unknown_reader_field not found' "$tmp/unknown-reader-field.err"

printf 'compatibility install: PASS (two pinned ceilings, optional v1 fields, same-version digest, unsupported format, unsupported minimum, unknown reader field)\n'
