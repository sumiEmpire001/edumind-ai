# Roadmap and verification gates

The user approved implementing the remaining phases together. Keep each functional gate
explicit: compilation alone never satisfies a gate. Phases 1–5 have verification evidence,
including hosted Gemini chat. Phases 6–12 have implementation and automated checks; hosted
activation gates remain tracked in final-readiness.md. Do not mark the whole platform
production-ready until those checks are complete.

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

## Completion audit

| Scope | State | Outstanding evidence |
|---|---|---|
| Phases 1–5 | Implemented, CI verified, hosted core flows verified | Full deployed browser coverage remains in QA |
| Phases 6–8 | Implemented, automated workflow checks passed | Real private storage, worker, administrator and hosted document/RAG flows |
| Phase 9 | Implemented, Linux/Windows CI verified | User's actual Windows folder and real scoped credential |
| Phase 10 | Regression suites and isolated restore/concurrency/retrieval rehearsals passed | Human real-model evaluation, full hosted browser/load assessment |
| Phase 11 | Core frontend/API/database deployed | Hosted document activation, hosted backup restore, automatic Vercel source integration |
| Phase 12 | Code fixes, audits and operations documentation present | Final sign-off after the remaining gates |

The user paused paid worker provisioning. Complete available isolated verification first;
do not replace missing hosted evidence with a claim of full roadmap completion. See
[release rehearsals](release-rehearsals.md) and [remaining gates](final-readiness.md).

## Studio extension

The additional ChatGPT-style document request is implemented separately from knowledge
processing: saved outlines, sequential section generation with recovery, editing and
expansion, report/answer/conversation PDF export, and private personal image/text context.
See [the idea](studio-plan.md) and [release evidence](studio-report.md).

Text drafting and PDF exports use the existing API without a paid worker. Personal
attachments remain unavailable on the hosted app until its private storage credential is
configured. Image generation is disabled. These new features do not close the original
administrator, reviewed knowledge, worker, hosted restore or Windows-folder gates above.

