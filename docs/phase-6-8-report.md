# Connected contributor, administration and retrieval milestone

30 October 2026. Local implementation verified and published in PR #5 with user approval. Cloud CI is in progress; hosted activation has separate gates.

## Implemented

- Contributor application and administrator decisions, with session revocation on promotion.
- Contributor/admin uploads, own-submission histories, rejection reasons, and authenticated
  original-file/text previews. Only administrators review submissions.
- Strict MIME/signature checks, UTF-8 validation, Office ZIP expansion/entry limits,
  3 MB uploads, bounded extraction/chunking and content-hash duplicate protection.
- PDF, DOCX, TXT, CSV and PPTX extraction. Missing author/institution metadata stays missing;
  scanned/encrypted PDFs need separate OCR or unlocking. Office macros are rejected.
- Private S3-compatible and private Vercel Blob storage adapters, without local-disk fallback.
- Additive 0004 migration: applications, submissions, document versions, vector chunks,
  message source records and durable jobs. A 768-dimensional cosine HNSW index supports search.
- Separate worker CLI with row claims, leases, bounded attempts and administrator requeue.
  Approval queues work; only successful indexing activates a version. Failed jobs remain excluded.
- Semantic retrieval, optional discipline filtering, model/version isolation, source locations,
  and source persistence alongside answers. General knowledge is allowed when no excerpt matches.
- Documents are untrusted reference data. Source status is rechecked under document locks
  before answers persist. Removal cancels indexing leases and immediately excludes retrieval.
- Re-indexing excludes the prior version until replacement succeeds. Historical chunks remain
  for past message-source integrity; this is soft removal, not physical erasure.
- Responsive contributor/admin workspace: inbox, reviews, text preview, processing states,
  re-index/remove controls, account enable/disable and platform counts.

## Deployment arrangement

Frontend snapshot: Vercel project edumind-ai, team AnEmpire; API requests proxy through the
frontend origin to avoid relying on third-party refresh cookies. GitHub integration is not
installed in Vercel, so source snapshots are used for now. The user explicitly approved removing Vercel sign-in protection; it is now disabled.
EduMind authentication and backend role checks remain enforced. A live HTTP test through
the frontend API proxy passed registration, login, Gemini generation, conversation persistence
and logout. GitHub integration in Vercel remains unconnected.

Render backend remains on the verified Phase 5 branch until this milestone passes CI.
Its private PostgreSQL connection uses Render's documented encrypted private-network mode
with a pinned internal hostname. Other production databases retain certificate verification.

An empty private Blob store edumind-knowledge exists in AnEmpire. A scoped read/write token
must be configured on Render before uploads activate; alternatively configure an existing
private S3 bucket. Never put storage tokens in frontend variables or git.

A dedicated worker service is not yet provisioned. Render workers can require a paid plan;
no paid worker was created. The ready-to-run command is:

    python -m app.knowledge.worker

The worker uses the same DATABASE_URL, storage credentials, GEMINI_API_KEY and EMBEDDING_MODEL
as the API. Enable RAG_ENABLED only after hosted storage, embeddings and worker verification.
See docs/knowledge-operations.md. Public access, storage credentials and hosted worker
activation remain explicit gates, not completed deployment claims.

## Verification

Final local validation: 112 backend tests passed; seven PostgreSQL-only checks skipped.
45 frontend tests, lint, TypeScript and build passed. Ruff lint/format and offline
Alembic SQL generation passed. Backend dependency audit reported no known vulnerabilities. New tests
cover approval gating, roles, duplicate uploads, failed processing, preview ownership,
old versions, removal races, source persistence, application promotion and vector filtering.
GitHub CI is authoritative for PostgreSQL migrations, vector queries and browser regressions.

## Limits and follow-up

Embedding quality/cost needs evaluation on a real approved corpus. RAG is off by default.
Private documents are never used to train a provider through this application. Generation
and embedding requests do transmit selected text to Gemini; contributor terms should make
that use clear. No malware scanning or OCR service is claimed. Processing runs in a separate,
resource-bounded worker container; add antivirus/quarantine before accepting a public corpus.
Source attribution identifies retrieved references and does not prove every generated claim.
PDF/Office parsing needs further stress tests before broad public use. Storage reconciliation,
retention and physical deletion are operations follow-ups. Contributor requests are paginated
at 50; admin user management currently displays the first 100 accounts. No inbox watcher
(Phase 9), mobile app, subscriptions or other future-expansion feature is included.

Publication initially required explicit approval, which the user subsequently supplied.
PR #5 contains the source. The first PostgreSQL run passed 118 tests and found one
Alembic metadata drift: the HNSW index was declared in the migration but missing from
SQLAlchemy metadata. The model declaration is corrected; all jobs rerun on the fix.
Render remains on Phase 5 until cloud verification finishes.
