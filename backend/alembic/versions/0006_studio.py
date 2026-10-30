"""Personal document drafts and private chat attachment metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0006_studio"
down_revision = "0005_inbox"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "messages", sa.Column("attachments", sa.JSON(), nullable=False, server_default="[]")
    )
    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("chat_requests.id")),
        sa.Column("filename", sa.String(160), nullable=False),
        sa.Column("mime", sa.String(60), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(200), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    for field in ("owner_id", "conversation_id", "request_id"):
        op.create_index("ix_chat_attachments_" + field, "chat_attachments", [field])
    op.create_table(
        "studio_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("target_pages", sa.Integer(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("pending", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_studio_documents_positive_revision")),
    )
    op.create_index("ix_studio_documents_owner_id", "studio_documents", ["owner_id"])


def downgrade():
    raise RuntimeError("Personal document retention requires an explicit data-preserving plan.")
