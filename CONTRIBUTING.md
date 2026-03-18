# Contributing

Rules are welcome via pull request. Each rule must meet the quality bar below before merge.

## Adding a New Rule

1. Create a YAML file in the appropriate directory:
   - `rules/dlp/` for credential/secret detection
   - `rules/injection/` for prompt injection detection
   - `rules/tool-poison/` for MCP tool description poisoning

2. Follow the naming convention:
   - DLP: `{provider}.yaml` or `{provider}-{credential-type}.yaml`
   - Injection: `{technique}.yaml`
   - Tool-poison: `{behavior}.yaml`

3. Add fixture files in `fixtures/{type}/`:
   - `{rule-id}-true-positive.txt` -- one test string per line that MUST match
   - `{rule-id}-false-positive.txt` -- one test string per line that MUST NOT match
   - Every non-empty line is tested (no comment syntax)

4. Run validation:
   ```bash
   make compile
   make test-fixtures
   ```

5. Submit a PR.

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
