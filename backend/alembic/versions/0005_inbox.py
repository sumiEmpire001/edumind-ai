"""Add expiring, revocable submission-only administrator inbox credentials."""

import sqlalchemy as sa

from alembic import op

revision = "0005_inbox"
down_revision = "0004_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inbox_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_credentials_owner_id", "inbox_credentials", ["owner_id"])


def downgrade():
    raise RuntimeError("Credential downgrade requires an explicit revocation/retention plan.")
