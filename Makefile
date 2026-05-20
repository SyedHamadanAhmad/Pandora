COMPOSE := docker compose
COMPOSE_DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_STUB := $(COMPOSE_DEV) -f docker-compose.stub.yml --profile stub
COMPOSE_AGENTS_PARSE := $(COMPOSE_DEV) -f docker-compose.agents.yml --profile agents-parse
COMPOSE_PARSE_E2E := $(COMPOSE_AGENTS_PARSE) -f docker-compose.stub.yml --profile stub
COMPOSE_BRIEF_E2E := $(COMPOSE_DEV) -f docker-compose.agents.yml \
	--profile agents-parse --profile agents-downstream \
	-f docker-compose.stub.yml --profile stub
COMPOSE_AGENTS_FULL := $(COMPOSE_DEV) -f docker-compose.agents.yml \
	--profile agents-parse --profile agents-downstream

# Default parallelism for component.generate / component.generated consumers
COMPONENT_GEN_SCALE ?= 5
FEEDBACK_SCALE ?= 5

.PHONY: dev dev-stub dev-agents dev-parse-agents dev-parse-e2e dev-brief-e2e dev-phase5-e2e dev-phase6-e2e dev-phase7-e2e down-phase6-e2e down-phase7-e2e up down logs migrate test test-integration phase2-gate shell scale-component-gen scale-feedback check-env test-parse-unit test-phase6-unit test-phase7-unit

check-env:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)

dev: check-env
	$(COMPOSE_DEV) up --build

dev-stub: check-env
	$(COMPOSE_STUB) up --build

dev-parse-agents: check-env
	$(COMPOSE_AGENTS_PARSE) up --build

dev-agents: dev-phase7-e2e

# Parse agents + stub downstream (brief/schema) — do not run stub-parse-* with real parse workers
dev-parse-e2e: check-env
	$(COMPOSE_PARSE_E2E) up --build worker-parse-text worker-parse-image worker-parse-url stub-downstream

# Real Brief + Schema workers + stub downstream (component/verify/showcase only).
# Do not run stub-parse-* with real parse workers.
dev-phase5-e2e: check-env
	STUB_SKIP_BRIEF=1 STUB_SKIP_SCHEMA=1 $(COMPOSE_BRIEF_E2E) up --build \
		worker-parse-text worker-parse-url worker-brief worker-schema stub-downstream

# Tear down Phase 6 E2E stack (fixes stale Docker networks after Ctrl+C).
down-phase6-e2e:
	$(COMPOSE_BRIEF_E2E) down --remove-orphans

# Real parse + brief + schema + component-gen + feedback; stub handles verify/showcase only.
# Override scale: make dev-phase6-e2e COMPONENT_GEN_SCALE=3 FEEDBACK_SCALE=3
dev-phase6-e2e: check-env down-phase6-e2e
	STUB_SKIP_BRIEF=1 STUB_SKIP_SCHEMA=1 STUB_SKIP_COMPONENT=1 $(COMPOSE_BRIEF_E2E) up -d --build --wait postgres rabbitmq minio backend
	STUB_SKIP_BRIEF=1 STUB_SKIP_SCHEMA=1 STUB_SKIP_COMPONENT=1 $(COMPOSE_BRIEF_E2E) up --build \
		--scale worker-component-gen=$(COMPONENT_GEN_SCALE) \
		--scale worker-feedback=$(FEEDBACK_SCALE) \
		worker-parse-text worker-parse-url worker-brief worker-schema \
		worker-component-gen worker-feedback stub-downstream

# Full real-agent pipeline (no stub-downstream).
down-phase7-e2e:
	$(COMPOSE_AGENTS_FULL) down --remove-orphans

dev-phase7-e2e: check-env down-phase7-e2e
	STUB_SKIP_BRIEF=1 STUB_SKIP_SCHEMA=1 STUB_SKIP_COMPONENT=1 $(COMPOSE_AGENTS_FULL) up -d --build --wait postgres rabbitmq minio backend
	$(COMPOSE_AGENTS_FULL) up --build \
		--scale worker-component-gen=$(COMPONENT_GEN_SCALE) \
		--scale worker-feedback=$(FEEDBACK_SCALE) \
		worker-parse-text worker-parse-url worker-brief worker-schema \
		worker-component-gen worker-feedback worker-verification worker-showcase

# Alias: brief-only real agent (stub still handles schema unless you use dev-phase5-e2e).
dev-brief-e2e: check-env
	STUB_SKIP_BRIEF=1 $(COMPOSE_BRIEF_E2E) up --build \
		worker-parse-text worker-parse-url worker-brief stub-downstream

test-parse-unit:
	@PYTHONPATH=workers/src:pandora_shared python3.11 -m unittest \
	  backend.tests.unit.test_parse_agents \
	  backend.tests.unit.test_brief_agent \
	  backend.tests.unit.test_schema_agent \
	  -v

test-phase6-unit:
	@PYTHONPATH=workers/src:pandora_shared python3.11 -m unittest \
	  backend.tests.unit.test_component_gen_agent \
	  backend.tests.unit.test_feedback_agent \
	  -v

test-phase7-unit:
	@PYTHONPATH=workers/src:pandora_shared python3.11 -m unittest \
	  backend.tests.unit.test_verification_agent \
	  backend.tests.unit.test_showcase_agent \
	  -v

up: check-env
	$(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate: check-env
	$(COMPOSE) run --rm backend-migrate alembic upgrade head

test: test-integration

test-integration: check-env
	$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
		pytest tests/integration/ -v

phase2-gate: check-env
	@chmod +x scripts/phase2_gate.sh
	@if curl -sf http://localhost:8000/health >/dev/null 2>&1; then \
		BASE_URL=http://localhost:8000 ./scripts/phase2_gate.sh; \
	else \
		echo "localhost:8000 not reachable — running gate inside backend container..."; \
		$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml exec -T backend \
			env BASE_URL=http://127.0.0.1:8000 ./scripts/phase2_gate.sh; \
	fi

test-e2e:
	@echo "E2E tests — implemented in Phase 9 (requires DEEPSEEK_API_KEY)"

scale-component-gen:
	@test -n "$(n)" || (echo "Usage: make scale-component-gen n=5" && exit 1)
	$(COMPOSE_BRIEF_E2E) up --scale worker-component-gen=$(n) -d worker-component-gen

scale-feedback:
	@test -n "$(n)" || (echo "Usage: make scale-feedback n=5" && exit 1)
	$(COMPOSE_BRIEF_E2E) up --scale worker-feedback=$(n) -d worker-feedback

shell:
	@test -n "$(s)" || (echo "Usage: make shell s=backend" && exit 1)
	$(COMPOSE) exec $(s) bash

queues-dlq:
	@echo "Check RabbitMQ management UI at http://localhost:15672 for DLQ depth"
