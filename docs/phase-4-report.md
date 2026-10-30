# Phase 4 development report

Date: 30 October 2026. Status: implementation complete; PostgreSQL/browser CI pending.

## Delivered

- Owner-only conversation creation, listing, rename and soft removal with pagination.
- Durable user/assistant messages, follow-up context and request status/history.
- Conversation-row locking, request UUID/hash protection, frozen replay results,
  pending-request deadlines and late-answer identity/deletion checks.
- Async provider contract; normal startup is explicitly unconfigured. No live Gemini
  calls, credentials or fake academic answers are introduced in product code.
- Isolated scripted provider and guarded browser fixture factory under backend/tests.
- Responsive study-chat route/sidebar, saved history, question composer, context-aware
  follow-ups, request recovery, copy controls and safe rich answer rendering.
- Markdown/GFM/code/math rendering with raw HTML and remote images disabled, untrusted
  KaTeX commands rejected, bounded rendering and escaped plain-text fallback.
- Additive Alembic migration, audit events, write limits, environment examples and guide.

## Files

Backend: app/ai, models/chat.py, schemas/chat.py, services/chat.py, api/chat.py,
0003_conversations migration, configuration/readiness and tests/test_chat.py.
Frontend: chat API/renderer/copy components, pages/Chat.tsx, authenticated API transport,
workspace navigation/overview, lazy route boundary, styles and unit/browser tests.
Documentation: docs/conversations.md and this report. Existing auth browser helpers
are shared rather than reimplemented.

## Evidence so far

The full backend regression suite passed locally: 85 passed, six PostgreSQL checks skipped
(including the two new chat concurrency checks). The new chat subset passed 26 tests.
42 frontend tests passed locally, including safe math/Markdown, copy errors, draft/request
recovery and unavailable states. Lint/TypeScript/build passed. A transitive math renderer
advisory was resolved by pinning all instances to the patched direct version; npm audit
then reported zero vulnerabilities. Full backend regression and browser verification
will run on CI before this phase is marked verified.

## Phase boundary and limits

Live Gemini answers are Phase 5. Normal runtime clearly disables generation until a real
provider is configured; scripted fixture answers exist only in isolated tests and are
labelled in the UI. Approved knowledge/source attribution is Phase 8, so no citations
or school-specific claims are fabricated. Removal is soft deletion, not physical erasure.
Clipboard behavior depends on browser permission and has an explicit fallback.

Phase 4 is stacked on Phase 3 PR #2 while earlier PRs remain open. Integrate the branches
in phase order. No merge, production deployment, real academic corpus or real account
was created. Retention/permanent erasure, load, real devices and production operations
remain later verification gates.
