# AGENTS.md: pipelock-rules Development Guide

Community detection rule bundles for [Pipelock](https://github.com/luckyPipewrench/pipelock).

## Quick Reference

| Item | Value |
|------|-------|
| Language | YAML (rule definitions) + Bash (build scripts) |
| CI | GitHub Actions: validate, test-fixtures, yaml-lint |
| Bundle format | `format_version: 1` YAML with Ed25519 signatures |
| Regex engine | RE2 (no lookahead/lookbehind, no backreferences) |

## Build, Test, Validate

```bash
make compile         # Merge default bundle files into published/pipelock-community/bundle.yaml
make validate        # Compile + install into pipelock (validates schema and regexes)
make test-fixtures   # Run every regex against its true/false positive fixtures
make diagrams        # Re-render the README assets from the compiled bundles
make check-diagrams  # Fail if an asset, a painted count, or a README claim has drifted
make preflight       # check-diagrams, then validate and test-fixtures for every bundle
```

Set `BUNDLE_NAME=<bundle-name>` to work on a non-default bundle, for example `BUNDLE_NAME=healthcare-phi-pii make test-fixtures`.

`make validate` requires `pipelock` on PATH. Install with `go install github.com/luckyPipewrench/pipelock/cmd/pipelock@latest`.

Any change to rule counts, bundle versions, the Pipelock version CI installs, the pinned signing key, or a CI job name changes what the README diagrams claim. Run `make diagrams` and commit the result; `make check-diagrams` fails otherwise. The generator reads only `python3` from the standard library, so it needs no extra tooling.

## Repository Layout

```text
rules/
  pipelock-community/
    dlp/            One YAML file per DLP pattern
    injection/      One YAML file per injection pattern
    tool-poison/    One YAML file per tool-poison pattern
  healthcare-phi-pii/
    dlp/
fixtures/
  pipelock-community/
    dlp/            True/false positive test strings per rule
    injection/
    tool-poison/
  healthcare-phi-pii/
    dlp/
published/
  pipelock-community/
    bundle.yaml     Compiled bundle (all rules merged)
    bundle.yaml.sig Ed25519 signature (production-signed)
  healthcare-phi-pii/
    bundle.yaml
scripts/
  compile.sh        Merges rule files into bundle.yaml
  test-fixtures.sh  Validates every regex against fixtures
```

## Adding a Rule

1. Create `rules/{bundle}/{type}/{name}.yaml` following the schema in CONTRIBUTING.md
2. Add `fixtures/{bundle}/{type}/{rule-id}-true-positive.txt` (one match per line)
3. Add `fixtures/{bundle}/{type}/{rule-id}-false-positive.txt` (stable rules only)
4. Run `BUNDLE_NAME={bundle} make compile && BUNDLE_NAME={bundle} make test-fixtures`
5. Run `BUNDLE_NAME={bundle} make validate`, which installs the compiled bundle with Pipelock and checks the schema and every regex. Compilation and fixture tests alone do not cover that.
6. Submit a PR

## Rule YAML Schema

Every rule requires these fields:

```yaml
- id: dlp-example-api-key        # Unique, prefixed with rule type
  type: dlp                       # dlp, injection, or tool-poison
  status: stable                  # stable or experimental
  name: "Example API Key"
  description: "Detects Example.com API keys"
  severity: critical              # critical, high, medium, low
  confidence: high                # high, medium, low
  references:
    - "https://example.com/docs"
  tags:
    - "provider:example"
  pattern:
    regex: 'ex_[A-Za-z0-9]{32,}' # RE2-compatible
```

`scan_field` is conditional, not required. It applies to tool-poison rules only, where it selects `name` or `description`. DLP rules omit it entirely; see `rules/pipelock-community/dlp/vercel-project.yaml` for a rule that carries every required field and no `scan_field`.

```yaml
  pattern:
    regex: 'ex_[A-Za-z0-9]{32,}'
    scan_field: description       # tool-poison rules only
```

## Regex Guidelines

- RE2 syntax only (pipelock uses Go's `regexp` package)
- Prefer specific prefixes over broad character classes
- Set minimum match lengths to reduce false positives
- Case-insensitive matching (`(?i)`) is applied automatically by pipelock
- Test against real-world text, not just isolated tokens

## Fixture Format

One test string per line. Every non-empty line is tested (no comment syntax).

- `{rule-id}-true-positive.txt`: strings that MUST match the regex
- `{rule-id}-false-positive.txt`: strings that MUST NOT match

## Signing

Published official bundles are signed with the Pipelock official rules key. Only maintainers with keystore access can sign. CI verifies that committed `published/<bundle>/bundle.yaml` files are current with `rules/<bundle>/` and that each `bundle.yaml.sig` verifies against `.github/rules-official/pipelock-official.pub`.

## Style

- Rule IDs: `{type}-{provider}` or `{type}-{technique}` (lowercase, hyphens)
- One rule per YAML file
- Keep regexes readable: prefer `[A-Za-z0-9]` over `\w` for clarity
- Include primary source citations for every stable rule
