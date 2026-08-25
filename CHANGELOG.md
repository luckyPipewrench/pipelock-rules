# Changelog

Bundle versions are independent. Repository validation changes don't alter bundle content, so they don't require a bundle version bump.

## pipelock-community

### 2026.07.0 (2026-07-15)

- Expanded explicit HTTP exfiltration detection to match transfers sent "over" HTTP or HTTPS.
- Added accented French spellings for override instructions.
- Tightened hidden HTML attribute matching so class names such as `hidden-label` don't trigger the rule, while quoted and unquoted `aria-hidden=true` remain covered.
- Required suspicious content inside fake privileged XML tags, which avoids matching ordinary `admin_message` and `internal_prompt` elements.
- Accepted straight and curly apostrophes in tool-poison concealment instructions.
- Expanded pre-call data-harvest detection to cover more call and retrieval wording.
- Replaced the shell fixture parser with a Go fixture runner that compiles patterns with Go's RE2 engine, enforces fixture coverage, and requires a bundle version bump when rules or fixtures change.

### 2026.03.1 (2026-03-16)

- Introduced the community bundle with 28 rules: 18 stable rules with positive and negative fixtures, plus 10 experimental rules with positive fixtures.
- Added DLP, prompt-injection, and MCP tool-poison detections.

## healthcare-phi-pii

### 2026.05.1 (2026-05-14)

- Introduced the healthcare bundle with 28 DLP rules for regex-detectable HIPAA Safe Harbor identifiers, financial PII, and clinical laboratory identifiers.
- Added independent compilation, fixtures, versioning, and signing for the second published bundle.

## Repository validation

### 2026-08-23

- The parser-integrity fixture gate rejects duplicate rule IDs and malformed rule-start lines before fixture evaluation ([#45](https://github.com/luckyPipewrench/pipelock-rules/pull/45)).

### 2026-08-20

- The compatibility gate installs each bundle with the current Pipelock release and with the bundle's declared minimum Pipelock version, so an unsupported floor fails in CI ([#44](https://github.com/luckyPipewrench/pipelock-rules/pull/44)).
