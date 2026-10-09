# Makefile for AWS SAM Custom Builds (Metadata: BuildMethod: makefile)
#
# When `sam build` runs, SAM looks for targets named `build-<LogicalId>`.
# It provides ARTIFACTS_DIR as the staging directory that will be zipped
# into the respective Lambda deployment package.

.PHONY: build-ZaloWebhookFunction build-ZaloWorkerFunction

# -----------------------------------------------------------------------------
# Zalo Webhook Lambda (Fast intake API)
# SLA < 2s; sub-50ms cold start. Zero third-party runtime dependencies.
# Packages only api/ and shared/ without vendor packages.
# -----------------------------------------------------------------------------
build-ZaloWebhookFunction:
	mkdir -p $(ARTIFACTS_DIR)/api $(ARTIFACTS_DIR)/shared
	cp -R src/api/. $(ARTIFACTS_DIR)/api/
	cp -R src/shared/. $(ARTIFACTS_DIR)/shared/
	find $(ARTIFACTS_DIR) -name "__pycache__" -type d -prune -exec rm -rf {} +
	find $(ARTIFACTS_DIR) -name "*.pyc" -delete

# -----------------------------------------------------------------------------
# Zalo Worker Lambda (Queue processor)
# Asynchronous worker for heavier event processing.
# Packages worker/ and shared/, plus dependencies from [dependency-groups.worker].
# -----------------------------------------------------------------------------
build-ZaloWorkerFunction:
	mkdir -p $(ARTIFACTS_DIR)/worker $(ARTIFACTS_DIR)/shared
	cp -R src/worker/. $(ARTIFACTS_DIR)/worker/
	cp -R src/shared/. $(ARTIFACTS_DIR)/shared/
	@if command -v uv >/dev/null 2>&1; then \
		uv export --frozen --only-group worker --no-hashes --no-dev --no-emit-project -o $(ARTIFACTS_DIR)/requirements.txt; \
		if grep -E -v '^[[:space:]]*(#|$$)' $(ARTIFACTS_DIR)/requirements.txt >/dev/null 2>&1; then \
			uv pip install -r $(ARTIFACTS_DIR)/requirements.txt --target $(ARTIFACTS_DIR) --python-platform linux --python-version 3.14 --link-mode copy; \
		fi; \
		rm -f $(ARTIFACTS_DIR)/requirements.txt; \
	fi
	find $(ARTIFACTS_DIR) -name "__pycache__" -type d -prune -exec rm -rf {} +
	find $(ARTIFACTS_DIR) -name "*.pyc" -delete
