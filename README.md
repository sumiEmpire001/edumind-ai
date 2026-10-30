# EduMind AI

**Teach students, not just answer questions.**

AI academic support platform, built in verified phases. This repository currently
contains **Phase 1 only**: React/Vite foundation, FastAPI health checks,
PostgreSQL/pgvector configuration, Alembic baseline, tests, CI, and documentation.
It is not a production-ready learning platform yet. No authentication, AI calls,
uploads, RAG indexing, or local watcher is implemented.

## Requirements

Git, Python 3.12, Node.js 22.12+ (22 LTS recommended), and Docker Compose v2.
On Windows, run each command as a separate PowerShell command from the stated folder.
Docker Desktop must be running for local PostgreSQL.

## Get the source

Clone the project repository:

```sh
git clone https://github.com/sumiEmpire001/edumind-ai.git
cd edumind-ai
```

If you downloaded the source archive, extract it and open its `edumind-ai` folder.

## Local database

From the repository root:

```sh
cp .env.example .env
docker compose up -d db
```

PowerShell: use `Copy-Item .env.example .env` instead of `cp` if preferred.
The database port is bound to localhost only. The named volume persists data.
Never use `docker compose down -v` as a repair command: it destroys that data.

## Backend

From the repository root:

```sh
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on Windows PowerShell or
`source .venv/bin/activate` on Linux/macOS. Then:

```sh
cd backend
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:create_app --factory --reload --port 8000 --no-access-log
```

API docs: http://localhost:8000/docs (development only).
Liveness: `/api/v1/health/live`. Readiness: `/api/v1/health/ready`.
Readiness returns 503 when the database, pgvector, or required migration is missing.
No tables or migrations are applied automatically at application startup.

## Frontend

In another terminal, from the repository root:

```sh
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Open http://localhost:5173. `Check connection` calls the backend readiness API.
The page is a development shell, not the Phase 3 landing page or a simulated login.
Only `VITE_API_BASE_URL` is public configuration; never put secrets in Vite variables.

## Verification

From `backend` with the virtual environment activated:

```sh
ruff check .
ruff format --check .
pytest -q -m "not integration"
pip-audit -r requirements.txt
```

For database integration, create a **separate disposable** PostgreSQL database,
set `TEST_DATABASE_URL` to its psycopg URL, then run `pytest -q -m integration`.
The integration test applies the baseline twice and executes real vector SQL.
Without that variable it explicitly skips; a skip is not a successful database test.
CI provisions an isolated pgvector PostgreSQL service and runs both suites.

From `frontend`:

```sh
npm run lint
npm run typecheck
npm test
npm run build
npm audit --audit-level=high
```

## Documentation

- [Architecture and security boundaries](docs/architecture.md)
- [Phased roadmap and acceptance gates](docs/roadmap.md)
- [Deployment and migrations](docs/deployment.md)
- [Phase 1 development report](docs/phase-1-report.md)

## Source control

Repository: https://github.com/sumiEmpire001/edumind-ai

Use feature branches and pull requests from Phase 2 onward. Require both CI jobs
before merging when repository settings allow it. Do not commit `.env`, uploads,
databases, tokens, or private academic materials. Cloud deployment belongs to Phase 11.
