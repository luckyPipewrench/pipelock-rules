#!/usr/bin/env bash
# Require a strictly newer bundle version whenever source rules change.
set -euo pipefail

component_cmp=0

compare_version_component() {
	local left="$1" right="$2"
	local LC_ALL=C
	while [[ ${#left} -gt 1 && "$left" == 0* ]]; do left="${left#0}"; done
	while [[ ${#right} -gt 1 && "$right" == 0* ]]; do right="${right#0}"; done
	if (( ${#left} > ${#right} )); then
		component_cmp=1
	elif (( ${#left} < ${#right} )); then
		component_cmp=-1
	elif [[ "$left" > "$right" ]]; then
		component_cmp=1
	elif [[ "$left" < "$right" ]]; then
		component_cmp=-1
	else
		component_cmp=0
	fi
}

version_gt() {
	local newer="$1" older="$2"
	local ny nm np oy om op
	[[ "$newer" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$older" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
	IFS=. read -r ny nm np <<<"$newer"
	IFS=. read -r oy om op <<<"$older"
	compare_version_component "$ny" "$oy"
	(( component_cmp > 0 )) && return 0
	(( component_cmp < 0 )) && return 1
	compare_version_component "$nm" "$om"
	(( component_cmp > 0 )) && return 0
	(( component_cmp < 0 )) && return 1
	compare_version_component "$np" "$op"
	(( component_cmp > 0 ))
}

main() {
	if [[ $# -ne 1 || -z "$1" ]]; then
		printf 'usage: %s BASE_GIT_REF\n' "$0" >&2
		return 2
	fi
	local base_ref="$1" status=0 bundle_dir bundle current_file current_version previous_version
	if ! git cat-file -e "${base_ref}^{commit}" 2>/dev/null; then
		printf 'ERROR: base ref is unavailable: %s\n' "$base_ref" >&2
		return 1
	fi
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
	return "$status"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	main "$@"
fi
