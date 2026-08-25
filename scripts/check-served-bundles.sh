#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RULES_BASE_URL="${RULES_BASE_URL:-https://pipelab.org/rules}"
DRIFT_CHECK_FIXTURE_ROOT="${DRIFT_CHECK_FIXTURE_ROOT:-}"

temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT

read_version() {
	local file="$1"
	local label="$2"
	local versions=()
	mapfile -t versions < <(sed -n 's/^version: "\([^"]*\)"$/\1/p' "$file")
	if (( ${#versions[@]} != 1 )) || [[ -z "${versions[0]}" ]]; then
		printf 'served-copy drift: FAIL - %s must contain exactly one quoted version line\n' "$label" >&2
		return 1
	fi
	printf '%s\n' "${versions[0]}"
}

mapfile -d '' bundle_dirs < <(find published -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
if (( ${#bundle_dirs[@]} == 0 )); then
	printf 'served-copy drift: FAIL - no published bundles found\n' >&2
	exit 1
fi

status=0
for bundle_dir in "${bundle_dirs[@]}"; do
	bundle="$(basename "$bundle_dir")"
	repo_file="$bundle_dir/bundle.yaml"
	served_file="$temp_dir/${bundle}.yaml"
	url="${RULES_BASE_URL%/}/${bundle}/bundle.yaml"

	if [[ ! -f "$repo_file" ]]; then
		printf 'served-copy drift: FAIL - repository bundle is missing: %s\n' "$repo_file" >&2
		status=1
		continue
	fi
	if ! repo_version="$(read_version "$repo_file" "$repo_file")"; then
		status=1
		continue
	fi

	if [[ -n "$DRIFT_CHECK_FIXTURE_ROOT" ]]; then
		fixture_file="${DRIFT_CHECK_FIXTURE_ROOT%/}/${bundle}/bundle.yaml"
		if ! cp "$fixture_file" "$served_file" 2>/dev/null; then
			printf 'served-copy drift: FAIL - fixture bundle is unreadable: %s\n' "$fixture_file" >&2
			status=1
			continue
		fi
	elif ! curl --fail --silent --show-error --location --connect-timeout 10 --max-time 30 --output "$served_file" "$url"; then
		printf 'served-copy drift: FAIL - could not fetch %s\n' "$url" >&2
		status=1
		continue
	fi

	if ! served_version="$(read_version "$served_file" "$url")"; then
		status=1
		continue
	fi
	if [[ "$repo_version" != "$served_version" ]]; then
		printf 'served-copy drift: FAIL - %s version mismatch (repository: %s, served: %s)\n' "$bundle" "$repo_version" "$served_version" >&2
		status=1
		continue
	fi
	printf 'served-copy drift: OK - %s repository and served versions are %s\n' "$bundle" "$repo_version"
done

exit "$status"
