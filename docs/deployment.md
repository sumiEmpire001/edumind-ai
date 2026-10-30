# Deployment and database operations

The test API and PostgreSQL database are hosted in Render Frankfurt. The public frontend
is hosted on Vercel. Private storage is provisioned but lacks an application credential;
a separate worker has not been purchased. See final-readiness.md for current evidence.

## GitHub

Repository: https://github.com/sumiEmpire001/edumind-ai

Confirm backend, frontend, browser and both local-inbox CI jobs pass after source updates.
Use required checks and protected branches before accepting feature changes.
Review third-party Actions and pin vetted commit SHAs before production CI hardening.

## Vercel frontend (Phase 11)

Import the GitHub repository. Root directory: `frontend`. Framework: Vite.
Install: `npm ci`; build: `npm run build`; output: `dist`.
Use `VITE_API_BASE_URL=/` with the existing API rewrite to the Render backend before
the SPA fallback. This preserves same-origin secure cookies. `frontend/vercel.json`
also contains basic security headers.
Test deep links and API connectivity. Set API CORS to the exact frontend origin;
add preview origins explicitly only when needed. Do not allow arbitrary origins.

## API and worker (Phase 11)

Deploy backend/Dockerfile using `backend` as Docker build context to a Render web
service or equivalent Python/Docker platform. The image runs as a non-root user.
Set APP_ENV=production, DATABASE_URL with verified TLS, CORS_ORIGINS JSON list and
LOG_LEVEL. Platform-provided PORT is honored. Liveness endpoint:
`/api/v1/health/live`; readiness endpoint: `/api/v1/health/ready`.
Use readiness to gate traffic; use liveness for process monitoring.
The process intentionally stays alive during database outages and returns 503 readiness.

The implemented worker command is `python -m app.knowledge.worker`. Run it in a separate
background-worker service using the same backend image, Frankfurt region, database,
storage and Gemini configuration. It does not migrate the database or bootstrap admins.
The proposed Render Starter worker is $7/month, subject to account pricing confirmation;
no purchase is authorized yet. Configure private storage before enabling uploads.
Store files there, never on an ephemeral web-service disk. Keep Gemini, session-signing
and storage credentials in backend/worker environment secrets only.
Use the managed DB's private network, verified TLS, automated backups and restore tests.
Separate migration credentials from least-privilege runtime database credentials.
Size DB connection limits across web replicas and workers (Phase 1 pool is 5+5/API process).

## Alembic migration procedure

1. Back up production and confirm restore readiness before risky schema changes.
2. Review migration SQL and test against a restored staging database.
3. Run `alembic upgrade head` once as a release operation, before traffic shifts.
4. Check `alembic current` and readiness, then application workflows.
5. Roll back application code where compatible; prefer forward data-preserving fixes.

The first migration enables `vector`; managed service permissions must allow it or a
DB administrator must enable it. Downgrade intentionally leaves the shared extension
installed. Never run drop_all, volume deletion or database resets to fix deployment.
There is no automatic create_all. The single-instance test deployment explicitly opts
into startup migrations with `RUN_DATABASE_MIGRATIONS=true` and `python -m app.start`.
Production deployments should use a dedicated release migration job.

For new models: `alembic revision --autogenerate -m "describe change"`, inspect and
edit the result, test upgrade against a disposable DB and representative existing data.
Update the readiness schema revision alongside schema-compatible application releases.
Future rolling releases need an explicit compatible revision policy.

## Production gate

Do not deploy until earlier phase tests pass. Verify student, contributor, admin,
RAG and inbox workflows through the deployed HTTPS endpoints; verify private storage
and database persistence after redeploy/restart. Exercise token expiry, revocation,
provider outage, failed jobs and backup restore. Record version and results.

## Private initial administrator on a phone

The deployed setup helper is off by default. Enter `INITIAL_ADMIN_SETUP=true`,
`INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_NAME` and a strong `INITIAL_ADMIN_PASSWORD` privately
in the Render API service environment. Deploy once, confirm the generic success log,
then remove all four setup values. The helper creates only the first administrator,
never promotes an existing public account and never resets an existing administrator.
Do not send the password in chat or commit it. See authentication.md for the private CLI alternative.

## Proposed document worker (requires purchase approval)

| Setting | Prepared value |
|---|---|
| Service type / name | Background worker / edumind-knowledge-worker |
| Repository / branch | sumiEmpire001/edumind-ai / main |
| Region / instances | Frankfurt / one |
| Runtime | Docker |
| Dockerfile / build context | backend/Dockerfile / backend |
| Docker command | python -m app.knowledge.worker |
| Compute | Starter, listed at $7/month; verify account quote before purchase |
| Auto deploy | Off during activation |
| Database migration | API/release operation only; worker never migrates |

Use the existing API's private database configuration, production CORS/settings and
Gemini configuration, plus the same scoped private storage credentials on both services.
The worker does not need INITIAL_ADMIN_* setup values. Do not expose database ingress or
publish object URLs. Keep RAG_ENABLED=false until hosted document approval, extraction,
embedding, retrieval, removal and re-indexing checks pass. Storage and AI usage charges
are separate from the worker's base price. No worker was created by preparing this table.
