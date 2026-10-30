# EduMind AI architecture proposal

## Scope and approach

A modular monolith for the API, a separately deployed ingestion worker, a React SPA,
and a separate local inbox process. Avoid microservices and Redis initially.
PostgreSQL is the source of truth for users, conversations, review decisions,
processing jobs, and searchable vectors. Private object storage holds originals.
Phase 1 foundation and Phase 2 authentication modules are implemented; see their reports for verification.

## Stack and deployment arrangement

| Concern | Choice | Deployment |
|---|---|---|
| Frontend | React, TypeScript, Vite, Router, modern CSS | Vercel, frontend/ root, dist/ output |
| API | Python 3.12, FastAPI, SQLAlchemy, Pydantic | Render Docker web service |
| Jobs | PostgreSQL durable queue with leases | Separate Render background worker |
| Database | PostgreSQL 16 with pgvector | Managed PostgreSQL; private network and verified TLS |
| Files | S3-compatible private object storage | Provider selected before Phase 6 |
| AI | Google GenAI SDK behind a provider protocol | Backend only; credentials in secret manager |
| Inbox | Python process with local SQLite journal | Administrator's Windows computer |
| Tests | pytest, Ruff, Vitest, Testing Library, ESLint, TypeScript | Local checks and GitHub Actions |

Render is a proposal, not a provisioned resource or pricing commitment. Verify costs,
region, backups, storage provider, and production resource limits in Phase 11.
Do not deploy backend document processing into the Vercel frontend runtime.

## Request and retrieval boundaries

The browser talks only to HTTPS API endpoints. The API authenticates every protected
request and enforces roles and resource ownership. It reads private documents from
storage only after authorization. Provider credentials never reach the browser.

AI flow: authenticated question -> persist idempotent request -> retrieve approved,
ready, active knowledge -> provider -> validate answer -> persist answer and exact
source references -> respond. Preserve conversation ownership for follow-ups.
Retrieved material is delimited as untrusted reference data, never system instructions.
Source labels originate from retrieved chunk IDs, never model-generated citations.
General knowledge answers must be distinguished from school-specific verified facts.
The provider abstraction covers generation and embeddings separately; future providers
can be added without changing API routes. Model IDs and dimensions are versioned
configuration selected and tested during Phase 5/8, not guessed now.

## Proposed normalized schema (future phases)

All domain entities use UUID primary keys, UTC timestamps, explicit foreign keys,
indexed ownership/status fields, and constrained state transitions.

| Table | Relationships and constraints |
|---|---|
| users | Unique normalized email, password hash, role, active flag; no public admin registration |
| contributor_applications | Applicant and reviewer FKs; pending/approved/rejected with reason |
| courses | Unique course code within institution context; discipline and title |
| conversations | Owner FK, title, timestamps; ownership checked on every operation |
| messages | Conversation FK, role, content, request id; unique conversation/request key |
| knowledge_submissions | Uploader/reviewer FKs, SHA-256, private storage key, metadata, review status/reason |
| knowledge_documents | Submission FK, logical document/version, approval link, active flag, processing state |
| knowledge_chunks | Document version FK, ordinal, content, page/section, embedding model/dimension |
| message_sources | Message/chunk FKs, citation ordinal, source snapshot for historical integrity |
| processing_jobs | Document version FK, unique operation key, attempts, lease, retry time, sanitized error |
| audit_logs | Actor FK, action, target, request ID, timestamp; sanitized immutable event records |
| auth_sessions / refresh_tokens | Session family, user FK, absolute expiry/revocation and hashed single-use refresh verifiers |
| service_credentials | Hashed revocable inbox credential, owner FK, scope, expiry, last used |

Schema changes are introduced with owning features. Phase 1 enables vector; Phase 2 adds identity, sessions, audit and rate limits.
Academic domain tables remain deferred until their owning phases.
Duplicate uploads use content hashes and idempotency keys. New versions cannot silently
replace active content; supersession/deactivation and retrieval exclusion are transactional.
Embedding model changes require a new versioned index and successful re-indexing before activation.

## Document state machine

