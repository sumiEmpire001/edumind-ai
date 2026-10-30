# Phase 3 frontend and browser verification

## User story

A student opens the landing page, registers, signs in, enters their protected workspace,
reloads without losing their session, manages their password, and signs out securely.
The browser talks to the real FastAPI routes and PostgreSQL; no mock login exists in
product code. Contributor/admin accounts use the same sign-in flow and show the
server-confirmed role. Their document and administration tools remain future phases.

## Pages and boundaries

| Route | Experience |
|---|---|
| / | Responsive landing page, real registration/sign-in links, approach section |
| /register | Name/email/password/confirmation form, client validation, POST registration |
| /login | Sign-in form, registration confirmation, safe errors, protected return destination |
| /app | Protected personal workspace, real account identity, clear availability of future AI tools |
| /app/account | Account details and a working password-change form |
| Other paths | Page-not-found view with a home link |

No conversational AI, contributor upload, admin review, analytics or statistics are
simulated. These belong to later phases. Sign-out explicitly closes sessions on all
devices using the existing /auth/logout-all endpoint. This is disclosed beside the
control; network failure leaves the user informed rather than claiming success.
Password changes use the backend's current-password validation and revoke all sessions.

## Session lifecycle

The typed API client sends credentials: include, bounds request/response-body time to
12 seconds, maps errors to safe messages, and respects Retry-After. It never displays
raw provider/database error bodies or logs credentials. A successful response is checked
before user data is accepted. Mutation timeouts/network failures are never auto-retried.

Access JWTs live only in the SessionClient instance in memory. Cookies stay HttpOnly.
After a reload, GET /auth/csrf retrieves the session-bound CSRF value and POST
/auth/refresh rotates the token. A shared promise coalesces bootstrap/refresh, including
React StrictMode effects. Web Locks serialize cookie-changing operations across same-origin
tabs; refresh reads current CSRF/cookies only after acquiring the lock. Lock timeout
shows a recoverable unavailable state. BroadcastChannel communicates only changed/signed-out
signals, never tokens. Epoch guards stop late responses from restoring a signed-out view.

Protected API calls renew near expiry and may retry once after a backend 401 rejection.
Other failures are surfaced. A 401 during recovery means anonymous; a service/network
failure means unavailable with a retry action, not a false successful login/logout.
Focus revalidates the account. Backend ownership/role/session checks remain the security
boundary; frontend routing is only navigation protection.

Web Locks and BroadcastChannel are feature-detected. Without Web Locks, in-tab refresh
is still coalesced but simultaneous tab refreshes can trigger the backend's intentional
fail-closed replay policy and require sign-in again. Without BroadcastChannel, other
tabs revalidate on focus/API calls instead of receiving immediate sign-out notification.
No credential is stored in localStorage/sessionStorage or broadcast in a message.

## Responsive and accessible UI

Shared CSS tokens, local system font fallbacks, no external font/image requests, visible
keyboard focus, labels, field errors, status/error announcements, skip link, descriptive
page titles and mobile navigation. Menus close on selection/Escape and return focus on
Escape. Mobile navigation is a separate collapsible layout, not a scaled desktop sidebar.
No unnecessary animation; reduced-motion preference disables smooth scrolling.

## Local configuration

Use the backend setup and JWT_SECRET instructions in README.md first. For standard
local development frontend/.env can use VITE_API_BASE_URL=http://localhost:8000 and the
backend CORS_ORIGINS must include the frontend origin (normally http://localhost:5173).
When the variable is absent in development, Vite proxies /api to 127.0.0.1:8000.
The development preview allows only Vite's default hosts plus terminal.local.

For a production build, explicitly set VITE_API_BASE_URL to the deployed HTTPS API origin.
A missing production API URL fails closed for API calls rather than treating static HTML
as a valid API. This phase does not provision Vercel or a production backend. Same-site
custom domains/secure-cookie settings still need production verification in Phase 11.

## Tests

From frontend: npm test, npm run typecheck, npm run lint, npm run build, npm audit.
The unit/component tests use explicit fixtures only in test files. They cover navigation,
forms, validation, pending submissions, safe errors, bootstrap, refresh coalescing, session
revocation signals, stale responses, storage avoidance, timeouts and lock failure.

The browser CI job provisions a disposable PostgreSQL/pgvector database, applies real
migrations, creates test-only contributor/admin fixtures, starts FastAPI and the built
Vite frontend, and runs Playwright on desktop Chromium and mobile WebKit. Browser cases
cover actual registration/sign-in/reload, concurrent tabs, sign-out/revocation, password
changes, incorrect credentials, form controls, role display, mobile layout and an injected
503 logout failure. The injected failure is test-only; product API calls are real.

To reproduce browser tests locally, use an explicitly disposable PostgreSQL database:

1. Set APP_ENV=test and DATABASE_URL and TEST_DATABASE_URL to the same disposable DB URL (database name must end in _test).
2. Set a generated JWT_SECRET and E2E_TEST_PASSWORD (test fixtures only, never production).
3. Set CORS_ORIGINS=["http://127.0.0.1:4173"] and VITE_API_BASE_URL=http://127.0.0.1:8000.
4. Use test-only quota overrides from the browser CI job to avoid throttling the test suite.
5. From backend run alembic upgrade head and PYTHONPATH=. python tests/seed_e2e.py.
   On PowerShell, set $env:PYTHONPATH="." first, then run python tests/seed_e2e.py.
6. From frontend install the official Playwright browsers with
   npx playwright install --with-deps chromium webkit, run npm run build, then npm run test:e2e.

The seeder refuses production configuration and never promotes existing accounts. Keep
its fixture password consistent if reusing a disposable test DB. No real account is
created by CI. Test credentials are generated for the job and masked in its logs.
Traces and authentication storage-state exports are disabled. Real phone testing and
production-domain cookie testing remain later verification work.
