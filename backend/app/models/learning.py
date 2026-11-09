"""Explicitly shared, reviewed learning data; never a mirror of private conversations."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class LearningExample(Base):
    __tablename__ = "learning_examples"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(String(2000))
    question_digest: Mapped[str] = mapped_column(String(64), unique=True)
    answer: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    split: Mapped[str] = mapped_column(String(16), default="train")
    reviewer_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        # Group the left concatenation like PostgreSQL index reflection.
        Index(
            "ix_learning_search",
            text("to_tsvector('simple', (question::text || ' '::text) || answer)"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("status IN ('pending','approved','rejected')", name="learning_status"),
        CheckConstraint("split IN ('train','evaluation')", name="learning_split"),
    )


class LearningQuery(Base):
    __tablename__ = "learning_queries"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    duration_ms: Mapped[int] = mapped_column(Integer)
    source_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
