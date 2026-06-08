import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class ReviewIssue(Base):
    __tablename__ = "review_issue"
    __table_args__ = (
        CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_review_issue_severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pull_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("pull_requests.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    github_id: Mapped[Optional[str]] = mapped_column(Text)
    agent: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    sub_category: Mapped[Optional[str]] = mapped_column(Text)
    code_context: Mapped[Optional[str]] = mapped_column(Text)
    code_snippet: Mapped[Optional[str]] = mapped_column(Text)  # 없으면 before_code=null
    suggestion: Mapped[Optional[str]] = mapped_column(Text)
    programming_language: Mapped[Optional[str]] = mapped_column(Text)
    framework: Mapped[Optional[str]] = mapped_column(Text)
    framework_version: Mapped[Optional[str]] = mapped_column(Text)
    name_of_function: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
