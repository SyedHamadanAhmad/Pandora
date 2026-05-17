COMPOSE := docker compose
COMPOSE_DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: dev up down logs migrate test shell scale-component check-env

check-env:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)

dev: check-env
	$(COMPOSE_DEV) up --build

up: check-env
	$(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate: check-env
	$(COMPOSE) run --rm backend-migrate alembic upgrade head

test:
	@echo "Integration tests — implemented in Phase 9"

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
