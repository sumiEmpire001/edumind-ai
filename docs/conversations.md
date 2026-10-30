# Phase 4 student conversations

## Scope

Private saved conversations, follow-up context, copy controls, safe Markdown/math/code
formatting and a responsive chat workspace. Gemini is Phase 5. Approved document retrieval
and real source references are Phase 8. This phase does not claim live AI question answering.

The normal app factory uses UnconfiguredProvider: users can create/rename/remove personal
conversations, but the composer explains that AI answers are not connected and is disabled.
Direct answer requests return 503 without storing an unsent question or inventing a reply.
Existing cached requests remain recoverable even if no provider is currently available.

## Provider/test boundary

app/ai/provider.py defines a small async protocol and typed failures. No Gemini SDK,
API key, network provider or automatic retry is introduced early. Test providers must
honor cancellation. Configurable generation timeout defaults to 20 seconds.

The deterministic fixture lives exclusively in backend/tests/fake_academic.py. It is
not copied into the production Docker image. create_app rejects provider injection
outside APP_ENV=test. The separate tests.e2e_app factory additionally requires matching
DATABASE_URL/TEST_DATABASE_URL and a database name ending in _test. No HTTP setting can
enable test responses. Every fixture response carries verification provenance, and the
browser displays a prominent scripted-test warning. These answers are not academic advice.

Phase 5 can add a real provider factory/adapter without changing conversation ownership,
storage or idempotency. It must implement academic prompting, Gemini credentials,
transient retries/backoff and real-provider reliability/quality verification.

## API

All routes require the live Bearer session; ownership is enforced by the backend.
Administrator/contributor roles do not grant access to another user's private history.
Foreign and missing conversations both return 404.

| Method and /api/v1 route | Behavior |
|---|---|
| GET /chat/capabilities | Provider availability, explicit mode, timeout budget |
| GET /conversations | Owner-only history; offset/limit pagination (default 30, max 100) |
| POST /conversations | client_id UUID; idempotent empty conversation creation |
| GET /conversations/{id} | Latest 50 messages; before_sequence/limit for older pages; request states |
| PATCH /conversations/{id} | Validated title, max 80 characters; preserves manual titles |
| DELETE /conversations/{id} | Owner-only soft removal; repeat calls by owner are idempotent |
| POST /conversations/{id}/messages | request_id UUID and content (1–4000 characters); bounded answer flow |

Successful new answers return 201; completed replays return 200; an in-flight duplicate
returns 202 with Retry-After. Different overlapping questions in one conversation return
409. Typed failures return appropriate 429/502/503/504 with sanitized request state;
raw provider error text is never persisted or returned. Invalid input/role injection
returns 422. CHAT_USER_LIMIT defaults to 20 write requests/minute/user using the existing
durable database quota mechanism. Cross-origin DELETE is explicitly permitted in CORS.

## Persistence and idempotency

0003_conversations adds conversations, chat_requests and messages. Existing identity
and academic data are preserved; startup does not create/reset tables. The migration
refuses a destructive downgrade. Readiness expects the new schema revision.

A client-generated request UUID and content hash identify a question. The conversation
row is locked while recording the request and user message. Only one request per
conversation can be active; sequences and role/request pairs have unique constraints.
A composite foreign key prevents a message from referencing another conversation's
request. The short transaction commits BEFORE awaiting the provider, releasing DB
connections. Completion locks the conversation again and rechecks ownership, deletion,
identity/session state and the request deadline before saving an assistant message.

Retrying a successful UUID recovers the exact saved result without invoking generation.
Reusing it with different content/conversation returns 409. Pending duplicates do not
invoke the provider. Failed results are frozen, not auto-retried. An interrupted/crashed
request expires after its generation budget plus ten seconds and fails closed; another
question can then proceed. A late answer cannot overwrite that outcome.

The server cannot guarantee recovery of an external-provider result/charge if the process
crashes before saving it. It deliberately does not regenerate an ambiguous/expired UUID.
Phase 5 must preserve this policy when adding external calls and safe transient retries.

The frontend retains the request UUID and draft across an unknown response outcome in
the current page. An explicit retry of the same question uses that UUID. A lost response
that was saved server-side is recovered through history and shown as recovered, rather
than falsely reporting a total failure. Drafts/request IDs are not persisted to browser
storage and do not survive a page reload. Reload recovers server-saved history instead.

## Context and history

All messages remain paginated in personal history. Generation uses only completed
user/assistant pairs from the same conversation plus the current question. At most the
latest 20 prior messages are considered, bounded by CHAT_CONTEXT_CHARACTERS (default
24000). Whole pairs are preserved; failed/pending turns and other conversations never
enter that context. Oversized/empty answers fail rather than creating a fake response.

Message bodies are not logged or included in audit records. Audit events record actions,
actor, target and request IDs. Conversation titles are a local excerpt of the first
question unless the user chose a title; no model invents title metadata.

Removal is a soft deletion: the conversation disappears from the owner's API/UI, and
an in-flight answer is discarded. It is not physical erasure and no restore UI is added.
Private retention, recovery and authorized permanent-erasure policies remain production
hardening work; backups may still contain removed messages. The removal confirmation
accurately describes removal from the workspace rather than promising secure erasure.

## Rendering and copying

The chat route and math/Markdown dependencies are lazy-loaded. React Markdown uses
skipHtml, an HTTP(S)-only link policy, isolated external links, and no remote images.
No rehype-raw is installed. KaTeX uses trust=false, bounded expansion/size and safe
error rendering. A formatting boundary falls back to escaped plain text if rendering
fails. GFM tables, headings, lists, code blocks and inline/display equations are supported.
Math fonts are local bundled assets; no third-party font/image request is needed.

Questions are rendered as text. Copy buttons write the exact question/answer/code text
using the browser clipboard API and report success only after it succeeds. If browser
permissions deny copying, users see a clear manual-copy fallback. No clipboard read or
background write is performed by product code.

The initial dependency audit found an older vulnerable KaTeX version nested beneath
math plugins. package.json overrides all KaTeX instances to the patched direct dependency;
installation, rendering tests and audit are rerun rather than ignoring the advisory.

## Verification

Unit/component tests cover owner isolation, CRUD, idempotency, context, frozen failures,
timeout/empty/rate-limited/provider errors, stale-request recovery, safe rendering,
copy permission failures, UI/API errors and the honest unconfigured state.
PostgreSQL tests additionally exercise concurrent duplicate submissions and removal
while generation is in flight. Alembic checks metadata drift and preserves an existing
data probe. The CI browser server uses explicit test fixtures and real PostgreSQL/API
persistence; it does not pretend to be Gemini.

Chromium/mobile WebKit cases cover the complete conversation/follow-up/rename/remove
flow, math/code rendering, lost-response recovery and replay without duplicates, private
history isolation, and disabled answers when capabilities are unavailable. Production
Gemini quality, approved RAG citations, real-device/browser-domain deployment, retention
and operational load remain later phase gates.
