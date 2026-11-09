# EduMind release assessment and remaining activation gates

Status: final-phase implementation and automated verification passed. Hosted activation
remains incomplete. Do not label the entire platform production-ready until every hosted
gate below has evidence.

## Completed evidence

- Studio extension PRs #8–#11 are merged. API release
  f304e61d1f73e600646933b81f5699ba2bf49ea7 is deployed as Render
  dep-dbijnu5g1s2s73denkj0 (live after private-storage activation).
  Vercel dpl_38PqawLKe8e2SroV9mPmWQcwxUfY
  is READY on frontend release 35bd6f638912a82b07400f0823f0c5e4b0191b54.
  GitHub run 41146020236 passed all jobs after run 41144322302 passed
  165 PostgreSQL backend tests, 50 frontend
  tests, 30 desktop/mobile browser cases, audits and both inbox platforms. See
  [Studio release evidence](studio-report.md) for deployment verification and limits.
  Personal PNG/JPEG/TXT uploads and private image previews are live and verified through
  the public app origin, including pending recovery, limits, invalid images, anonymous
  and wrong-conversation access rejection, removal and private-object cleanup.
  Hosted image understanding remains unverified after Gemini quota errors.
  Image generation is disabled.
  A hosted 11,400-word synthetic draft exported as 31 actual, nonempty PDF pages,
  and a short live Gemini answer succeeded. Long AI report generation has a separate
  hosted verification gate: the final attempt returned Gemini HTTP 429 (quota/rate limit).
  No billing was enabled. See the Studio report for the exact verified scope.
  This extension does not close the remaining hosted gates below.

- Follow-up QA PR #7 is merged (4ab6333f465c2b89524b94df02d2993c12277174).
  GitHub run 41134952520 passed all jobs: 144 PostgreSQL backend tests without skips,
  45 frontend tests, 26 same-origin desktop/mobile browser tests, audits and 11 inbox
  tests on each OS. Isolated database/object restore, 240-request concurrent-user
  rehearsal and controlled vector retrieval passed. These do not replace hosted restore,
  actual Gemini embedding evaluation or human academic review. See release-rehearsals.md.
  The rehearsal also corrected Alembic test-schema isolation and found/fixed browser
  same-origin CSRF recovery without relaxing write-request checks.
- Render deploy dep-dbih8359fdbs73dlgdag is live on release
  4ab6333f465c2b89524b94df02d2993c12277174. A fresh hosted browser check confirmed that
  /app/account redirects a signed-out visitor to /login after the session fix.
  The Vercel frontend build is unchanged; only the API required redeployment.

- Combined application release 6e8385e656fba2ea1687083b857e667ace1322b5 is live.
  Render deploy dep-dbig3pui0phs739cm7mg is live; Vercel deployment
  dpl_AYquXKpa5GvqL7TobLbHfdsxB2VY is READY on the existing public frontend alias.
  This deploys the implementation; it does not activate unavailable storage/RAG.
- Post-release frontend-origin HTTP verification passed registration, login, refresh,
  student identity, contributor application/persistence, conversation creation/persistence,
  an actual Gemini answer, logout and access-token revocation. Student admin reads and
  inbox credential minting returned 403. Storage/RAG capabilities remained correctly off.
  Both health endpoints returned 200. The deployed landing page was checked in a browser.
  Full hosted role/browser/RAG verification remains a separate gate.
- Phases 6-8 are in PR #5. GitHub run 41121122221 passed backend, frontend and browser jobs
  after the HNSW metadata and browser-navigation fixes.
- Contributor/admin workflows, extraction, private-object adapters, durable processing,
  768-dimensional vectors, source eligibility checks, versioning and source persistence
  are implemented. Pending/rejected/failed/removed/old versions cannot be retrieved.
- Phase 9 adds a separate Windows-compatible local service with hashed, scoped, expiring,
  revocable inbox credentials and durable local retries/recovery. Every upload stays pending.
- Final GitHub run 41124969741 passed every job: backend PostgreSQL tests, 45 frontend
  unit tests, 26 desktop Chromium/mobile WebKit browser cases, dependency audits, and
  11 local-inbox cases on both Linux and Windows. The backend suite collects 130 tests.
- The mobile route-focus regression is fixed; actual password change and re-login pass.
- Office metadata is retained only when supplied, and PowerPoint citations follow
  presentation slide order. Private first-administrator setup is disabled by default.
- No Gemini/storage key or real credential is committed; examples contain empty placeholders.

## Remaining hosted gates

1. The Render API's scoped private-store credential is configured and personal upload/
   preview/removal passed on 31 October 2026. The existing edumind-knowledge store remains
   private. Configure the same scoped storage access on a worker only after that service
   is separately approved and provisioned. Do not use public object URLs.
2. Approve and provision a dedicated worker service. Render's Starter worker is listed at
   $7/month on https://render.com/pricing; billing and plan availability must be checked
   in the account before purchase. No paid worker has been created or approved.
3. Configure a real administrator through private bootstrap. Verified source and additive
   migrations are deployed; readiness confirms the required schema revision. A real
   administrator email/password is not guessed or created.
4. Verify private upload/preview, approval/rejection, extraction, live embeddings, vector
   retrieval, citations, source removal and re-indexing on the hosted system. Only then
   enable RAG_ENABLED. It remains false until evidence supports activation.
5. Create/revoke a real scoped inbox credential and test the local service on the user's
   Windows computer. Code/automated Windows tests do not prove access to their actual folder.
6. Run the complete deployed frontend/browser workflows, including refresh cookies and
   mobile navigation. Run a backup-and-restore exercise with representative data.
7. Connect Vercel's GitHub integration for automatic source-based deployments. Current
   deployment uses a source snapshot; GitHub remains the canonical source repository.

## Security/operations assessment

Use HTTPS frontend/API, HttpOnly secure refresh cookies, backend role checks, CSRF origin
validation, Argon2id, short access-token lifetimes, rotating/revocable sessions and hashed
inbox tokens. Never permit public registration as admin. Inbox credentials authorize only
pending uploads, never reviews or reads. Private files are reference data, not instructions.

Parser workers need CPU/memory limits and malware/quarantine assessment before opening
contributions broadly. Extraction supports text PDFs and bounded Office ZIPs; scanned PDFs
need OCR. AI accuracy and retrieval thresholds need human assessment across disciplines.
Citations identify supplied references; they do not mathematically verify generated answers.

The test API/database use free hosting. The database expires 29 November 2026. Cold starts,
connection limits, shared-ingress IP limits and expired test resources preclude a broad
production reliability claim. Establish paid persistent plans, backups, restore verification,
alerts, retention/physical deletion and an incident/credential-rotation process before launch.

Source removal is soft deactivation. Private objects and historical referenced chunks remain
for source integrity until a separate retention/erasure policy is implemented. S3/database
partial failures can leave private orphan objects requiring reconciliation. Read/write storage
credentials must be confined to this store/bucket, never to an entire cloud account.

No public API/mobile app/subscription/institutional integration or other deferred feature
has been added. Finalization means meeting the agreed workflows, not hiding unfinished gates.
