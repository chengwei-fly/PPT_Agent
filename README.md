# PPT_Agent

AI-powered PPT generation / knowledge base / agent evolution platform.

Upload source documents or PPTX samples, build a knowledge base with embeddings, then generate style-aligned presentations from a single sentence prompt.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- pnpm 9+
- Docker & Docker Compose

### 1. Start Infrastructure

```bash
make dev
# or manually:
cd infra && docker compose up -d
```

This starts PostgreSQL 16 (pgvector), Redis 7, MinIO, Jaeger, Prometheus, Grafana.

### 2. Backend

```bash
cd backend
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

Open http://localhost:5173

### 4. Seed Sample Data

```bash
cd backend
python -m src.scripts.seed_samples
```

## Project Structure

```
PPT_Agent/
├── backend/          # FastAPI (Python 3.11+) server
│   ├── src/
│   │   ├── agents/       # Agent orchestration (ReAct, Orchestrator)
│   │   ├── api/          # REST + WebSocket endpoints
│   │   ├── core/         # Config, security, observability, PII
│   │   ├── db/           # SQLAlchemy models + Alembic migrations
│   │   ├── middleware/    # Idempotency, request-ID
│   │   ├── models/       # Pydantic DTOs
│   │   ├── scheduler/    # Redis queue worker
│   │   ├── services/     # Business logic (generation, KB, scoring)
│   │   ├── storage/      # MinIO client
│   │   └── tools/        # SVG2PPTX, sample parser, PII detector
│   ├── tests/            # Unit, contract, integration, e2e
│   └── migrations/       # Alembic migration files
├── frontend/         # React 18 + TypeScript (Vite)
│   ├── src/
│   │   ├── components/   # UI components (Radix + Tailwind)
│   │   ├── hooks/        # React Query + custom hooks
│   │   ├── pages/        # Route pages
│   │   ├── stores/       # Zustand state
│   │   └── ws/           # WebSocket subscriptions
│   └── tests/            # Vitest + Playwright
├── infra/            # Docker Compose + Grafana dashboards
├── scripts/          # Utility scripts (availability report, etc.)
└── specs/            # Design documents and contracts
```

## Development

### Commands

```bash
make dev        # Start all services (infra + backend + frontend)
make test       # Run all tests (unit + contract + integration)
make lint       # Run linters (ruff + eslint + prettier)
make migrate    # Run Alembic migrations
make seed       # Seed sample PPTX fixtures into MinIO
```

### Testing

```bash
# Backend
cd backend
uv run pytest tests/unit                    # Unit tests
uv run pytest tests/contract                # Contract tests
uv run pytest tests/integration             # Integration tests
uv run pytest tests/integration/test_token_budget.py  # Token budget (SC-001)

# Frontend
cd frontend
pnpm run test            # Vitest unit tests
pnpm run test:e2e        # Playwright e2e tests
```

### Code Generation

```bash
cd frontend
pnpm run gen:api         # Generate TypeScript API client from OpenAPI spec
```

## Architecture

### Generation Pipeline

```
User prompt → Outline → Points → SVG → PPTX
                 ↓          ↓       ↓
            Knowledge   ReAct Agent  SVG2PPTX
            Retriever   (LLM calls)  Tool
```

### Key Technologies

| Layer | Stack |
|-------|-------|
| Backend | FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 |
| Frontend | React 18, Vite, TypeScript, Tailwind, Radix UI, Zustand, React Query |
| Infra | PostgreSQL 16 (pgvector), Redis 7, MinIO, Jaeger, Prometheus, Grafana |
| Testing | pytest, Vitest, Playwright, Pact, bandit |

## Milestone Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| **M0** | Setup + Foundational (T001-T029) | Done |
| **M1** | US1: Generate PPT from prompt (T030-T050) | Done |
| **M2** | US2: Knowledge base management (T051-T071) | Done |
| **M3** | US3+US4: Preferences + Trace (T072-T093) | Done |
| **M4** | US5: Security + Polish (T094-T123) | In Progress |
| **M5** | US6: Materials + Drafts (T200-T282) | Done (backend) |

## Contributing

1. Create a feature branch from `main`
2. Write tests first (Constitution §VI)
3. Ensure `make lint && make test` passes
4. Submit PR — CI must pass all 6 stages
5. At least 1 reviewer required; 2 for core generation/agent changes

## License

Proprietary. See LICENSE file.
