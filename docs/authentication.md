# Phase 2 authentication and backend operations

## Scope

Backend accounts, session management, role enforcement, private administrator bootstrap,
durable authentication rate limits, audit events, and database failure handling.
Frontend forms arrive in Phase 3. Contributor applications/review dashboards, document
uploads and Gemini are not implemented in this phase.

## API contract

All endpoints use /api/v1. User responses never contain password or session hashes.
Registration normalizes email case and creates a student. Extra input fields are rejected.
Passwords accept 15–128 characters (spaces and Unicode allowed); passwords are not trimmed.

| Method and route | Authentication and behavior |
|---|---|
| POST /auth/register | Exact allowed Origin, registration quota; email/password/full_name; 201 user |
| POST /auth/login | Exact allowed Origin, IP and normalized-account quotas; 200 token bundle and cookies |
| GET /auth/csrf | Allowed Origin and current refresh/CSRF cookies; returns session-bound CSRF value |
| POST /auth/refresh | Allowed Origin, refresh/CSRF cookies, X-CSRF-Token; rotates token |
| POST /auth/logout | Allowed Origin; valid session requires X-CSRF-Token; revokes session and clears cookies |
| POST /auth/logout-all | Allowed Origin and Bearer access token; revokes every session |
| POST /auth/password | Allowed Origin and Bearer; current_password/new_password; invalidates all sessions |
| GET /users/me | Bearer access token; current account details |
| GET /admin/users | Admin Bearer; paginated users (offset, limit 1–100) |
| PATCH /admin/users/{id} | Admin Bearer; student/contributor role or is_active; revokes affected sessions |

Registration returns 409 on conflicting details. Login uses the same 401 response for
unknown, inactive and incorrect-password accounts. Missing/expired/revoked credentials
return 401; inadequate roles/origin/CSRF return 403; quotas return 429 with Retry-After.
Validation returns 422 without echoing input. Bodies above 16 KiB (including chunked)
return 413. Database failures return generic 503; request IDs connect responses to logs.
The body limit applies to current APIs and must be revised deliberately for Phase 6 uploads.

## Tokens, CSRF and cookies

Access tokens: HS256 JWT, 10 minutes by default (1–30 configurable), issuer/audience,
subject, session ID, issued/not-before/expiry and access-type validation. The backend
also reads the live session and user on every protected request. Role is never trusted
from a JWT claim. Expiration, deactivation and revocation take effect server-side.

Refresh tokens: 48 cryptographically random bytes encoded URL-safe. Only SHA-256 hashes
are persisted. A family/session has an absolute 14-day expiry by default (1–30 configurable).
Every refresh consumes the old token and stores a new hash transactionally. Used hashes
are retained for replay detection; reuse revokes the whole family, including its access
tokens. Locks use user -> session ordering to coordinate refresh with account changes.

Clients must serialize refreshes (including across tabs); never blindly retry a refresh
after a lost response. Reusing a consumed token fails closed and requires login again.
This intentional policy prioritizes replay detection over silent retry convenience.

Refresh and CSRF cookies are HttpOnly, host-only, scoped to /api/v1/auth, and SameSite=Lax
by default. Production uses Secure and __Secure- cookie names. No cookie Domain is set.
The CSRF value is also returned in a successful login/refresh response; keep it and the
access JWT in browser memory. Never use localStorage/sessionStorage for credentials.
After reload, call GET /auth/csrf with credentials and Origin, then POST /auth/refresh with
the returned X-CSRF-Token. The server checks the allowed Origin and matches the header,
cookie and session hash before cookie-authenticated writes. Both cookies are HttpOnly;
frontend JavaScript does not read document.cookie.

Frontend requests to auth use credentials: include. Browser fetch supplies Origin;
CLI tests must set it explicitly. On production use custom frontend/API domains under
the same site where possible. Unrelated vercel.app and backend domains require
COOKIE_SAMESITE=none (production HTTPS only), and browsers may still block third-party
cookies. Test this arrangement before Phase 11; no cross-site compatibility is claimed yet.
Cookie transport Max-Age is renewed on refresh, but the absolute server session expiry
is never extended. The client must handle 401 after expiry by discarding its in-memory state.

