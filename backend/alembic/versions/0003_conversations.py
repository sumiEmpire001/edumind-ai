"""Add private conversations and durable question idempotency records."""

import sqlalchemy as sa

from alembic import op

revision = "0003_conversations"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("automatic_title", sa.Boolean(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_conversations_owner_updated", "conversations", ["owner_id", "updated_at"])
    op.create_table(
        "chat_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')", name=op.f("ck_chat_requests_valid_status")
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND completed_at IS NULL) OR "
            "(status <> 'pending' AND completed_at IS NOT NULL)",
            name=op.f("ck_chat_requests_completion_state"),
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) OR "
            "(status <> 'failed' AND error_code IS NULL)",
            name=op.f("ck_chat_requests_error_state"),
        ),
        sa.UniqueConstraint("id", "conversation_id", name="uq_chat_requests_id_conversation_id"),
    )
    op.create_index(
        "ix_chat_requests_conversation_status", "chat_requests", ["conversation_id", "status"]
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name=op.f("ck_messages_valid_role")),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_messages_conversation_sequence"
        ),
        sa.UniqueConstraint("request_id", "role", name="uq_messages_request_role"),
        sa.ForeignKeyConstraint(
            ["request_id", "conversation_id"],
            ["chat_requests.id", "chat_requests.conversation_id"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    raise RuntimeError("Destructive chat downgrade disabled; use a reviewed recovery plan.")
