"""팀 API용 식별자 — DDL에 teams 테이블 없음, `users.team` 문자열 기반."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


def team_id_from_name(team_name: str) -> int:
    """안정적인 숫자 팀 ID (프론트 호환)."""
    return abs(hash(team_name)) % (10**9)


def member_row_id(team_name: str, user_id: uuid.UUID) -> int:
    return abs(hash((team_name, str(user_id)))) % (10**9)


@dataclass
class TeamView:
    id: int
    name: str
    created_at: datetime


@dataclass
class MemberView:
    id: int
    user_id: uuid.UUID
    role: str
    joined_at: datetime
