# Phase 2 development report

Date: 30 October 2026. Status: implemented; PostgreSQL CI verification pending.

## Scope and files

- app/auth: Argon2id/JWT helpers, live-session authorization, cookie handling,
  private admin bootstrap and bounded rate-bucket maintenance.
- app/models/identity.py and schemas/identity.py: normalized user/session/refresh,
  audit and quota tables; strictly validated request/response schemas.
- app/services/identity.py: transactional registration/login, refresh rotation,
  replay revocation, logout, password changes and admin user operations.
- app/api/auth.py and users.py: versioned REST routes with server-side permissions.
- app/security: durable distributed quotas, hashing resource limits, bounded request bodies.
- app/main.py: credentialed exact-origin CORS, safe validation/DB errors and request logs.
- alembic/versions/0002_identity.py: additive auth migration; destructive downgrade refused.
- config, env examples and dependency locks: required independent JWT secret and configurable lifetimes.
- tests/test_auth.py: positive/negative API flows and PostgreSQL concurrency/bootstrap checks.
- docs/authentication.md and README.md: API contract, setup, admin/bootstrap and operational limits.

## Security behavior

Public registration cannot choose roles. Protected requests check the live user and
server-side session. Refresh verifiers are hashed, single-use, and locked during rotation.
Replay revokes the family. Logout immediately revokes access; password and administrative
account changes revoke all affected sessions. No route can create/promote/edit admin
accounts. Origin and session-bound CSRF checks protect refresh/logout. Request validation
never echoes submitted passwords. Quotas persist on failures and share a database
across replicas. Bounded Argon2 work and request bodies protect process resources.

## Verification so far

Local: 59 tests passed, four PostgreSQL-specific checks skipped. Ruff lint/format passed;
runtime dependency audit found no known vulnerabilities. No frontend files changed.
CI will run the full suite on PostgreSQL/pgvector before this phase is declared verified.
Results will be recorded in this report after the workflow completes.

## Remaining limits

Frontend login/registration and browser cookie workflows are Phase 3. Production domains,
proxy trust, secrets, retention, recovery/email flows, load testing and deployment remain
unverified. No real account or deployment was provisioned. The Starlette HTTPX test-client
deprecation warning from Phase 1 remains; it does not fail tests.
