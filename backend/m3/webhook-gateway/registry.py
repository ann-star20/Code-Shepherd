"""분석 에이전트 플러그인 레지스트리.

각 팀원은 자기 분석 함수를 여기에 '등록'만 하면, Webhook이 PR을 받을 때
등록된 모든 에이전트를 차례로 호출한다. (Dev2도 자기 함수 하나만 등록)

분석 함수 규약 (계약):
    def analyze(ctx: PRContext) -> list[dict]:
        '''PR 정보를 받아 이슈 목록(dict)을 반환.
        반환 dict 형식 (표준 Issue):
          {"severity": "Major", "file": "src/x.py", "line": 7,
           "message": "...", "rule_id": "PERF-002", "suggestion": "..."}
        '''
        ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PRContext:
    """Webhook이 추출한 PR 정보. 모든 분석 에이전트가 받는 입력."""
    repo_full_name: str          # "owner/repo"
    clone_url: str               # "https://github.com/owner/repo.git"
    pr_number: int
    commit_sha: str
    branch: str
    author: str = ""
    work_dir: str = ""           # clone된 로컬 경로 (게이트웨이가 채워줌)
    pr_diff: str = ""            # unified diff (게이트웨이가 채워줌)


@dataclass
class RegisteredAgent:
    name: str                    # "test_verification" 등
    fn: Callable                 # analyze(ctx) -> list[dict]


# ── 전역 레지스트리 ──────────────────────────────────────
_AGENTS: list[RegisteredAgent] = []


def register(name: str):
    """데코레이터 — 분석 함수를 게이트웨이에 등록.

    사용 예 (Dev2):
        @register("security_scan")
        def my_security_analyze(ctx):
            return [{"severity": "Critical", ...}]
    """
    def deco(fn: Callable) -> Callable:
        _AGENTS.append(RegisteredAgent(name=name, fn=fn))
        return fn
    return deco


def register_fn(name: str, fn: Callable) -> None:
    """데코레이터 대신 직접 등록 (이미 만들어진 함수 연결용)."""
    _AGENTS.append(RegisteredAgent(name=name, fn=fn))


def registered_agents() -> list[RegisteredAgent]:
    return list(_AGENTS)


def clear() -> None:
    """테스트용 — 등록 초기화."""
    _AGENTS.clear()
