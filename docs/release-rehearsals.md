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

The restore rehearsal also exposed a test-isolation flaw: Alembic could find an existing
public version table on search_path and skip creating the new test schema's tables.
Tests now give migrations an explicit version-table schema and assert that users,
knowledge_chunks and alembic_version actually exist there before running any fixture.
The CLI option is test-only; normal deployed migration behavior remains unchanged.

## Evidence and remaining boundaries

GitHub run [41134952520](https://github.com/sumiEmpire001/edumind-ai/actions/runs/41134952520)
passed all five jobs on commit 558c3603255799919803db499debb7eebdfc8d94:
144 PostgreSQL backend tests with no skips, 45 frontend unit tests, 26 desktop Chromium/
mobile WebKit browser tests, dependency audits, and 11 inbox tests on each of Linux and
Windows. PR #7 is merged as 4ab6333f465c2b89524b94df02d2993c12277174.

Render deploy dep-dbih8359fdbs73dlgdag is live on that merged release. Hosted browser
verification confirmed a signed-out /app/account visit now reaches /login. The frontend
build was not changed. No worker was purchased and hosted RAG remains disabled.

The concurrency rehearsal completed 240 requests in 2.907 seconds, with a 0.321-second
95th percentile for each three-request cycle. These are controlled CI/ASGI measurements
with fixture answers, not hosted capacity or live-model performance claims. The restore
rehearsal compared actual rows and verified vector retrieval after restore, then recovered
the private fixture bytes from the checksummed snapshot. Local regression: 133 passed,
11 PostgreSQL-only skips; Ruff formatting/lint and diff checks passed.

Even after these rehearsals pass, the hosted gates remain: real private storage and worker,
administrator bootstrap, hosted document/embedding/retrieval/removal checks, human answer
evaluation, a hosted backup/restore exercise, full deployed browser verification, the
user's actual Windows inbox, and automatic source deployments. Paid services are paused
at the user's request. These checks do not change that decision.
