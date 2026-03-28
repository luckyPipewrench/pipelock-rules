# Security Policy

## Reporting a Vulnerability

If a community rule regex could be exploited for **ReDoS** (regular expression denial of service) or other abuse, report it through the [Pipelock Security Advisory process](https://github.com/luckyPipewrench/pipelock/security/advisories/new).

**Do NOT open a public GitHub issue for ReDoS or exploitable regex patterns.**

For false negatives (a rule fails to detect a real secret or injection pattern), open a regular issue using the "Rule Evasion / ReDoS" template.

Include:
- Rule ID affected
- Description of the bypass or exploit
- Test string demonstrating the issue
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix and disclosure:** Coordinated with reporter, typically within 30 days

## Scope

The following are in scope for security advisories:

- ReDoS patterns that cause catastrophic backtracking
- Regex patterns that match sensitive data they shouldn't (false positives causing information disclosure)
- Signature verification bypass in bundle signing
- Supply chain attacks via rule bundle distribution

The following are regular issues (not security advisories):

- False negatives (rule misses a real threat)
- False positives (rule matches benign content)
- Rule quality improvements

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2026.x  | Yes       |
