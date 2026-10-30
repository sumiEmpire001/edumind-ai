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

## Evidence and remaining boundaries

Local prompt-boundary test passed. Local PostgreSQL startup is restricted in this
execution environment, so database rehearsal results must come from CI and are pending
until recorded below. Existing regression evidence is in final-readiness.md.

Even after these rehearsals pass, the hosted gates remain: real private storage and worker,
administrator bootstrap, hosted document/embedding/retrieval/removal checks, human answer
evaluation, a hosted backup/restore exercise, full deployed browser verification, the
user's actual Windows inbox, and automatic source deployments. Paid services are paused
at the user's request. These checks do not change that decision.
