#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=check-version-bumps.sh
source "$root/scripts/check-version-bumps.sh"

expect_gt() {
	version_gt "$1" "$2" || {
		printf 'expected %s > %s\n' "$1" "$2" >&2
		exit 1
	}
}

expect_not_gt() {
	if version_gt "$1" "$2"; then
		printf 'expected %s not > %s\n' "$1" "$2" >&2
		exit 1
	fi
}

expect_gt 0.1.0 0.0.99
expect_gt 2026.7.10 2026.7.9
expect_gt 999999999999999999999.0.0 999999999999999999998.999.999
expect_gt 1.0002.0 1.1.999
expect_not_gt 1.2.3 1.2.3
expect_not_gt 1.2.2 1.2.3
expect_not_gt 1.2.3-rc1 1.2.2
expect_not_gt 1.2 1.1.9

printf 'version comparison tests passed\n'
