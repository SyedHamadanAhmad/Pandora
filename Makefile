# Pandora — local development
# Run `make help` for commands.
#
# Follow logs:  make start-watch  |  make start WATCH=1  |  ./scripts/dev start --watch

COMPOSE := docker compose
COMPOSE_DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_WORKERS := $(COMPOSE_DEV) -f docker-compose.workers.yml

COMPONENT_GEN_SCALE ?= 3
FEEDBACK_SCALE ?= 3

WATCH ?= 0
ifneq ($(filter watch,$(MAKECMDGOALS)),)
  override WATCH := 1
endif

WORKER_SERVICES := worker-parse-text worker-parse-image worker-parse-url \
	worker-brief worker-schema worker-component-gen worker-feedback worker-verification

.PHONY: help setup start start-watch workers workers-watch start-all start-all-watch \
	down logs follow-logs follow-backend-logs follow-worker-logs migrate test shell health up watch

.DEFAULT_GOAL := help

watch:
	@:

help:
	@echo "Pandora — local development"
	@echo ""
	@echo "  make setup        Copy .env.example → .env (first time)"
	@echo "  make start        API + Postgres + RabbitMQ + Redis + MinIO"
	@echo "  make workers      Agent workers (requires OPENROUTER_API_KEY in .env)"
	@echo "  make start-all    start + workers"
	@echo "  make down         Stop all containers"
	@echo "  make logs         Follow backend logs only"
	@echo "  make migrate      Run Alembic migrations"
	@echo "  make test         Backend integration tests"
	@echo "  make shell s=backend   Shell into a service"
	@echo "  make health       Hit /health"
	@echo ""
	@echo "  Follow logs after up:"
	@echo "    make start-watch          (or: make start WATCH=1 | make start watch)"
	@echo "    make workers-watch        make start-all-watch"
	@echo "    ./scripts/dev start --watch   (same; works on macOS)"
	@echo ""
	@echo "  Frontend (host):  cd frontend && npm install && npm run dev"
	@echo "  API:              http://localhost:8000"
	@echo "  RabbitMQ UI:      http://localhost:15672"
	@echo "  Postman guide:    docs/POSTMAN_PIPELINE_TEST.md"

setup:
	@test -f .env || cp .env.example .env
	@echo "Set OPENROUTER_API_KEY in .env before make workers"

check-env:
	@test -f .env || (echo "Missing .env — run: make setup" && exit 1)

start: check-env
	$(COMPOSE_DEV) up -d --build --wait \
		postgres rabbitmq redis minio backend
	@$(if $(filter 1,$(WATCH)),$(MAKE) follow-backend-logs,)

start-watch:
	@$(MAKE) start WATCH=1

workers: check-env
	$(COMPOSE_WORKERS) up -d --build \
		--scale worker-component-gen=$(COMPONENT_GEN_SCALE) \
		--scale worker-feedback=$(FEEDBACK_SCALE) \
		$(WORKER_SERVICES)
	@$(if $(filter 1,$(WATCH)),$(MAKE) follow-worker-logs,)

workers-watch:
	@$(MAKE) workers WATCH=1

start-all: check-env
	@$(MAKE) start WATCH=0
	@$(MAKE) workers WATCH=0
	@$(if $(filter 1,$(WATCH)),$(MAKE) follow-logs,)

start-all-watch:
	@$(MAKE) start-all WATCH=1

follow-backend-logs:
	$(COMPOSE_DEV) logs -f backend

follow-worker-logs:
	$(COMPOSE_WORKERS) logs -f $(WORKER_SERVICES)

follow-logs:
	$(COMPOSE_WORKERS) logs -f backend $(WORKER_SERVICES)

down:
	$(COMPOSE_DEV) -f docker-compose.workers.yml down --remove-orphans

logs:
	$(COMPOSE_DEV) logs -f backend

migrate: check-env
	$(COMPOSE_DEV) run --rm backend-migrate alembic upgrade head

test: check-env
	$(COMPOSE_DEV) run --rm backend pytest tests/integration/ -v

shell:
	@test -n "$(s)" || (echo "Usage: make shell s=backend" && exit 1)
	$(COMPOSE_DEV) exec $(s) bash

health:
	@curl -sf http://localhost:8000/health | python3 -m json.tool || \
		(echo "API not reachable — run: make start" && exit 1)

up: check-env
	$(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up --build -d
