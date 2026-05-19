COMPOSE := docker compose
COMPOSE_DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_STUB := $(COMPOSE_DEV) -f docker-compose.stub.yml --profile stub
COMPOSE_AGENTS := $(COMPOSE_DEV) -f docker-compose.agents.yml --profile agents

.PHONY: dev dev-stub dev-agents up down logs migrate test test-integration phase2-gate shell scale-component check-env

check-env:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)

dev: check-env
	$(COMPOSE_DEV) up --build

dev-stub: check-env
	$(COMPOSE_STUB) up --build

dev-agents: check-env
	$(COMPOSE_AGENTS) up --build

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

scale-component:
	@test -n "$(n)" || (echo "Usage: make scale-component n=5" && exit 1)
	$(COMPOSE) up --scale worker-component=$(n) -d

shell:
	@test -n "$(s)" || (echo "Usage: make shell s=backend" && exit 1)
	$(COMPOSE) exec $(s) bash

queues-dlq:
	@echo "Check RabbitMQ management UI at http://localhost:15672 for DLQ depth"
