"""팀 API DTO — teams / team_members SSOT."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

GITHUB_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
_GITHUB_URL_PATTERN = re.compile(
    r"^https?://github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:\.git)?/?$"
)


def normalize_github_repo(value: str) -> str:
    repo = value.strip().rstrip("/")
    url_match = _GITHUB_URL_PATTERN.match(repo)
    if url_match:
        repo = url_match.group(1)
    if not GITHUB_REPO_PATTERN.match(repo):
        raise ValueError(
            "github_repo must be in 'owner/repo' format (e.g. akdlemfla24-dotcom/my-repo)"
        )
    return repo


@dataclass
class TeamView:
    id: uuid.UUID
    name: str
    github_repo_full_name: str
    created_at: datetime


@dataclass
class MemberView:
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime
    login: str
    name: str
    avatar_url: str | None


@dataclass
class InvitationView:
    id: uuid.UUID
    team_id: uuid.UUID
    team_name: str
    invitee_user_id: uuid.UUID
    invited_by_user_id: uuid.UUID
    invited_by_login: str
    invited_by_name: str
    status: str
    created_at: datetime
