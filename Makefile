BUNDLE_NAME := pipelock-community
BUNDLE_DIR := published/$(BUNDLE_NAME)
BUNDLE_FILE := $(BUNDLE_DIR)/bundle.yaml

# Temporary name for validation: avoids the pipelock-* prefix reservation
# that blocks unsigned local installs of official-prefix bundles.
VALIDATE_NAME := validate-community
VALIDATE_DIR := /tmp/pipelock-validate-rules

.PHONY: compile validate sign test-fixtures publish clean stats

# Compile individual rule files into a single bundle.yaml
compile:
	@echo "Compiling rules into $(BUNDLE_FILE)..."
	@./scripts/compile.sh > $(BUNDLE_FILE)
	@echo "Done. $$(grep -c '^  - id:' $(BUNDLE_FILE)) rules compiled."

# Validate the compiled bundle: copy with a non-reserved name so
# pipelock rules install accepts it without a signature.
validate: compile
	@echo "Validating bundle..."
	@rm -rf $(VALIDATE_DIR)
	@mkdir -p $(VALIDATE_DIR)/$(VALIDATE_NAME)
	@sed 's/^name: pipelock-community/name: validate-community/' $(BUNDLE_FILE) > $(VALIDATE_DIR)/$(VALIDATE_NAME)/bundle.yaml
	@pipelock rules install --path $(VALIDATE_DIR)/$(VALIDATE_NAME) --allow-unsigned --rules-dir $(VALIDATE_DIR)/installed
	@rm -rf $(VALIDATE_DIR)
	@echo "Validation passed."

# Sign with production key (requires keystore with the agent's keypair)
sign:
	@test -n "$(AGENT)" || { echo "Usage: make sign AGENT=pipelock-official"; exit 1; }
	@pipelock sign $(BUNDLE_FILE) --agent "$(AGENT)"
	@echo "Signed: $(BUNDLE_FILE).sig"

# Run fixture tests against compiled bundle regexes
test-fixtures:
	@echo "Testing fixtures..."
	@./scripts/test-fixtures.sh
	@echo "All fixture tests passed."

# Copy to versioned path and prepare for publish
publish: compile
	@VERSION=$$(grep '^version:' $(BUNDLE_FILE) | awk '{print $$2}' | tr -d '"'); \
	echo "Publishing $(BUNDLE_NAME) v$$VERSION..."; \
	mkdir -p "$(BUNDLE_DIR)/$$VERSION"; \
	cp $(BUNDLE_FILE) "$(BUNDLE_DIR)/$$VERSION/"; \
	test -f $(BUNDLE_FILE).sig && cp $(BUNDLE_FILE).sig "$(BUNDLE_DIR)/$$VERSION/" || true; \
	echo "Published to $(BUNDLE_DIR)/$$VERSION/"

clean:
	rm -rf $(VALIDATE_DIR)

# Print canonical stats from the compiled bundle
stats:
	@echo "# pipelock-rules stats"
	@echo "rules_total: $$(grep -c '  name: ' $(BUNDLE_FILE))"
	@echo "rules_dlp: $$(grep -B2 'type: dlp' $(BUNDLE_FILE) | grep -c '  - id:')"
	@echo "rules_injection: $$(grep -B2 'type: injection' $(BUNDLE_FILE) | grep -c '  - id:')"
	@echo "rules_tool_poison: $$(grep -B2 'type: tool-poison' $(BUNDLE_FILE) | grep -c '  - id:')"
	@echo "rules_stable: $$(grep -c 'status: stable' $(BUNDLE_FILE))"
	@echo "rules_experimental: $$(grep -c 'status: experimental' $(BUNDLE_FILE))"
