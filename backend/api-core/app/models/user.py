"""User 모델 — 팀 통합 DDL `users` 테이블 직접 매핑."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from shared.db import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    github_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_level: Mapped[str] = mapped_column(String(20), nullable=False, default="junior")
    career_years: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tech_stack: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        server_default="[]",
    )
    diagnosis_source: Mapped[str] = mapped_column(String(20), nullable=False, default="github")
    diagnosis_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_week: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def login(self) -> str:
        """API 호환 — DDL `github_id`는 GitHub 사용자명."""
        return self.github_id or ""

    @property
    def avatar_url(self) -> str | None:
        """API 호환 — 프로필 URL."""
        return self.github_url
