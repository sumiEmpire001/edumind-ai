# EduMind AI

**Teach students, not just answer questions.**

AI academic support platform with student conversations, live Gemini answers,
contributor applications, private document submissions, administrator review,
approved-source retrieval and a separate Windows-compatible knowledge inbox.

The hosted test app is at https://edumind-ai-an-empire.vercel.app/ . Live Gemini chat
is verified. The document workflows and local inbox are implemented and tested;
hosted storage, a separately approved worker, administrator bootstrap and real-corpus
verification remain activation gates. Document retrieval stays disabled until those
checks pass. See [release readiness](docs/final-readiness.md) for evidence and limits.

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
```

Generate a signing secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
and put it in `JWT_SECRET` in `backend/.env` (replace the example placeholder).
Then run:

```sh
alembic upgrade head
uvicorn app.main:create_app --factory --reload --port 8000 --no-access-log
```

API docs: http://localhost:8000/docs (development only).
Liveness: `/api/v1/health/live`. Readiness: `/api/v1/health/ready`.
Readiness returns 503 when the database, pgvector, or required migration is missing.
Normal application startup never creates tables. The explicit test-deployment entrypoint
`python -m app.start` runs migrations only when `RUN_DATABASE_MIGRATIONS=true`.
Use a separate release migration operation for production.

## Frontend

In another terminal, from the repository root:

```sh
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Open http://localhost:5173. Start the backend and apply its migrations before signing in.
The frontend includes landing, registration/login, workspace, account, study chat and
role-aware knowledge-library pages. Gemini is available only when the backend key is
configured; uploads report unavailable until private storage is configured.
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
The integration tests apply migrations and execute real vector SQL, while the auth suite
runs API, concurrency and admin bootstrap tests inside an isolated PostgreSQL schema.
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
- [Authentication and admin operations](docs/authentication.md)
- [Phase 2 development report](docs/phase-2-report.md)
- [Frontend authentication and browser tests](docs/frontend-authentication.md)
- [Phase 3 development report](docs/phase-3-report.md)
- [Conversation architecture and testing](docs/conversations.md)
- [Phase 4 development report](docs/phase-4-report.md)
- [Gemini verification](docs/phase-5-report.md)
- [Knowledge platform](docs/phase-6-8-report.md)
- [Knowledge operations](docs/knowledge-operations.md)
- [Local inbox setup](services/knowledge-inbox/README.md)
- [Final implementation](docs/phase-9-12-report.md)
- [Release readiness and remaining gates](docs/final-readiness.md)

## Source control

Repository: https://github.com/sumiEmpire001/edumind-ai

Use feature branches and pull requests, and require backend, frontend, browser and
Linux/Windows inbox checks. Do not commit `.env`, uploads, databases, tokens, or private
academic materials. The hosted frontend currently uses a source snapshot; GitHub remains
the canonical source. Automatic Vercel Git integration is a remaining setup task.
