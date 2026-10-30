# Release verification without paid hosting

These rehearsals run only against disposable test fixtures. They do not enable hosted
uploads, purchase services, configure real administrators, or spend Gemini credits.

## Checks

`backend/tests/test_release_gates.py` adds:

- Eight concurrent authenticated students making 240 chat/read/isolation requests against
  PostgreSQL. Each student saves ten question/answer pairs; reads by other students must
  return 404. Timings describe in-process ASGI three-request cycles, not hosted throughput,
  HTTP network latency, Gemini latency or a production capacity guarantee.
- Real pgvector cosine ranking across two topic-specific documents, unrelated-query
  rejection, and source-location preservation. Deterministic embeddings deliberately
  isolate database ranking from external model quality. This is not a semantic evaluation
  of Gemini embeddings or a human assessment of academic answers.
- Untrusted reference delimiters and fail-closed retrieval error handling. This tests
  prompt construction, not universal resistance to model prompt injection.
- An actual `pg_dump`/`pg_restore` rehearsal into a fresh database named
  `edumind_restore_<random UUID>`. It compares every row in the isolated test schema,
  including accounts, sessions, audit records, conversations, documents and vector chunks,
  then runs vector retrieval against the restored database. A separate temporary private
  object snapshot and SHA-256 manifest restore the fixture document bytes. Only the newly
  created restore database is dropped. The source database is never reset.

## Run

Use a disposable PostgreSQL instance with pgvector and a role allowed to create disposable
databases. Install `pg_dump` and `pg_restore` compatible with the server (a dump client must
not be older than its server). Never supply the hosted application database URL here.

From `backend`, set `TEST_DATABASE_URL` and `DATABASE_URL` to that disposable instance,
set `APP_ENV=test`, and set `RUN_BACKUP_REHEARSAL=true`. Then run:

```sh
pytest -q -rP tests/test_release_gates.py
```

CI enables the backup opt-in only in its ephemeral PostgreSQL backend job. The test
authentication fixture creates its own random schema. Without PostgreSQL, three of these
checks explicitly skip; a skipped check is not evidence of success.

## Same-origin session recovery regression

The deployed browser revealed that a same-origin `GET /auth/csrf` can lack `Origin`.
The old origin-only guard returned 403 and left signed-out visitors at "Let's reconnect"
instead of the sign-in page. HTTP smoke tests manually supplied Origin, and the browser
suite used a cross-origin API URL, so neither represented the deployed proxy behavior.

The guard now accepts an exact allowlisted Referer origin only for the read-only CSRF GET
when Origin is absent. Explicit untrusted Origin is still rejected, and writes continue
requiring trusted Origin plus the existing CSRF checks. Regression cases reject missing,
malformed, credential-bearing and lookalike Referers. Browser CI now uses the same-origin
Vite API proxy so cookie recovery/reload tests exercise this deployment topology.

First PostgreSQL CI run 41134204510 passed concurrency/ranking checks; the restore command
needed an explicit --dbname option. That test-command correction and the session fix are
awaiting the new full run. No failed or skipped restore is counted as successful evidence.

The restore rehearsal then exposed a test-isolation flaw: Alembic could find an existing
public version table on search_path and skip creating the new test schema's tables.
Tests now give migrations an explicit version-table schema and assert that users,
knowledge_chunks and alembic_version actually exist there before running any fixture.
The CLI option is test-only; normal deployed migration behavior remains unchanged.

## Evidence and remaining boundaries

Local prompt-boundary test passed. Local PostgreSQL startup is restricted in this
execution environment, so database rehearsal results must come from CI and are pending
until recorded below. Existing regression evidence is in final-readiness.md.

Even after these rehearsals pass, the hosted gates remain: real private storage and worker,
administrator bootstrap, hosted document/embedding/retrieval/removal checks, human answer
evaluation, a hosted backup/restore exercise, full deployed browser verification, the
user's actual Windows inbox, and automatic source deployments. Paid services are paused
at the user's request. These checks do not change that decision.
