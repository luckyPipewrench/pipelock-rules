# pipelock-rules

Official community rule bundles for [Pipelock](https://github.com/luckyPipewrench/pipelock), the open-source agent firewall.

Community rules extend pipelock's built-in detection patterns with additional DLP, injection, and tool-poison rules that ship on a faster cadence than the core binary.

## What's Included

The `pipelock-community` bundle ships **28 detection rules**:

| Category | Stable | Experimental | Examples |
|----------|--------|--------------|----------|
| **DLP** | 7 | 4 | Perplexity, 1Password, Vercel, Buildkite, Pulumi, Doppler, Shopify, Modal |
| **Injection** | 6 | 4 | HTML comment hiding, system tag override, delimiter breakout, exfil imperative, multilingual (ES/FR/DE/ZH) |
| **Tool-Poison** | 5 | 2 | Concealment, precall harvest, cross-tool replacement, exfil URL, prompt harvest, binary mimicry |

These rules are **additive** -- they extend pipelock's built-in DLP and injection patterns. No overlap with built-in rules.

## Installing

```bash
pipelock rules install pipelock-community
```

Requires pipelock v1.5.0+ (release binaries with embedded keyring). The `min_pipelock` field in the bundle will be bumped to `1.5.0` at publication time. See the [pipelock docs](https://github.com/luckyPipewrench/pipelock/blob/main/docs/rules.md) for configuration options.

## Rule Status

- **Stable** (18 rules): Validated regexes with true-positive and false-positive fixtures. Primary source citations for every pattern.
- **Experimental** (10 rules): True-positive fixtures only. May have higher false positive rates. Disabled by default unless `include_experimental: true` is set in your config.

## Development

```bash
# Compile individual rule files into a single bundle
make compile

# Validate the bundle with pipelock
make validate

# Run fixture tests (every regex against its true/false positive fixtures)
make test-fixtures
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a new rule.

## License

Apache 2.0 -- see [LICENSE](LICENSE).
