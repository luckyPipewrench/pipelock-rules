#!/usr/bin/env bash
# Require a strictly newer bundle version whenever source rules change, and
# prevent a published bundle name/version identity from changing its bytes.
set -euo pipefail

# Compare stored release objects even when a local checkout has replacement refs.
export GIT_NO_REPLACE_OBJECTS=1

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

version_valid() {
	[[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

# Numeric equality so that leading-zero aliases of the same version
# (e.g. 2026.07.0 and 2026.7.0) are treated as one identity. A raw string
# compare would let a released bundle's bytes change under an aliased version
# string without tripping the immutability check.
version_eq() {
	local left="$1" right="$2" ly lm lp ry rm rp
	version_valid "$left" && version_valid "$right" || return 1
	IFS=. read -r ly lm lp <<<"$left"
	IFS=. read -r ry rm rp <<<"$right"
	compare_version_component "$ly" "$ry"
	(( component_cmp != 0 )) && return 1
	compare_version_component "$lm" "$rm"
	(( component_cmp != 0 )) && return 1
	compare_version_component "$lp" "$rp"
	(( component_cmp != 0 )) && return 1
	return 0
}

bundle_identity_from_content() {
	local content="$1" field values value line
	for field in name version; do
		values=()
		while IFS= read -r line; do
			if [[ "$line" == "$field: "* ]]; then
				values+=("${line#"$field: "}")
			fi
		done <<< "$content"
		if [[ ${#values[@]} -ne 1 || -z "${values[0]}" ]]; then
			return 1
		fi
		value="${values[0]}"
		if [[ "$value" == \"*\" ]]; then
			value="${value:1:${#value}-2}"
		elif [[ "$field" == version ]]; then
			return 1
		fi
		if [[ "$field" == name ]]; then
			[[ "$value" =~ ^[a-z0-9][a-z0-9-]*$ ]] || return 1
			bundle_name="$value"
		else
			version_valid "$value" || return 1
			bundle_version="$value"
		fi
	done
}

bundle_identity_from_file() {
	bundle_identity_from_content "$(<"$1")"
}

bundle_identity_from_git() {
	local content
	content="$(git show "$1" 2>/dev/null)" || return 1
	bundle_identity_from_content "$content"
}

# Filesystem reads follow links while Git hashes the stored link text. Require
# real bundle directories and regular files before comparing either view.
validate_worktree_layout() {
	local root entry links
	for root in rules published; do
		[[ -e "$root" || -L "$root" ]] || continue
		if [[ -L "$root" || ! -d "$root" ]]; then
			printf 'ERROR: %s must be a real directory\n' "$root" >&2
			return 1
		fi
		links="$(find "$root" -type l -print)" || return 1
		if [[ -n "$links" ]]; then
			printf 'ERROR: symbolic links are not supported under %s\n' "$root" >&2
			return 1
		fi
		for entry in "$root"/* "$root"/.[!.]* "$root"/..?*; do
			[[ -e "$entry" ]] || continue
			if [[ ! -d "$entry" ]]; then
				printf 'ERROR: %s must be a bundle directory\n' "$entry" >&2
				return 1
			fi
			if [[ "$root" == published && ! -f "$entry/bundle.yaml" ]]; then
				printf 'ERROR: %s/bundle.yaml must be a regular file\n' "$entry" >&2
				return 1
			fi
		done
	done
}

validate_history_layout() {
	local ref="$1" root entries mode type object name bundle_entries
	for root in rules published; do
		entries="$(git ls-tree "$ref" -- "$root")" || return 1
		[[ -n "$entries" ]] || continue
		read -r mode type object name <<< "$entries"
		[[ "$mode" == 040000 && "$type" == tree ]] || {
			printf 'ERROR: %s:%s is not a directory\n' "$ref" "$root" >&2; return 1;
		}
		entries="$(git ls-tree "$ref:$root")" || return 1
		while read -r mode type object name; do
			[[ -n "$mode" ]] || continue
			if [[ "$mode" != 040000 || "$type" != tree || ! "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
				printf 'ERROR: unsupported bundle entry in %s:%s\n' "$ref" "$root" >&2
				return 1
			fi
			[[ "$root" == published ]] || continue
			bundle_entries="$(git ls-tree "$ref:$root/$name" -- bundle.yaml)" || return 1
			read -r mode type object name <<< "$bundle_entries"
			if [[ "$type" != blob || ( "$mode" != 100644 && "$mode" != 100755 ) ]]; then
				printf 'ERROR: %s has a missing or non-regular published bundle.yaml\n' "$ref" >&2
				return 1
			fi
		done <<< "$entries"
	done
}

bundle_names() {
	local base_ref="$1" root="$2" current_names="" base_names="" base_entry
	if [[ -d "$root" ]]; then
		current_names="$(find "$root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n')" || return 1
	fi
	base_entry="$(git ls-tree --name-only "$base_ref" -- "$root")" || return 1
	if [[ -n "$base_entry" ]]; then
		base_names="$(git ls-tree -d --name-only "$base_ref:$root")" || return 1
	fi
	printf '%s\n%s\n' "$current_names" "$base_names" | sed '/^$/d' | sort -u
}

check_published_identity() {
	local base_ref="$1" bundle="$2" tags="$3"
	local current_file="published/$bundle/bundle.yaml"
	local base_file="$base_ref:$current_file" current_blob base_blob tag tag_path tag_blob
	local current_name current_version historical_name historical_version base_path tag_paths
	if [[ -L "$current_file" || ! -f "$current_file" ]]; then
		printf 'ERROR: published/%s/bundle.yaml was removed\n' "$bundle" >&2
		return 1
	fi
	if ! bundle_identity_from_file "$current_file"; then
		printf 'ERROR: published/%s/bundle.yaml must contain one valid name and quoted version\n' "$bundle" >&2
		return 1
	fi
	current_name="$bundle_name"
	current_version="$bundle_version"
	if ! version_valid "$current_version"; then
		printf 'ERROR: published/%s/bundle.yaml has an invalid version: %s\n' "$bundle" "$current_version" >&2
		return 1
	fi
	if [[ "$current_name" != "$bundle" ]]; then
		printf 'ERROR: published/%s/bundle.yaml name must match its directory (%s != %s)\n' \
			"$bundle" "$current_name" "$bundle" >&2
		return 1
	fi
	current_blob="$(git hash-object "$current_file")" || return 1
	base_path="$(git ls-tree --name-only "$base_ref" -- "$current_file")" || return 1
	if [[ -n "$base_path" ]]; then
		base_blob="$(git rev-parse "$base_file")" || return 1
		if ! bundle_identity_from_git "$base_file"; then
			printf 'ERROR: base published/%s/bundle.yaml has an invalid identity header\n' "$bundle" >&2
			return 1
		fi
		if [[ "$current_name" == "$bundle_name" ]] && version_eq "$current_version" "$bundle_version" && [[ "$current_blob" != "$base_blob" ]]; then
			printf 'ERROR: published bundle identity %s@%s changed bytes from %s\n' \
				"$current_name" "$current_version" "$base_ref" >&2
			return 1
		fi
	fi
	while IFS= read -r tag; do
		[[ -n "$tag" ]] || continue
		tag_paths="$(git ls-tree -r --name-only "$tag" -- published)" || return 1
		while IFS= read -r tag_path; do
			[[ "$tag_path" =~ ^published/[^/]+/bundle\.yaml$ ]] || continue
			if ! bundle_identity_from_git "$tag:$tag_path"; then
				printf 'ERROR: invalid published identity in release tag %s: %s\n' "$tag" "$tag_path" >&2
				return 1
			fi
			historical_name="$bundle_name"
			historical_version="$bundle_version"
			if [[ "$current_name" != "$historical_name" ]] || ! version_eq "$current_version" "$historical_version"; then
				continue
			fi
			tag_blob="$(git rev-parse "$tag:$tag_path")" || return 1
			if [[ "$current_blob" != "$tag_blob" ]]; then
				printf 'ERROR: published bundle identity %s@%s changed bytes from release tag %s\n' \
					"$current_name" "$current_version" "$tag" >&2
				return 1
			fi
		done <<< "$tag_paths"
	done <<< "$tags"
	return 0
}

# A non-shallow clone can still omit tags (for example, clone --no-tags).
# Compare tag objects, not just names, with the same origin used by CI.
# The caller owns Git configuration and must not mutate refs during this check.
# CI uses a fresh checkout; locally this checks uncommitted working-tree edits.
verify_release_tags() {
	local remote_tags remote_oid ref local_oid
	if ! remote_tags="$(GIT_TERMINAL_PROMPT=0 timeout --kill-after=5s 30s bash -c 'git "$@"' -- ls-remote --refs origin 'refs/tags/v*')"; then
		printf 'ERROR: cannot verify release tags against origin; check remote access and retry\n' >&2
		return 1
	fi
	while IFS=$'\t' read -r remote_oid ref; do
		[[ -n "$remote_oid" ]] || continue
		if ! local_oid="$(git rev-parse --verify "$ref" 2>/dev/null)" || [[ "$local_oid" != "$remote_oid" ]]; then
			printf 'ERROR: release tag %s is missing or differs from origin; fetch release tags and retry\n' "$ref" >&2
			return 1
		fi
	done <<< "$remote_tags"
}

main() {
	if [[ $# -ne 1 || -z "$1" ]]; then
		printf 'usage: %s BASE_GIT_REF\n' "$0" >&2
		return 2
	fi
	local base_ref="$1" status=0 bundle current_file current_version previous_version
	local source_bundles published_bundles tags shallow base_path diff_status tag
	if ! git cat-file -e "${base_ref}^{commit}" 2>/dev/null; then
		printf 'ERROR: base ref is unavailable: %s\n' "$base_ref" >&2
		return 1
	fi
	shallow="$(git rev-parse --is-shallow-repository)" || return 1
	if [[ "$shallow" != false ]]; then
		printf 'ERROR: identity checks require full history; fetch full history and release tags\n' >&2
		return 1
	fi
	verify_release_tags || return 1
	validate_worktree_layout || return 1
	validate_history_layout "$base_ref" || return 1
	source_bundles="$(bundle_names "$base_ref" rules)" || { printf 'ERROR: cannot enumerate source bundles\n' >&2; return 1; }
	published_bundles="$(bundle_names "$base_ref" published)" || { printf 'ERROR: cannot enumerate published bundles\n' >&2; return 1; }
	# Every v* tag is a release input, including releases off the base ancestry.
	tags="$(git tag --list 'v*')" || { printf 'ERROR: cannot enumerate release tags\n' >&2; return 1; }
	while IFS= read -r tag; do
		[[ -n "$tag" ]] || continue
		validate_history_layout "$tag" || return 1
	done <<< "$tags"
	while IFS= read -r bundle; do
		[[ -n "$bundle" ]] || continue
		if git diff --quiet "$base_ref" -- "rules/$bundle"; then
			continue
		else
			diff_status=$?
			[[ "$diff_status" == 1 ]] || return 1
		fi
		current_file="published/$bundle/bundle.yaml"
		if [[ ! -f "$current_file" ]]; then
			printf 'ERROR: changed rules/%s has no compiled bundle\n' "$bundle" >&2
			status=1
			continue
		fi
		if ! bundle_identity_from_file "$current_file"; then
			printf 'ERROR: changed rules/%s has an invalid compiled identity\n' "$bundle" >&2
			status=1
			continue
		fi
		current_version="$bundle_version"
		base_path="$(git ls-tree --name-only "$base_ref" -- "$current_file")" || return 1
		[[ -n "$base_path" ]] || continue
		if ! bundle_identity_from_git "$base_ref:$current_file"; then
			printf 'ERROR: base published/%s/bundle.yaml has an invalid identity header\n' "$bundle" >&2
			status=1
			continue
		fi
		previous_version="$bundle_version"
		if [[ -z "$current_version" ]] || ! version_gt "$current_version" "$previous_version"; then
			printf 'ERROR: rules/%s changed but bundle version did not increase (%s -> %s)\n' \
				"$bundle" "$previous_version" "${current_version:-missing}" >&2
			status=1
		fi
	done <<< "$source_bundles"
	while IFS= read -r bundle; do
		[[ -n "$bundle" ]] || continue
		if ! check_published_identity "$base_ref" "$bundle" "$tags"; then
			status=1
		fi
	done <<< "$published_bundles"
	return "$status"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	main "$@"
fi
