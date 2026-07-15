#!/usr/bin/env bash
# Require a strictly newer bundle version whenever source rules change.
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
	printf 'usage: %s BASE_GIT_REF\n' "$0" >&2
	exit 2
fi

base_ref="$1"
if ! git cat-file -e "${base_ref}^{commit}" 2>/dev/null; then
	printf 'ERROR: base ref is unavailable: %s\n' "$base_ref" >&2
	exit 1
fi

version_gt() {
	local newer="$1" older="$2"
	local ny nm np oy om op
	IFS=. read -r ny nm np <<<"$newer"
	IFS=. read -r oy om op <<<"$older"
	[[ "$newer" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]+$ && "$older" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]+$ ]] || return 1
	((10#$ny > 10#$oy)) && return 0
	((10#$ny < 10#$oy)) && return 1
	((10#$nm > 10#$om)) && return 0
	((10#$nm < 10#$om)) && return 1
	((10#$np > 10#$op))
}

status=0
while IFS= read -r bundle_dir; do
	bundle="$(basename "$bundle_dir")"
	if git diff --quiet "$base_ref" -- "$bundle_dir"; then
		continue
	fi
	current_file="published/$bundle/bundle.yaml"
	if [[ ! -f "$current_file" ]]; then
		printf 'ERROR: changed rules/%s has no compiled bundle\n' "$bundle" >&2
		status=1
		continue
	fi
	current_version="$(sed -n 's/^version: "\([^"]*\)"$/\1/p' "$current_file")"
	previous_version="$(git show "$base_ref:$current_file" 2>/dev/null | sed -n 's/^version: "\([^"]*\)"$/\1/p' || true)"
	if [[ -z "$previous_version" ]]; then
		continue
	fi
	if [[ -z "$current_version" ]] || ! version_gt "$current_version" "$previous_version"; then
		printf 'ERROR: rules/%s changed but bundle version did not increase (%s -> %s)\n' \
			"$bundle" "$previous_version" "${current_version:-missing}" >&2
		status=1
	fi
done < <(find rules -mindepth 1 -maxdepth 1 -type d | sort)

exit "$status"
