BUNDLE_NAME := pipelock-community
BUNDLE_DIR := published/$(BUNDLE_NAME)
BUNDLE_FILE := $(BUNDLE_DIR)/bundle.yaml

.PHONY: compile validate sign verify test-fixtures publish clean

# Compile individual rule files into a single bundle.yaml
compile:
	@echo "Compiling rules into $(BUNDLE_FILE)..."
	@./scripts/compile.sh > $(BUNDLE_FILE)
	@echo "Done. $$(grep -c '^  - id:' $(BUNDLE_FILE)) rules compiled."

# Validate the compiled bundle with pipelock binary
validate: compile
	@echo "Validating bundle..."
	@rm -rf /tmp/pipelock-validate-rules
	@pipelock rules install --path $(BUNDLE_DIR) --allow-unsigned --rules-dir /tmp/pipelock-validate-rules 2>&1 || true
	@rm -rf /tmp/pipelock-validate-rules
	@echo "Validation complete."

# Sign with production key (requires USB key mounted)
sign:
	@test -f "$(KEY)" || { echo "Usage: make sign KEY=/path/to/private.key"; exit 1; }
	@pipelock sign $(BUNDLE_FILE) --key "$(KEY)"
	@echo "Signed: $(BUNDLE_FILE).sig"

# Verify signature against public key
verify:
	@test -f "$(PUBKEY)" || { echo "Usage: make verify PUBKEY=/path/to/public.key"; exit 1; }
	@pipelock verify $(BUNDLE_FILE) --key "$(PUBKEY)"

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
	rm -rf /tmp/pipelock-validate-rules
