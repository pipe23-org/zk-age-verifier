# ORIGIN must equal ORIGIN in tests/integration/conftest.py: the presenter signs the
# transcript over this origin and the server checks it against expected_origin. It is a
# declared transcript input, unrelated to the socket address below.
ORIGIN := https://chat.example.org
PORT := 8791
ANCHOR := $(CURDIR)/tests/integration/credentials/test-anchor.pem

CONTAINER_PORT := 8792
CONTAINER_CACHE := zk_age_verifier_test_circuits
CONTAINER_COMPOSE := docker compose -f compose.yaml -f compose.test.yaml

.PHONY: test-live test-container

# Integration suite against a local granian process — the deployment path
# (config load, env-var handoff, real socket) that in-process pytest skips.
test-live:
	@tmp=$$(mktemp -d); \
	config="$$tmp/config.toml"; \
	log="$$tmp/server.log"; \
	printf '[service]\nexpected_origin = "%s"\n[trust]\nsources = [{ pem = "%s" }]\n' \
		"$(ORIGIN)" "$(ANCHOR)" > "$$config"; \
	ZK_AGE_VERIFIER_CONFIG="$$config" uv run granian --interface asgi --factory \
		--workers 1 --host 127.0.0.1 --port $(PORT) \
		zk_age_verifier.app:app_factory > "$$log" 2>&1 & \
	pid=$$!; \
	trap 'kill $$pid 2>/dev/null; wait $$pid 2>/dev/null' EXIT; \
	up=0; i=0; \
	while [ $$i -lt 50 ]; do \
		if curl -sf http://127.0.0.1:$(PORT)/health >/dev/null 2>&1; then up=1; break; fi; \
		i=$$((i + 1)); sleep 0.2; \
	done; \
	if [ $$up -ne 1 ]; then echo "server did not answer /health"; cat "$$log"; exit 1; fi; \
	uv run pytest tests/integration --transport=live --base-url=http://127.0.0.1:$(PORT) --no-cov; \
	status=$$?; \
	if [ $$status -ne 0 ]; then echo "--- server log ---"; cat "$$log"; fi; \
	exit $$status

# The same integration suite against the compose-built image — the packaging path
# (image build, entrypoint, mounts) on top of what test-live covers.
# The image runs as non-root user app (uid 1000); the mounted config must be
# world-readable because mktemp -d dirs are mode 700. The trust anchor and config
# name the anchor by its in-container path. The circuit cache is an external named
# volume so first-boot generation is paid once; the post-run check asserts the cache
# actually landed in the volume (the mount path must match the app's derived default).
test-container:
	@tmp=$$(mktemp -d); \
	chmod 755 "$$tmp"; \
	config="$$tmp/config.toml"; \
	printf '[service]\nexpected_origin = "%s"\n[trust]\nsources = [{ pem = "/etc/zk-age-verifier/anchors" }]\n' \
		"$(ORIGIN)" > "$$config"; \
	chmod 644 "$$config"; \
	export TEST_CONTAINER_CONFIG="$$config"; \
	export TEST_CONTAINER_ANCHOR="$(ANCHOR)"; \
	trap '$(CONTAINER_COMPOSE) down >/dev/null 2>&1' EXIT; \
	$(CONTAINER_COMPOSE) build || exit 1; \
	docker volume create $(CONTAINER_CACHE) >/dev/null; \
	$(CONTAINER_COMPOSE) up -d || exit 1; \
	up=0; i=0; \
	while [ $$i -lt 180 ]; do \
		if curl -sf http://127.0.0.1:$(CONTAINER_PORT)/health >/dev/null 2>&1; then up=1; break; fi; \
		i=$$((i + 1)); sleep 1; \
	done; \
	if [ $$up -ne 1 ]; then echo "container did not answer /health"; $(CONTAINER_COMPOSE) logs; exit 1; fi; \
	uv run pytest tests/integration --transport=live --base-url=http://127.0.0.1:$(CONTAINER_PORT) --no-cov; \
	status=$$?; \
	if [ $$status -eq 0 ]; then \
		$(CONTAINER_COMPOSE) exec -T app sh -c 'ls -A /home/app/.cache/zk-age-verifier/circuits | grep -q .' \
			|| { echo "circuit cache volume is empty after run"; status=1; }; \
	fi; \
	if [ $$status -ne 0 ]; then echo "--- compose logs ---"; $(CONTAINER_COMPOSE) logs; fi; \
	exit $$status
