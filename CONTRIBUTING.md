# Contributing

Rules are welcome via pull request. Each rule must meet the quality bar below before merge.

## Prerequisites

- [Pipelock](https://github.com/luckyPipewrench/pipelock) v1.4.0+ (for `make validate`)
- Bash (for `make compile` and `make test-fixtures`)
- A regex that works with Go's RE2 engine (no lookahead/lookbehind, no backreferences)

## Contributing Rules to an Existing Bundle

1. Create a YAML file in the appropriate directory:
   - `rules/<bundle-name>/dlp/` for credential, secret, PHI, or PII detection
   - `rules/<bundle-name>/injection/` for prompt injection detection
   - `rules/<bundle-name>/tool-poison/` for MCP tool description poisoning

2. Follow the naming convention:
   - DLP: `{provider}.yaml` or `{provider}-{credential-type}.yaml`
   - Injection: `{technique}.yaml`
   - Tool-poison: `{behavior}.yaml`

3. Add fixture files in `fixtures/<bundle-name>/{type}/`:
   - `{rule-id}-true-positive.txt`: one test string per line that MUST match
   - `{rule-id}-false-positive.txt`: one test string per line that MUST NOT match
   - Every non-empty line is tested (no comment syntax)

4. Run validation:
   ```bash
   BUNDLE_NAME=<bundle-name> make compile
   BUNDLE_NAME=<bundle-name> make test-fixtures
   BUNDLE_NAME=<bundle-name> make validate
   ```

5. Re-render the README diagrams, because one of them counts the rules you just changed:
   ```bash
   make diagrams
   ```
   Commit the updated files under `assets/`. CI runs `make check-diagrams`, which fails
   while a committed diagram still shows the old counts.

6. Submit a PR.

`pipelock-community` is the default bundle, so existing commands such as `make compile` still target it.

## Contributing a New Bundle

Open an issue first so naming, scope, signing-key alignment, and maintenance ownership can be confirmed before code is added. New bundles must use `format_version: 2`, which requires Pipelock v2.2.0 or later. The existing `pipelock-community` and `healthcare-phi-pii` bundles remain on `format_version: 1` until their bundle content, signatures, served copies, and compatibility checks can migrate together.

Use this header for a new bundle:

```yaml
format_version: 2
name: example-community-rules
version: "2026.08.0"
author: example-security
description: "Detection rules for Example Security"
homepage: "https://example.com/security/rules"
min_pipelock: "2.2.0"
license: "Apache-2.0"
tier: community
monotonic_version: 1
published_at: "2026-08-25T00:00:00Z"
expires_at: "2027-08-25T00:00:00Z"
required_features:
  - dlp

rules:
  # Rule entries follow the format below.
```

`tier` declares the bundle's trust tier. `required_features` lists the Pipelock engine features that every rule in the bundle needs. Increase `monotonic_version` for each published bundle version so Pipelock can reject rollbacks. Write `published_at` and `expires_at` as UTC RFC 3339 timestamps.

New bundles should use this layout:

```text
rules/<bundle-name>/<type>/<rule-file>.yaml
fixtures/<bundle-name>/<type>/<rule-id>-true-positive.txt
fixtures/<bundle-name>/<type>/<rule-id>-false-positive.txt
published/<bundle-name>/bundle.yaml
```

## Rule YAML Format

```yaml
  - id: dlp-example-api-key           # unique ID, prefixed with rule type
    type: dlp                          # dlp, injection, or tool-poison
    status: stable                     # stable or experimental
    name: "Example API Key"            # human-readable name
    description: "Detects Example.com API keys"
    severity: critical                 # critical, high, medium, low
    confidence: high                   # high, medium, low
    references:                        # primary sources (vendor docs, research)
      - "https://example.com/docs/api-keys"
    tags:                              # categorization
      - "provider:example"
      - "owasp-llm:LLM06"
    pattern:
      regex: 'ex_[A-Za-z0-9]{32,}'    # RE2-compatible regex
      scan_field: description          # tool-poison only: name or description
```

## Quality Bar

### Stable rules

- At least one true-positive fixture string that matches the regex
- At least one false-positive fixture string that does NOT match
- A primary source citation (vendor docs, research paper, or security advisory)
- RE2-compatible regex (validated by `make validate`)
- Minimum match length of 8+ characters to reduce false positives

### Experimental rules

- At least one true-positive fixture
- RE2-compatible regex
- A brief note in the description explaining why it's experimental

## Regex Guidelines

- Use RE2 syntax (no lookahead/lookbehind, no backreferences)
- Prefer specific prefixes over broad character classes (`pplx-[A-Za-z0-9]{16,}` is better than `[a-z]{4}-[A-Za-z0-9]+`)
- Set minimum match lengths to reduce false positives
- Test against real-world text, not just isolated tokens
- Case-insensitive matching is applied automatically by pipelock (`(?i)` prefix)

## Rule Types

| Type | `type` value | What it detects | `scan_field` |
|------|-------------|-----------------|-------------|
| DLP | `dlp` | Credentials and secrets in outbound traffic | N/A |
| Injection | `injection` | Prompt injection in fetched content and tool responses | N/A |
| Tool-poison | `tool-poison` | Hidden instructions in MCP tool descriptions | `name` or `description` |

## Pull Requests

- PRs are squash-merged into `main`
- CI must pass: bundle validation, fixture tests, YAML lint
- Official published bundles must be current and signed before merge. Contributors
  do not need signing-key access; maintainers add or refresh `bundle.yaml.sig`
  during review when a PR changes `published/<bundle>/bundle.yaml`.
- All review threads must be resolved before merge

## Development Workflow

1. Fork the repo and create a branch (`feat/new-rule-name` or `fix/rule-id`)
2. Add your rule and fixtures
3. Run `BUNDLE_NAME=<bundle-name> make compile && BUNDLE_NAME=<bundle-name> make test-fixtures && BUNDLE_NAME=<bundle-name> make validate`
4. Push and open a PR

## Contributor License Agreement

By submitting a pull request, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE), the same license as this project.

## Security

If a regex could be exploited for ReDoS or other abuse, use the [security advisory process](https://github.com/luckyPipewrench/pipelock/security/advisories). See [SECURITY.md](SECURITY.md) for details.
