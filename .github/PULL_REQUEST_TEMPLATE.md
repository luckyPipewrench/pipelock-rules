## Summary

Brief description of what this PR adds or changes.

## Rules Added/Changed

| Rule ID | Type | Status | Description |
|---------|------|--------|-------------|
| | | | |

## Bundle

- [ ] `pipelock-community`
- [ ] `healthcare-phi-pii`
- [ ] Other:

## Testing

- [ ] `BUNDLE_NAME=<bundle-name> make compile` succeeds
- [ ] `BUNDLE_NAME=<bundle-name> make test-fixtures` passes (all true/false positive fixtures)
- [ ] `BUNDLE_NAME=<bundle-name> make validate` passes (pipelock accepts the bundle)

## Checklist

- [ ] RE2-compatible regex (no lookahead/lookbehind)
- [ ] True-positive fixture added
- [ ] False-positive fixture added (stable rules)
- [ ] Primary source citation included (stable rules)
- [ ] Rule ID follows naming convention (`{type}-{provider/technique}`)
