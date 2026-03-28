# CLAUDE.md: pipelock-rules Development Guide

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
make compile         # Merge rule files into published/pipelock-community/bundle.yaml
make validate        # Compile + install into pipelock (validates schema and regexes)
make test-fixtures   # Run every regex against its true/false positive fixtures
```

`make validate` requires `pipelock` on PATH. Install with `go install github.com/luckyPipewrench/pipelock/cmd/pipelock@latest`.

## Repository Layout

```
rules/
  dlp/              One YAML file per DLP pattern
  injection/        One YAML file per injection pattern
  tool-poison/      One YAML file per tool-poison pattern
fixtures/
  dlp/              True/false positive test strings per rule
  injection/
  tool-poison/
published/
  pipelock-community/
    bundle.yaml     Compiled bundle (all rules merged)
    bundle.yaml.sig Ed25519 signature (production-signed)
scripts/
  compile.sh        Merges rule files into bundle.yaml
  test-fixtures.sh  Validates every regex against fixtures
```

## Adding a Rule

1. Create `rules/{type}/{name}.yaml` following the schema in CONTRIBUTING.md
2. Add `fixtures/{type}/{rule-id}-true-positive.txt` (one match per line)
3. Add `fixtures/{type}/{rule-id}-false-positive.txt` (stable rules only)
4. Run `make compile && make test-fixtures`
5. Submit a PR

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
    scan_field: description       # tool-poison only: name or description
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

The published bundle is signed with the pipelock production key. Only maintainers with keystore access can sign. CI validates the unsigned bundle; signing happens at release time.

## Style

- Rule IDs: `{type}-{provider}` or `{type}-{technique}` (lowercase, hyphens)
- One rule per YAML file
- Keep regexes readable: prefer `[A-Za-z0-9]` over `\w` for clarity
- Include primary source citations for every stable rule
