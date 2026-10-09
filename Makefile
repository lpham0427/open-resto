# Makefile for AWS SAM Custom Builds (Metadata: BuildMethod: makefile)
#
# When `sam build` runs, SAM looks for targets named `build-<LogicalId>`.
# It provides ARTIFACTS_DIR as the staging directory that will be zipped
# into the respective Lambda deployment package.

.PHONY: build-ReceiveZaloEventFunction build-ProcessOrderFunction

# -----------------------------------------------------------------------------
# Receive Zalo Event Lambda (Fast intake API)
# SLA < 2s; sub-50ms cold start. Zero third-party runtime dependencies.
# Packages only receive_zalo_event/ and shared/ without vendor packages.
# -----------------------------------------------------------------------------
build-ReceiveZaloEventFunction:
	mkdir -p $(ARTIFACTS_DIR)/receive_zalo_event $(ARTIFACTS_DIR)/shared
	cp -R functions/receive_zalo_event/. $(ARTIFACTS_DIR)/receive_zalo_event/
	cp -R shared/. $(ARTIFACTS_DIR)/shared/
	find $(ARTIFACTS_DIR) -name "__pycache__" -type d -prune -exec rm -rf {} +
	find $(ARTIFACTS_DIR) -name "*.pyc" -delete

# -----------------------------------------------------------------------------
# Process Order Lambda (SQS FIFO Queue consumer)
# Asynchronous worker for order processing.
# Packages process_order/ and shared/, plus dependencies from [dependency-groups.worker].
# -----------------------------------------------------------------------------
build-ProcessOrderFunction:
	mkdir -p $(ARTIFACTS_DIR)/process_order $(ARTIFACTS_DIR)/shared
	cp -R functions/process_order/. $(ARTIFACTS_DIR)/process_order/
	cp -R shared/. $(ARTIFACTS_DIR)/shared/
	@if command -v uv >/dev/null 2>&1; then \
		uv export --frozen --only-group worker --no-hashes --no-dev --no-emit-project -o $(ARTIFACTS_DIR)/requirements.txt; \
		if grep -E -v '^[[:space:]]*(#|$$)' $(ARTIFACTS_DIR)/requirements.txt >/dev/null 2>&1; then \
			uv pip install -r $(ARTIFACTS_DIR)/requirements.txt --target $(ARTIFACTS_DIR) --python-platform linux --python-version 3.14 --link-mode copy; \
		fi; \
		rm -f $(ARTIFACTS_DIR)/requirements.txt; \
	fi
	find $(ARTIFACTS_DIR) -name "__pycache__" -type d -prune -exec rm -rf {} +
	find $(ARTIFACTS_DIR) -name "*.pyc" -delete
