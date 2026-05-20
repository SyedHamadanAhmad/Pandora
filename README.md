# Pandora

Intelligent agentic design system generator — POC.

Transforms multi-modal input (text, images, URLs) into a production-ready React component library with real-time SSE streaming.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- `make`

## First-time setup

```bash
cp .env.example .env
# Edit .env — set DEEPSEEK_API_KEY before running workers (Phase 4+)

make dev        # Start stack with hot reload (dev override)
make migrate    # Run Alembic migrations (first run and after schema changes)
```

Open:

- Frontend (dev): http://localhost:5173
- Frontend (prod `make up`): http://localhost:3000
- RabbitMQ management: http://localhost:15672 (credentials from `.env`)
- MinIO console: http://localhost:9001 (credentials from `.env`)
- PostgreSQL (dev, GUI clients): `postgresql://pandora:pandora@localhost:5432/pandora`

## Makefile commands

| Command | Description |
|---------|-------------|
| `make dev` | Dev stack with volume mounts and hot reload |
| `make up` | Production-style stack (built images, no volume mounts) |
| `make down` | Stop all services |
| `make migrate` | Run `alembic upgrade head` |
| `make logs` | Tail all service logs |
| `make shell s=backend` | Shell into a running container |
| `make scale-component n=5` | Scale component generation workers |
| `make dev-parse-agents` | Phase 4 parse workers (text, image, url) |
| `make dev-parse-e2e` | Parse agents + stub downstream (brief/schema) |
| `make test-parse-unit` | Unit tests for parse agents |

## Project layout

```
pandora/
├── pandora_shared/   # Shared queues, enums, message envelopes (pip install -e)
├── frontend/         # React + Vite + Sandpack
├── backend/          # FastAPI — sole DB writer
├── workers/          # Stateless RabbitMQ agent workers
├── docker-compose.yml
└── docker-compose.dev.yml
```

Install `pandora_shared` locally (optional, for IDE support):

```bash
pip install -e ./pandora_shared
```

## Documentation

- [Phase 0 walkthrough](docs/PHASE_0.md)
- [Phase 1 implementation plan](docs/PHASE_1.md)
- [Phases 4–7 — real agents](docs/PHASES_4_7_IMPLEMENTATION.md)
- [Phase 4 — implementation reference](docs/PHASE_4_IMPLEMENTATION.md)
- [Phase 4 — testing parse agents (URL focus)](docs/PHASE_4_TESTING.md)
- [Pandora_PRD.pdf](Pandora_PRD.pdf)
- [Pandora_TechSpec_v1.7.pdf](Pandora_TechSpec_v1.7.pdf)
