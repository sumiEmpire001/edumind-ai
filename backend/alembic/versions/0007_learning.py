"""Reviewed learning dataset and independent lexical knowledge API."""

import sqlalchemy as sa

from alembic import op

revision = "0007_learning"
down_revision = "0006_studio"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_examples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.String(2000), nullable=False),
        sa.Column("question_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("evidence", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("split", sa.String(16), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="learning_status"),
        sa.CheckConstraint("split IN ('train','evaluation')", name="learning_split"),
    )
    op.create_index("ix_learning_examples_owner_id", "learning_examples", ["owner_id"])
    op.create_index("ix_learning_examples_status", "learning_examples", ["status"])
    op.create_table(
        "learning_queries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learning_queries_created_at", "learning_queries", ["created_at"])
    # Matches the query expressions exactly; no embedding service is required.
    op.execute(
        "CREATE INDEX ix_learning_search ON learning_examples USING gin "
        "(to_tsvector('simple', question || ' ' || answer))"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_text ON knowledge_chunks USING gin "
        "(to_tsvector('simple', content))"
    )


def downgrade():
    op.drop_index("ix_knowledge_chunks_text", table_name="knowledge_chunks")
    op.drop_table("learning_queries")
    op.drop_table("learning_examples")
