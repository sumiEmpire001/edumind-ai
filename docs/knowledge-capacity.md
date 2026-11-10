# Knowledge capacity benchmark

The first million-resource benchmark counts one approved training question/answer pair as
one searchable record. Document passages, source files, tokens in a prompt, and simultaneous
users are separate units. The standalone model has its own inference and quality gates.

## Run

From `backend`, use an empty, disposable, loopback PostgreSQL database named
`edumind_capacity_test` with pgvector available. Apply the repository's Alembic migrations
using that database and test settings. Then run:

```sh
export EDUMIND_CAPACITY_DATABASE_URL='postgresql+psycopg://USER@127.0.0.1:5432/edumind_capacity_test'
python -m tools.benchmark_knowledge
```

Use `--rows 1000` for a quick run on a fresh database. The script rejects non-loopback URLs,
other database names and existing users, reviewed examples, or document passages. It leaves
the synthetic data in the disposable database so results can be inspected.

The script uses the current schema and the same `search()` function as the Knowledge API.
It seeds batches directly in PostgreSQL to isolate storage and retrieval from the submission
and review queue. It checks returned source counts and query matches, and reports statement
timeouts separately from completed-query p95 latency. The workload runs sequentially and
includes selective lookups, topic lookups, misses, and a term matching the entire corpus.

## First measured run

On 9 November 2026, the local embedded PostgreSQL 18.6 (PGlite) run committed
1,000,000 synthetic approved Q&A rows, with no document passages. Seeding and analysis took
127.78 seconds. The Q&A table and indexes occupied 1,254,752,256 bytes, of which
344,268,800 bytes were indexes. The database measured 1,263,427,707 bytes.
The selective text-search plan used the GIN index.

| Search case | Probes | Completed latency |
| --- | ---: | ---: |
| Exact resource term | 50 | 13.62 ms p95 |
| Topic term matching 10,000 rows | 20 | 863.81 ms p95 |
| No matching term | 20 | 8.15 ms p95 |
| Term matching all 1,000,000 rows | 1 | 138.74 seconds |

All probes returned the expected result counts and matching titles. The embedded run
did not interrupt the broad statement, which exceeded the app's three-second SQL budget.
Use `--skip-whole-corpus` to isolate the other probes when cancellation is unreliable.
These are sequential search-function measurements on synthetic data, with no live HTTP,
parallel clients, hosted ingestion, document vectors, or model inference in the timed path.
The tested footprint alone exceeds the current Render free database's 1 GB capacity.

## What must still be measured

- Native staging PostgreSQL with representative document and Q&A lengths, real ingestion,
  index size, concurrent query load, and sustained insert/review/index throughput.
- Retrieval correctness for reviewed and withdrawn material at scale, broad-query latency
  and timeouts, document chunking, and vector retrieval quality.
- Independent model serving with a bounded selection of retrieved sources per question.
  Measure citation support, accuracy, abstention, input/output tokens, latency, and concurrency
  against a held-out evaluation set. Training and inference remain separate from indexing.

A million 768-dimensional pgvector uncompressed embeddings alone require approximately 3.08 GB before
source text, row overhead, vector indexes, and other tables. See
[pgvector's storage formula](https://github.com/pgvector/pgvector#vector-type).
