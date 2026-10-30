# Roadmap and verification gates

Work on one phase at a time. Stop at an unmet gate and record evidence; compilation
alone never satisfies a functional gate. Phases 1 and 2 are verified. Phase 2 is delivered in PR #1; Phase 3 has not started.

| Phase | Deliverable | Required gate before next phase |
|---|---|---|
| 1 Foundation | Monorepo, environments, database, migrations, health, CI | Actual DB migration/vector test, API tests, frontend checks/build, GitHub source and CI confirmed |
| 2 Backend stability | Auth, sessions, user controls, RBAC, logs, limits | Register/login/logout, invalid/expired/replayed tokens, inactive user and role restrictions |
| 3 Frontend foundation | Landing, register/login, routing, API | Auth integration, protected routes, errors and mobile navigation |
| 4 Student experience | Chat interface, history, follow-up, copy, equations | Ownership and conversation tests; provider contract uses test adapter until Phase 5 |
| 5 Gemini | Provider adapter, retries, budgets, formatting | Success, context, timeout, 429, 503, empty result, idempotency; real smoke test with secret |
| 6 Contributors | Applications, private upload, history | File validation/duplicates, pending state, tracking and contributor restrictions |
| 7 Administration | User/application review, preview, approvals, audit | Admin-only decisions, rejection reasons, safe authorized preview and immutable review audit |
| 8 Knowledge engine | Extraction, embeddings, chunk retrieval, sources | Real vector retrieval, pending/rejected exclusion, failed processing, revoke/delete, injection tests |
| 9 Local inbox | Watcher, journal, HTTPS submission | Partial copy, crash/restart, retry, duplicates, revoked credential, PENDING enforcement |
| 10 QA | Full student/contributor/admin workflows and load/security checks | Browser E2E on mobile/desktop, resilience, security and RAG evaluation gates |
| 11 Deployment | GitHub CI, Vercel, API/worker, managed DB, object storage | Local gates passed first; production auth/AI/storage workflows, backups and HTTPS |
| 12 Stabilization | Audits, fixes, documentation | Production readiness review and explicit remaining-risk register |

Deferred: public API products, native mobile app, institutional tenancy, billing,
recommendations, additional AI providers and advanced analytics. Do not implement now.

First milestone: reproducible foundation with meaningful checks. Phase 2 cannot start
while Phase 1 database or source-control verification is incomplete.
