BUNDLE_NAME ?= pipelock-community
BUNDLE_DIR := published/$(BUNDLE_NAME)
BUNDLE_FILE := $(BUNDLE_DIR)/bundle.yaml
PREFLIGHT_BUNDLES := pipelock-community healthcare-phi-pii

# Temporary name for validation: avoids the pipelock-* prefix reservation
# that blocks unsigned local installs of official-prefix bundles.
TMPDIR := $(HOME)/.cache/pipelock-tmp
GOCACHE := $(HOME)/.cache/go-build
export TMPDIR GOCACHE
VALIDATE_NAME ?= validate-$(BUNDLE_NAME)
VALIDATE_DIR := $(TMPDIR)/pipelock-validate-rules

.PHONY: preflight compile validate require-pipelock sign test-fixtures publish clean stats diagrams check-diagrams brand check-brand

# Runs fully offline when Pipelock is already installed. The CLI is the schema
# authority, so absence is a clear fail-closed prerequisite error, never an
# implicit download or a skipped schema check. Check every maintained bundle:
# a default-only gate would miss a normal healthcare rule change.
preflight: check-diagrams check-brand
	@set -e; for bundle in $(PREFLIGHT_BUNDLES); do \
		$(MAKE) BUNDLE_NAME="$$bundle" validate test-fixtures; \
	done

# Regenerate the README diagrams from the live bundles.
diagrams:
	@python3 scripts/render_diagrams.py

# Compose the brand assets from assets/mark.svg, the committed master.
brand:
	@command -v inkscape >/dev/null 2>&1 || { \
		echo "inkscape is required to regenerate vectors, rasters, and provenance together" >&2; \
		exit 1; \
	}
	@python3 scripts/render_brand.py
	@set -e; \
	inkscape assets/pipelock-rules-logo.svg -o assets/pipelock-rules-logo-256.png -w 256 >/dev/null; \
	inkscape assets/social-preview.svg -o assets/social-preview.png -w 1280 >/dev/null; \
	python3 scripts/render_brand.py --stamp-png; \
	echo "exported rasters"

# Fail when a brand asset drifts from the master mark, the mark stops following
# the brand rules, or the README shows a badge for a workflow that is gone.
check-brand:
	@python3 scripts/render_brand.py --check

# Fail when a committed asset, a painted count, or a README claim no longer
# matches the bundles. Needs only python3, so it runs before the Pipelock CLI
# prerequisite and gives a fast answer on a documentation-only change.
check-diagrams:
	@PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/render_diagrams_test.py
	@python3 scripts/render_diagrams.py --check

require-pipelock:
	@command -v pipelock >/dev/null 2>&1 || { \
		echo "preflight: FAIL - schema validation requires a preinstalled Pipelock CLI"; \
		echo "  This target never downloads tools; install Pipelock, then rerun make preflight."; \
		exit 1; \
	}

# Compile individual rule files into a single bundle.yaml
compile:
	@echo "Compiling rules into $(BUNDLE_FILE)..."
	@mkdir -p $(BUNDLE_DIR)
	@BUNDLE_NAME="$(BUNDLE_NAME)" ./scripts/compile.sh > $(BUNDLE_FILE)
	@echo "Done. $$(grep -c '^  - id:' $(BUNDLE_FILE)) rules compiled."

# Validate the compiled bundle: copy with a non-reserved name so
# pipelock rules install accepts it without a signature.
validate: require-pipelock compile
	@echo "Validating bundle..."
	@rm -rf $(VALIDATE_DIR)
	@mkdir -p $(VALIDATE_DIR)/$(VALIDATE_NAME)
	@sed 's/^name: .*/name: $(VALIDATE_NAME)/' $(BUNDLE_FILE) > $(VALIDATE_DIR)/$(VALIDATE_NAME)/bundle.yaml
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
	@go test scripts/test-fixtures.go scripts/test-fixtures_test.go
	@BUNDLE_NAME="$(BUNDLE_NAME)" ./scripts/test-fixtures.sh
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

# Print canonical stats from the compiled bundle.
# Uses anchored patterns matching the bundle schema to avoid false positives.
stats:
	@echo "# pipelock-rules stats"
	@echo "rules_total: $$(grep -c '^  - id:' $(BUNDLE_FILE))"
	@echo "rules_dlp: $$(grep -c '^    type: dlp' $(BUNDLE_FILE))"
	@echo "rules_injection: $$(grep -c '^    type: injection' $(BUNDLE_FILE))"
	@echo "rules_tool_poison: $$(grep -c '^    type: tool-poison' $(BUNDLE_FILE))"
	@echo "rules_stable: $$(grep -c '^    status: stable' $(BUNDLE_FILE))"
	@echo "rules_experimental: $$(grep -c '^    status: experimental' $(BUNDLE_FILE))"
