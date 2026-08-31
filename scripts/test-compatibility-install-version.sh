#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
parser="$root/scripts/test-compatibility-install.sh"

accept() {
	local input="$1" expected="$2" actual
	actual="$($parser --parse-version "$input")"
	[[ "$actual" == "$expected" ]] || {
		printf 'version parser: FAIL - %q produced %q, expected %q\n' "$input" "$actual" "$expected" >&2
		return 1
	}
}

reject() {
	local input="$1"
	if "$parser" --parse-version "$input" >/dev/null 2>&1; then
		printf 'version parser: FAIL - accepted malformed output %q\n' "$input" >&2
		return 1
	fi
}

accept 'pipelock version 3.5.0' '3.5.0'
accept 'pipelock version v3.5.0' '3.5.0'
accept 'pipelock version 3.5.0-rc1' '3.5.0'
accept 'pipelock version v3.5.0-preview.1' '3.5.0'
accept 'pipelock version v3.5.0-alpha-1.0' '3.5.0'

reject 'pipelock version 3.5'
reject 'pipelock version vv3.5.0'
reject 'pipelock version 03.5.0'
reject 'pipelock version v3.5.0-01'
reject 'pipelock version v3.5.0-preview.01'
reject 'pipelock version v3.5.0-rc.'
reject 'pipelock version v3.5.0+build.1'
reject 'pipelock version v3.5.0-rc1+build.1'
reject 'pipelock version v3.5.0 extra'
reject 'pipelock version devel'

printf 'version parser: PASS (release and prerelease cores accepted; malformed and build metadata rejected)\n'
