"""Measure the actual Knowledge API search against synthetic reviewed Q&A rows."""

import argparse
import json
import math
import os
import time

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.session import build_engine, check_database
from app.knowledge.learning import search

SEED = text("""
    INSERT INTO learning_examples
      (id, owner_id, question, question_digest, answer, evidence, status, split,
       created_at, updated_at)
    SELECT gen_random_uuid(), '00000000-0000-4000-8000-000000000001',
      'Academic resource' || lpad(n::text, 7, '0') ||
          ' topic' || lpad((n % 100)::text, 3, '0'),
      encode(sha256(convert_to(n::text, 'UTF8')), 'hex'),
      format(
        'This academic practice example uses specimen %s, measurement %s, and trial %s. ',
        n, n % 127, n % 73
      ) || repeat(
        'Compare observations, explain the reasoning, and check results with a second method. ',
        6
      ),
      'Synthetic capacity fixture', 'approved', 'train', now(), now()
    FROM generate_series(CAST(:first AS integer), CAST(:last AS integer)) AS n
""")


def run(size, url, *, skip_whole_corpus=False):
    settings = Settings(
        _env_file=None, app_env="test", database_url=url, jwt_secret="capacity-fixture-" * 3
    )
    engine = build_engine(settings)
    try:
        if not check_database(engine):
            raise SystemExit("Migrate the disposable capacity database to head first.")
        with engine.begin() as db:
            for table in ("users", "learning_examples", "knowledge_chunks"):
                if db.scalar(text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
                    raise SystemExit("Use an empty, disposable benchmark database.")
            db.execute(
                text("""
                INSERT INTO users
                  (id, email, full_name, password_hash, role, is_active, created_at, updated_at)
                VALUES ('00000000-0000-4000-8000-000000000001', 'capacity@example.invalid',
                        'Capacity fixture', 'unusable', 'student', false, now(), now())
            """)
            )

        started = time.perf_counter()
        for first in range(1, size + 1, 25_000):
            with engine.begin() as db:
                db.execute(text("SET LOCAL statement_timeout = '120s'"))
                db.execute(SEED, {"first": first, "last": min(first + 24_999, size)})
            if min(first + 24_999, size) % 100_000 == 0:
                print(f"Loaded {min(first + 24_999, size):,} rows", flush=True)

        with engine.begin() as db:
            db.execute(text("SET LOCAL statement_timeout = '120s'"))
            db.execute(text("ANALYZE learning_examples"))
            rows = db.scalar(text("SELECT count(*) FROM learning_examples"))
            table_bytes = db.scalar(text("SELECT pg_total_relation_size('learning_examples')"))
            index_bytes = db.scalar(text("SELECT pg_indexes_size('learning_examples')"))
            database_bytes = db.scalar(text("SELECT pg_database_size(current_database())"))
            server = db.scalar(text("SHOW server_version"))
            index_plan = db.scalar(
                text("""
                EXPLAIN (FORMAT JSON)
                SELECT id FROM learning_examples
                WHERE to_tsvector('simple', question || ' ' || answer)
                  @@ plainto_tsquery('simple', 'resource0000001')
            """)
            )
        assert rows == size

        result = {
            "postgres_version": server,
            "approved_qa_rows": rows,
            "knowledge_document_passages": 0,
            "seed_and_analysis_seconds": round(time.perf_counter() - started, 2),
            "qa_table_and_indexes_bytes": table_bytes,
            "qa_indexes_bytes": index_bytes,
            "database_bytes": database_bytes,
            "selective_plan_uses_gin_index": "ix_learning_search" in str(index_plan),
            "query_groups": {},
        }
        print(json.dumps({k: v for k, v in result.items() if k != "query_groups"}), flush=True)
        probes = {
            "single_resource": [f"resource{i:07}" for i in range(1, size + 1, max(1, size // 50))],
            "topic": [f"topic{i:03}" for i in range(20)],
            "missing": [f"nonexistent{i:03}" for i in range(20)],
            "whole_corpus": ["academic"],
        }
        if skip_whole_corpus:
            del probes["whole_corpus"]
        for group, questions in probes.items():
            timings = []
            timeouts = 0
            for question in questions:
                start = time.perf_counter()
                try:
                    with Session(engine) as db:
                        sources = search(db, question)
                except DBAPIError as exc:
                    if getattr(exc.orig, "sqlstate", None) != "57014":
                        raise
                    timeouts += 1
                    continue
                timings.append(round((time.perf_counter() - start) * 1000, 2))
                expected = {"single_resource": 1, "missing": 0}.get(group, 5)
                assert len(sources) == expected, (group, question, len(sources))
                assert all(question.casefold() in source["title"].lower() for source in sources)
            timings.sort()
            result["query_groups"][group] = {
                "requests": len(questions),
                "statement_timeouts": timeouts,
                "completed_p95_ms": timings[math.ceil(len(timings) * 0.95) - 1]
                if timings
                else None,
            }
            print(json.dumps({group: result["query_groups"][group]}), flush=True)
        print(json.dumps(result, indent=2), flush=True)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument(
        "--skip-whole-corpus",
        action="store_true",
        help="Skip the broad probe on environments with unreliable query cancellation.",
    )
    args = parser.parse_args()
    if not 1_000 <= args.rows <= 1_000_000:
        parser.error("--rows must be between 1,000 and 1,000,000")
    raw_url = os.getenv("EDUMIND_CAPACITY_DATABASE_URL")
    if not raw_url:
        parser.error("Set EDUMIND_CAPACITY_DATABASE_URL for a disposable local database.")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "edumind_capacity_test"
        or set(url.query) - {"sslmode"}
    ):
        parser.error("Use an empty local PostgreSQL database named edumind_capacity_test.")
    run(args.rows, raw_url, skip_whole_corpus=args.skip_whole_corpus)


if __name__ == "__main__":
    main()
