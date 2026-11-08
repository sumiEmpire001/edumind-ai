# EduMind knowledge API and model-development roadmap

## Release 1: curation and independent knowledge search

Implemented in this release, pending deployment. The new workspace is `/app/learning`
("Knowledge API" in navigation). It uses the existing authenticated account/session system.
It does not change account roles or resolve the pending administrator promotion.

An API is an interface, not a model. This release builds owned, reviewed knowledge and
training-ready data. It does **not** train model weights, auto-learn from every interaction,
replace Gemini chat, or certify high token throughput.

### Data paths

- Contributor/admin documents use the existing upload → administrator approval → worker
  extraction/indexing path. Search includes only active, successfully processed current
  versions of approved documents. Pending, rejected, removed and superseded content is excluded.
- Students/contributors/admins explicitly nominate general academic questions. No private
  conversations, attachments, account names or emails are automatically copied into a dataset.
- Admin writes/edits an answer and evidence reference, verifies accuracy, redacts personal
  information and confirms permission to reuse before approval. Approval requires these fields.
- Each reviewed example has a fixed `train` or `evaluation` purpose. Evaluation examples do
  not enter search or training exports. Once reviewed, the split cannot change, including after
  rejection. Normalized duplicate questions are refused. Paraphrase/topic duplication still needs
  human review: this is not a semantic deduplication guarantee.
- Admin can reject an approved example to withdraw it from subsequent search and exports.
  Previously downloaded exports must be discarded/rebuilt by the operator; revoking an example
  cannot remove it from an already trained model. Provenance remains in the audited review record.

### API contract

All routes require the existing bearer session; writes also require a trusted Origin.
No public developer API key or unauthenticated endpoint is introduced.

| Route | Access | Behavior |
| --- | --- | --- |
| `POST /api/v1/learning/examples` | Signed-in | Question plus `consent_to_share: true`; creates pending nomination, 10/hour/user |
| `GET /api/v1/learning/examples?offset=0` | Signed-in | Own suggestions; admins see review queue, 50/page |
| `POST /api/v1/admin/learning/examples/{id}/review` | Admin | Review answer, evidence, split and rights confirmation; audit event |
| `POST /api/v1/learning/query` | Signed-in | Up to 2,000 question characters; 30/min/user; up to five source excerpts |
| `GET /api/v1/admin/learning/overview` | Admin | Corpus counts and measured search observations, explicit unverified readiness gates |
| `GET /api/v1/admin/learning/dataset?split=train&offset=0&limit=500` | Admin | Reviewed examples in messages JSONL; page SHA-256, total and next offset; audited |

Search is PostgreSQL full-text lexical retrieval, with GIN indexes and parameterized queries.
It makes **no Gemini or embedding API call**. It is not semantic search, a general reasoning
model or a generated answer. Source presence does not prove correctness/relevance. The API
returns `sources_found` or `insufficient_knowledge`, clearly labelled excerpts with source IDs,
titles and locations; no invented answer when nothing matches. Source text remains untrusted
content. Current chunks are reused independent of their embedding-model ID.

The existing document worker still requires its configured embedding provider to process a
new document. This release's *query* independence does not remove that ingestion dependency.
Reviewed question/answer examples can enter search without that worker.

Dataset exports contain approved question/answer pairs only, not raw documents or transcripts.
Each page is bounded to 500 records. UI downloads the first page and reports if more remain;
operators use `next_offset` for subsequent pages. Hash covers exact UTF-8 JSONL page bytes.
There is no immutable full-dataset snapshot yet: pause reviews while assembling a multi-page
training release and record all page hashes, split counts and reviewer approval externally.

### What the dashboard measures

- Pending/rejected/approved examples, train/evaluation counts, active current document passages.
- Latest 1,000 completed searches within seven days: source-hit count and p95 search latency.
- Telemetry stores timestamp, duration and source count only, with no question/user identity.
  These are successful database-backed search completions; errors/timeouts are **not** included.
  They are not availability, answer quality, model token capacity or a load-test certificate.
- Metrics have no fixed retention cleanup job in this release. Operators should establish a
  bounded retention job before opening the API to significant traffic.

## Remaining milestones before a Gemini replacement

| Milestone | Required work and evidence | State |
| --- | --- | --- |
| 1. Owned knowledge/data foundation | Review queue, independent excerpt API, admin metrics, split JSONL export | Implemented; verify CI and deploy |
| 2. Dataset releases and evaluations | Immutable manifests; topic-level dedup; independent held-out questions, evidence/citation grading, abstention and leakage tests, subject coverage | Not implemented |
| 3. Independent inference | Select licensed open-weight model; provision GPU or inference host; integrate provider adapter behind existing chat interface; explicit context/output limits | Not configured |
| 4. Actual fine-tuning | Reviewed licensed data; offline reproducible adapter training; versioned weights, training loss and validation metrics; no training on the held-out set | Not implemented |
| 5. Controlled rollout | End-to-end accuracy/citation/safety evaluation versus Gemini; concurrent load and long-context tests; token/request limits; errors/p95/throughput/cost monitoring; admin canary switch and rollback | Not implemented |

Set numerical acceptance targets **before** running evaluation: subject-level answer accuracy,
source support, abstention on unknown questions, p95 end-to-end latency, sustained concurrent
requests, actual input/output token lengths, memory/cost budget and error rate. Compare the
same frozen evaluation set against Gemini and the candidate, with human review. Document count
and training loss alone must never turn the readiness flag green. There is intentionally no
activation control or automatic Gemini switch in release 1.

GPU provisioning, model downloads, paid training and public API credential issuance are outside
this release. Do not schedule these until the host, model licence, dataset rights and budget
are concretely selected. High traffic capacity comes from model architecture and infrastructure,
not from collecting more documents.

## Deployment and verification

1. Run full CI, including PostgreSQL/pgvector migrations and learning integration tests.
2. Back up the database, then deploy backend migration `0007_learning` before the new frontend.
   The live Render service currently follows `phase-5/gemini` with auto-deploy off; merging main
   alone does not update it. Do not deploy only the frontend against the old API.
3. Apply through the existing migration/startup process; never reset production tables. GIN
   index creation takes locks: schedule a migration window if the chunk corpus is already large.
4. Use an existing admin account. Admin promotion is a separate private operation and is not
   bypassed by this feature. Nominate/review a harmless question, query it, export both splits,
   withdraw it and verify exclusion. Confirm an ordinary student cannot access admin endpoints.
5. Keep Gemini chat configured during this foundation stage. No existing chat provider routing
   or startup bootstrap setting changes are required.

SQLite unit tests use a bounded test-only lexical fallback. Production lexical ranking/indexes
and migrations are exercised in the PostgreSQL CI job, not certified by SQLite results alone.
