# Pandora

Intelligent agentic design system generator — POC.

Transforms multi-modal input (text, images, URLs) into a production-ready React component library with real-time SSE streaming.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- `make`

## First-time setup

```bash
make setup          # copies .env.example → .env
# Edit .env — set OPENROUTER_API_KEY only if using real LLM workers

make start-all      # API + infra + agent workers
make health         # verify API is up
```

**Frontend (on host, optional):**

```bash
cd frontend && npm install && npm run dev
# → http://localhost:5173 (proxies /api → :8000)
```

**API testing:** [docs/POSTMAN_PIPELINE_TEST.md](docs/POSTMAN_PIPELINE_TEST.md) — import `docs/postman/Pandora_API.postman_collection.json`

### URLs

| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |
| Frontend (host) | http://localhost:5173 |
| RabbitMQ UI | http://localhost:15672 |
| MinIO console | http://localhost:9001 |
| PostgreSQL | `postgresql://pandora:pandora@localhost:5432/pandora` |

## Makefile commands

Run `make help` for the full list.

| Command | Description |
|---------|-------------|
| `make setup` | Create `.env` from example |
| `make start` | API + Postgres + RabbitMQ + Redis + MinIO |
| `make workers` | Agent workers (needs `OPENROUTER_API_KEY`) |
| `make start-all` | `start` + `workers` |
| `make down` | Stop all containers |
| `make logs` | Follow backend logs |
| `make migrate` | Run Alembic migrations |
| `make test` | Integration tests in Docker |
| `make health` | Check `/health` |
| `make up` | Production-style stack (frontend on :3000) |

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
