"""Allow approved text passages to be indexed without an embedding provider."""

from alembic import op

revision = "0008_lexical_knowledge"
down_revision = "0007_learning"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("knowledge_chunks", "embedding", nullable=True)


def downgrade():
    # PostgreSQL rejects this without modifying data if text-only passages exist.
    op.alter_column("knowledge_chunks", "embedding", nullable=False)