Review: PENDING -> APPROVED or REJECTED; rejecting requires a reason.
Processing: NOT_STARTED -> QUEUED -> PROCESSING -> READY or FAILED.
Only approved work may be queued. Approval and durable job creation share a transaction.
Worker rechecks approval, deletion state, and version before processing and activation.
A lease and unique operation key prevent duplicate activation after retries/crashes.
Chunks become available atomically after successful extraction, embeddings, and persistence.
Retrieval always joins approval=APPROVED, processing=READY, active=true, not deleted.
Pending, rejected, failed, revoked, deleted and superseded versions are excluded.

## Local knowledge inbox (Phase 9)

Folders: incoming/, processing/, completed/, failed/. The watcher is a separate process,
never code inside Vercel. Wait for stable size/mtime over multiple polls, minimum age,
and successful exclusive read where supported. Copy into a private staging location,
hash the completed bytes and validate the signature, size and allowed format.
A durable local journal stores hashes, submission IDs, attempts, and folder transitions.
HTTPS submissions use an expiring, revocable submit-only credential held in the OS
credential store. Backend repeats validation and records the responsible administrator.
Every submission starts PENDING; no approval scope is granted to the watcher.
Use an idempotency key so a lost network response can be safely retried. Retry timeouts,
429 and transient 5xx with bounded exponential backoff/jitter; quarantine terminal failures.
A completed folder means received by backend, not approved or indexed. Recovery resumes
journaled work after reboot. Log events without credentials or document text.

## Security and reliability decisions

Phase 2: Argon2id hashes; short-lived signed access tokens in browser memory; rotating,
revocable refresh sessions in Secure HttpOnly cookies. Recheck active user and role on
protected requests, protect cookie endpoints against CSRF and validate Origin. Separate
frontend/API domains may require same-site custom domains or carefully tested SameSite
settings. Logout revokes refresh sessions and clears cookies; privilege changes invalidate
sessions. Login/upload/AI limits must work across API instances, with PostgreSQL-backed
quotas initially. CORS is not authorization.

Uploads: allowlist formats, extension/MIME/signature agreement, bounded multipart bodies,
archive expansion limits for DOCX/PPTX, safe extraction subprocess with CPU/memory/time
limits and no network, malware scanning/quarantine policy before preview or activation.
Scanned PDFs need OCR as a separately assessed capability. Do not invent missing author,
institution or other metadata. Preserve admin corrections and extraction provenance.
Use isolated safe previews, short-lived authorization, nosniff, and restrictive CSP.

AI: bounded timeout, retry only transient failures with backoff and Retry-After, no
repeated charge after an idempotent request completes, per-user usage quotas, explicit
empty-response failure. Limit concurrent expensive work. Never log user prompts or
provider error bodies by default. Diagnostics use request/job IDs and error categories.

Backups, restore drills, retention/deletion policies, privacy notice, load tests, credential
rotation and production security review are mandatory before final readiness approval.
No production-ready claim is made by this foundation.

## Technical risks and controls

| Risk | Planned control and acceptance test |
|---|---|
| Hallucinations or incorrect calculations | Curated academic evaluation, uncertainty, citations, unit/step checks |
| Prompt injection in documents | Untrusted context, no tool privileges, malicious-document regression cases |
| Worker crashes and duplicate jobs | Leases, idempotency keys, atomic activation, crash recovery tests |
| Unsafe or scanned documents | Signature/size checks, sandboxed extraction, explicit unsupported/OCR state |
| API quota and cost spikes | User limits, bounded retries/concurrency, usage metrics and budgets |
| Embedding incompatibility | Store model/version/dimension; re-index with activation gate |
| Data loss or access leakage | Private storage, ownership/RBAC tests, backups and restore drill |
| Cross-domain auth and CORS | Explicit origins, CSRF controls, production browser tests |
| Production latency | Retrieval benchmarks, connection budgets, vector indexes after corpus measurement |

## Official references consulted 2026-10-30

- https://ai.google.dev/gemini-api/docs/libraries
- https://render.com/docs/background-workers
- https://render.com/docs/postgresql-extensions
- https://vite.dev/guide/static-deploy
