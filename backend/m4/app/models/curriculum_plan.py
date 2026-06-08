import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class CurriculumPlan(Base):
    __tablename__ = "curriculum_plan"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_curriculum_plan_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("review_issue.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    llm_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    card_content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)  # status=completed일 때 채워짐
    completed_at: Mapped[Optional[datetime]] = mapped_column()  # 사용자가 카드를 학습 완료한 시각 (POST /api/complete, D11) — status='completed'(카드 생성 성공)와 무관한 별개 개념
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now(), onupdate=func.now())
