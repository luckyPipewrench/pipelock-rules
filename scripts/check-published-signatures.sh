#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OFFICIAL_PUBKEY="${OFFICIAL_PUBKEY:-.github/rules-official/pipelock-official.pub}"
if [[ ! -r "$OFFICIAL_PUBKEY" ]]; then
	printf 'ERROR: official public key is missing or unreadable: %s\n' "$OFFICIAL_PUBKEY" >&2
	exit 1
fi
EXPECTED_OFFICIAL_PUBKEY_SHA256="${EXPECTED_OFFICIAL_PUBKEY_SHA256:-}"
if [[ -n "$EXPECTED_OFFICIAL_PUBKEY_SHA256" ]]; then
	read -r actual_pubkey_sha256 _ < <(sha256sum "$OFFICIAL_PUBKEY")
	if [[ "$actual_pubkey_sha256" != "$EXPECTED_OFFICIAL_PUBKEY_SHA256" ]]; then
		printf 'ERROR: official public key digest mismatch for %s\n' "$OFFICIAL_PUBKEY" >&2
		exit 1
	fi
fi

KEYSTORE_DIR="$(mktemp -d)"
trap 'rm -rf "$KEYSTORE_DIR"' EXIT

mkdir -p "$KEYSTORE_DIR/agents/pipelock-official"
cp "$OFFICIAL_PUBKEY" "$KEYSTORE_DIR/agents/pipelock-official/id_ed25519.pub"

status=0

while IFS= read -r bundle_dir; do
	bundle="$(basename "$bundle_dir")"
	bundle_file="published/$bundle/bundle.yaml"
	sig_file="$bundle_file.sig"

	if [[ ! -f "$bundle_file" ]]; then
		printf 'ERROR: %s is missing\n' "$bundle_file" >&2
		status=1
		continue
	fi
	if [[ ! -f "$sig_file" ]]; then
		printf 'ERROR: %s is missing; official bundles must be signed before merge\n' "$sig_file" >&2
		status=1
		continue
	fi

	original_bundle="$KEYSTORE_DIR/$bundle.bundle.yaml"
	cp "$bundle_file" "$original_bundle"
	if ! BUNDLE_NAME="$bundle" make compile >/dev/null; then
		cp "$original_bundle" "$bundle_file"
		printf 'ERROR: failed to compile rules/%s\n' "$bundle" >&2
		status=1
		continue
	fi
	if ! cmp -s "$bundle_file" "$original_bundle"; then
		printf 'ERROR: %s is not up to date with rules/%s; run BUNDLE_NAME=%s make compile\n' "$bundle_file" "$bundle" "$bundle" >&2
		diff -u --label "$bundle_file (before compile)" --label "$bundle_file (after compile)" "$original_bundle" "$bundle_file" >&2 || true
		cp "$original_bundle" "$bundle_file"
		status=1
	fi

	if ! pipelock verify "$bundle_file" --keystore "$KEYSTORE_DIR" --agent pipelock-official >/dev/null; then
		printf 'ERROR: %s does not verify against %s; sign it with the official rules key before merge\n' "$sig_file" "$OFFICIAL_PUBKEY" >&2
		status=1
	fi
done < <(find rules -mindepth 1 -maxdepth 1 -type d | sort)

exit "$status"
