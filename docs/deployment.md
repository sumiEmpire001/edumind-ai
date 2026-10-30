# Deployment and database operations

This is a deployment plan. No cloud services are provisioned in Phase 1.

## GitHub

Repository: https://github.com/sumiEmpire001/edumind-ai

Confirm both CI jobs pass after pushing source updates.
Use required checks and protected branches before accepting feature changes.
Review third-party Actions and pin vetted commit SHAs before production CI hardening.

## Vercel frontend (Phase 11)

Import the GitHub repository. Root directory: `frontend`. Framework: Vite.
Install: `npm ci`; build: `npm run build`; output: `dist`.
Set `VITE_API_BASE_URL` to the HTTPS backend origin and rebuild.
`frontend/vercel.json` contains the SPA fallback and basic security headers.
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

Provision a separate worker in Phase 8; no placeholder worker process exists today.
Provision private object storage before uploads in Phase 6. Store files there, never
on an ephemeral web-service disk. Keep Gemini, session-signing and storage credentials
in backend/worker environment secrets only, introduced in their owning phases.
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
There is no automatic create_all or startup migration.

For new models: `alembic revision --autogenerate -m "describe change"`, inspect and
edit the result, test upgrade against a disposable DB and representative existing data.
Update the readiness schema revision alongside schema-compatible application releases.
Future rolling releases need an explicit compatible revision policy.

## Production gate

Do not deploy until earlier phase tests pass. Verify student, contributor, admin,
RAG and inbox workflows through the deployed HTTPS endpoints; verify private storage
and database persistence after redeploy/restart. Exercise token expiry, revocation,
provider outage, failed jobs and backup restore. Record version and results.
