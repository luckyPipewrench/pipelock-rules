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

expect_eq() {
	version_eq "$1" "$2" || {
		printf 'expected %s == %s\n' "$1" "$2" >&2
		exit 1
	}
}

expect_not_eq() {
	if version_eq "$1" "$2"; then
		printf 'expected %s != %s\n' "$1" "$2" >&2
		exit 1
	fi
}

expect_eq 2026.07.0 2026.7.0
expect_eq 1.0.0 1.00.0
expect_eq 2026.07.0 2026.07.0
expect_not_eq 2026.07.0 2026.08.0
expect_not_eq 1.0.0 1.0.1
expect_not_eq bad 1.0.0

expect_gt 0.1.0 0.0.99
expect_gt 2026.7.10 2026.7.9
expect_gt 999999999999999999999.0.0 999999999999999999998.999.999
expect_gt 1.0002.0 1.1.999
expect_not_gt 1.2.3 1.2.3
expect_not_gt 1.2.2 1.2.3
expect_not_gt 1.2.3-rc1 1.2.2
expect_not_gt 1.2 1.1.9

fixture() {
	local directory base_version="1.0.0"
	if [[ $# -gt 0 ]]; then
		base_version="$1"
	fi
	directory="$(mktemp -d "${TMPDIR:-/tmp}/pipelock-rules-version-bumps.XXXXXX")"
	git -C "$directory" init -q
	git -C "$directory" config user.email rules-test@example.invalid
	git -C "$directory" config user.name 'Rules version test'
	git -C "$directory" remote add origin "$directory"
	mkdir -p "$directory/rules/demo/dlp" "$directory/published/demo"
	printf '%s\n' 'rule: original' >"$directory/rules/demo/dlp/example.yaml"
	printf '%s\n' \
		'format_version: 1' \
		'name: demo' \
		"version: \"$base_version\"" \
		'rules: []' >"$directory/published/demo/bundle.yaml"
	git -C "$directory" add rules published
	local tree commit
	tree="$(git -C "$directory" write-tree)"
	commit="$(GIT_EDITOR=true git -C "$directory" commit-tree "$tree" -m initial)"
	git -C "$directory" update-ref HEAD "$commit"
	git -C "$directory" update-ref refs/tags/v0.1.0 "$commit"
	printf '%s\n' "$directory"
}

expect_gate() {
	local expected="$1" directory="$2" base_ref="${3:-HEAD}" output
	if output="$(cd "$directory" && "$root/scripts/check-version-bumps.sh" "$base_ref" 2>&1)"; then
		if [[ "$expected" != pass ]]; then
			printf 'expected gate failure, got pass: %s\n' "$directory" >&2
			exit 1
		fi
	elif [[ "$expected" != fail ]]; then
		printf 'expected gate pass, got failure: %s\n%s\n' "$directory" "$output" >&2
		exit 1
	fi
}

directory="$(fixture)"
expect_gate pass "$directory"

directory="$(fixture)"
printf '%s\n' 'rule: changed' >"$directory/rules/demo/dlp/example.yaml"
expect_gate fail "$directory"

directory="$(fixture)"
sed -i 's/version: "1.0.0"/version: "1.0.1"/' "$directory/published/demo/bundle.yaml"
printf '%s\n' 'rule: changed' >"$directory/rules/demo/dlp/example.yaml"
expect_gate pass "$directory"

directory="$(fixture)"
mv "$directory/rules/demo" "$directory/removed-demo"
expect_gate fail "$directory"

directory="$(fixture)"
sed -i 's/rules: \[\]/rules: [changed]/' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

directory="$(fixture)"
sed -i 's/version: "1.0.0"/version: "1.0.1"/' "$directory/published/demo/bundle.yaml"
sed -i 's/rules: \[\]/rules: [changed]/' "$directory/published/demo/bundle.yaml"
expect_gate pass "$directory"

directory="$(fixture)"
sed -i 's/version: "1.0.0"/version: "0.9.0"/' "$directory/published/demo/bundle.yaml"
sed -i 's/rules: \[\]/rules: [changed]/' "$directory/published/demo/bundle.yaml"
git -C "$directory" add published/demo/bundle.yaml
tree="$(git -C "$directory" write-tree)"
commit="$(GIT_EDITOR=true git -C "$directory" commit-tree "$tree" -p HEAD -m prior-version)"
git -C "$directory" update-ref HEAD "$commit"
git -C "$directory" update-ref refs/tags/v0.0.9 "$commit"
sed -i 's/version: "0.9.0"/version: "1.0.0"/' "$directory/published/demo/bundle.yaml"
sed -i 's/rules: \[changed\]/rules: [different]/' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

directory="$(fixture)"
sed -i 's/version: "1.0.0"/version: bad/' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

directory="$(fixture)"
sed -i '/^version:/d' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

directory="$(fixture '')"
sed -i 's/version: ""/version: "1.0.1"/' "$directory/published/demo/bundle.yaml"
printf '%s\n' 'rule: changed' >"$directory/rules/demo/dlp/example.yaml"
expect_gate fail "$directory"

expect_gate fail "$directory" missing-base

# A leading-zero alias of the released version must not let the published bytes
# change: 2026.07.0 and 2026.7.0 are the same identity. rules/ is untouched, so
# only the immutability loop can catch this.
directory="$(fixture 2026.07.0)"
sed -i 's/version: "2026.07.0"/version: "2026.7.0"/' "$directory/published/demo/bundle.yaml"
sed -i 's/rules: \[\]/rules: [aliased]/' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

# A genuinely newer version with a leading-zero component is still allowed to
# change bytes; the alias defense must not over-block a real bump.
directory="$(fixture 2026.07.0)"
sed -i 's/version: "2026.07.0"/version: "2026.08.0"/' "$directory/published/demo/bundle.yaml"
sed -i 's/rules: \[\]/rules: [bumped]/' "$directory/published/demo/bundle.yaml"
expect_gate pass "$directory"

# A release outside the base ancestry still reserves its bundle identity.
directory="$(fixture)"
sed -i 's/version: "1.0.0"/version: "2.0.0"/' "$directory/published/demo/bundle.yaml"
git -C "$directory" add published/demo/bundle.yaml
tree="$(git -C "$directory" write-tree)"
commit="$(git -C "$directory" commit-tree "$tree" -m off-branch-release)"
git -C "$directory" update-ref refs/tags/v2.0.0 "$commit"
sed -i 's/rules: \[\]/rules: [changed]/' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

directory="$(fixture)"
mv "$directory/published/demo" "$directory/retained-demo"
expect_gate fail "$directory"

# Full history without release tags must fail before it can miss an off-branch
# identity. Fetching the tags repairs the input but still rejects changed bytes.
origin="$(fixture)"
sed -i 's/version: "1.0.0"/version: "2.0.0"/' "$origin/published/demo/bundle.yaml"
git -C "$origin" add published/demo/bundle.yaml
tree="$(git -C "$origin" write-tree)"
commit="$(git -C "$origin" commit-tree "$tree" -m off-branch-release)"
git -C "$origin" update-ref refs/tags/v2.0.0 "$commit"
directory="$(mktemp -d "${TMPDIR:-/tmp}/pipelock-rules-version-bumps.XXXXXX")"
git clone --quiet --no-tags "$origin" "$directory"
[[ "$(git -C "$directory" rev-parse --is-shallow-repository)" == false ]]
expect_gate fail "$directory"
git -C "$directory" fetch --quiet --tags origin
expect_gate pass "$directory"
sed -i 's/version: "1.0.0"/version: "2.0.0"/; s/rules: \[\]/rules: [changed]/' "$directory/published/demo/bundle.yaml"
expect_gate fail "$directory"

# A same-named local tag pointing at different bytes is not complete input.
git -C "$directory" show HEAD:published/demo/bundle.yaml >"$directory/published/demo/bundle.yaml"
expect_gate pass "$directory"
git -C "$directory" update-ref refs/tags/v2.0.0 HEAD
expect_gate fail "$directory"

# Offline/unavailable origin is an error, not evidence of no releases.
git -C "$directory" update-ref refs/tags/v2.0.0 "$commit"
expect_gate pass "$directory"
git -C "$directory" remote set-url origin "$directory/missing-origin"
expect_gate fail "$directory"

# Failed history or filesystem queries must never become empty successful scans.
directory="$(fixture)"
for GATE_FAIL_SUBCOMMAND in tag ls-tree hash-object diff show rev-parse ls-remote; do
	export GATE_FAIL_SUBCOMMAND
	git() {
		[[ "$1" != "$GATE_FAIL_SUBCOMMAND" ]] || return 93
		command git "$@"
	}
	export -f git
	expect_gate fail "$directory"
	unset -f git
done
unset GATE_FAIL_SUBCOMMAND
find() { return 93; }
export -f find
expect_gate fail "$directory"
unset -f find

# Exercise the real compiler's bare-name header, not only synthetic fixtures.
for bundle in pipelock-community healthcare-phi-pii; do
	bundle_identity_from_file "$root/published/$bundle/bundle.yaml"
	[[ "$bundle_name" == "$bundle" ]]
done

printf 'version comparison and immutable identity gate tests passed\n'