## Secrets and local development

Generate an independent JWT_SECRET using:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put its output in backend/.env. Do not send it in chat, commit it, or put it in Vite variables.
The example placeholder is intentionally rejected. Production requires verified DB TLS
and explicit HTTPS CORS origins. Changing the signing key invalidates access tokens and
changes the rate-limit HMAC key; rotate it in a coordinated maintenance release.

Apply migrations before starting the API:

```sh
cd backend
alembic upgrade head
uvicorn app.main:create_app --factory --reload --port 8000 --no-access-log
```

Readiness now expects revision 0002_identity. Startup never creates/resets tables.
The new migration adds users, auth_sessions, refresh_tokens, audit_logs and
rate_limit_buckets without replacing existing data. The downgrade intentionally refuses
to drop domain data. Use reviewed forward migrations or a validated recovery plan.

## Private administrator bootstrap

On a trusted backend machine with configured environment and migrated DB:

```sh
python -m app.auth.bootstrap
```

Enter email, full name and a password twice. getpass hides input; passwords are never CLI
arguments or environment variables. The command creates a NEW admin and audit event.
It never promotes an existing public account, even if its email matches. PostgreSQL
advisory locking serializes bootstrap attempts. Choose a new email if that address
already exists; handle ownership/identity reconciliation through private maintenance.
Additional admin accounts may be created using the same private process.

Public routes cannot create/promote admins or edit/deactivate any admin account. This
protects self-access and the final administrator. Sensitive admin-account recovery or
removal requires a reviewed private maintenance process; no recovery endpoint exists.
All target-role/status changes revoke target sessions so users must sign in again.

## Rate limits and resource bounds

Database UPSERT counters commit independently of request business transactions, so
failed logins consume quota and multiple API replicas share counts. Buckets use HMAC
keys rather than storing raw email/IP. Fixed windows allow boundary bursts; load testing
and distributed edge limits remain part of production hardening.

| Setting | Default |
|---|---|
| LOGIN_IP_LIMIT | 20 / minute |
| LOGIN_ACCOUNT_LIMIT | 5 / minute |
| REGISTER_IP_LIMIT | 5 / hour |
| AUTH_IP_LIMIT | 60 / minute on auth routes |
| Password changes | 5 / hour per user |
| Admin reads / writes | 120 / 30 per minute per admin |
| Argon2 work | At most 4 concurrent operations per API process; busy returns 503 Retry-After |

IP derives from the ASGI client. Configure Uvicorn's FORWARDED_ALLOW_IPS only for the
hosting platform's trusted proxies; never trust arbitrary X-Forwarded-For headers or
set all proxies trusted without an actual network boundary. This needs production
verification before relying on client-IP limits behind the cloud proxy.

Clean expired rate buckets in bounded batches:

```sh
python -m app.auth.maintenance
```

One call removes at most 1000 expired buckets. Run it regularly through a platform job;
no task is scheduled by Phase 2. Keep used refresh verifiers until session expiry.
Define and implement session/audit retention before production, respecting recovery
and replay-detection needs. Audit records have no public modification endpoints;
production DB privilege separation and retention policies are still required.

## Verification and limits

Local API tests use an isolated in-memory SQLite database when TEST_DATABASE_URL is
absent; this is a test adapter only. App Settings reject SQLite for runtime use.
With TEST_DATABASE_URL, the suite creates a unique PostgreSQL schema, applies real
migrations, runs the same API flows, and removes only its own test schema afterward.
The provided TEST_DATABASE_URL must point to a disposable database. Concurrent refresh,
atomic rate limiting and private bootstrap checks require PostgreSQL and explicitly
skip otherwise. CI provides PostgreSQL 16/pgvector and runs all tests.

No real production account or admin password is created by CI. No cloud deployment,
frontend login flow, browser cookie validation, MFA, email verification, password reset,
or production load test is claimed here. Account recovery/email delivery would require
an additional scoped design before public launch.

## References consulted 2026-10-30

- https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
