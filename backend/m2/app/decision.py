"""m2 mini-orchestrator — 분석 라우팅 판단.

PR diff를 보고 어떤 분석을 돌릴지 결정한다:
  - 정적분석만 / 보안스캔만 / 둘 다 / 건너뜀(skip)

판단 근거(현재 도구 능력에 한정):
  - analyzer가 실제로 스캔할 수 있는 파일은 .py/.js/.jsx/.ts/.tsx 뿐이다.
    → 지원 소스 파일이 하나도 없으면 분석할 게 없으므로 skip.
  - 정적분석/보안스캔 도구는 같은 소스 파일 집합 위에서 돈다.
    → 기본적으로 지원 소스가 있으면 둘 다 후보.
  - 보안 민감 신호(키워드/의존성 파일 변경)가 있으면 보안스캔을 명시적으로 켠다.
    (지원 소스가 없어도 보안 신호만으로는 스캔 대상 파일이 없어 skip — 도구가 못 돈다.)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.analyzer import _SUPPORTED_EXT, _parse_diff

# 보안 민감 키워드 — 추가된 코드(diff post-image)에서 발견되면 보안스캔 우선.
# 대소문자 무시. 과탐을 줄이려 토큰 위주로만 둔다.
_SECURITY_KEYWORDS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "eval(",
    "exec(",
    "subprocess",
    "os.system",
    "pickle",
    "yaml.load",
    "md5",
    "sha1",
    "select ",
    "insert ",
    "delete ",
    "drop ",
)

# 보안 관점에서 의미 있는 의존성/설정 파일 (정적/보안 도구로는 직접 스캔 못 해도 신호로 사용)
_DEPENDENCY_FILES = (
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)


class AnalysisDecision(BaseModel):
    """오케스트레이터 라우팅 결정."""

    needs_static: bool = False
    needs_security: bool = False
    skip: bool = False
    reason: str = ""
    supported_files: list[str] = Field(default_factory=list)
    security_signal: bool = False


def _is_dependency_file(rel_path: str) -> bool:
    name = Path(rel_path).name.lower()
    return name in _DEPENDENCY_FILES


def _has_security_keyword(content: str) -> bool:
    lowered = content.lower()
    return any(kw in lowered for kw in _SECURITY_KEYWORDS)


def decide(pr_diff: str) -> AnalysisDecision:
    """PR diff → 분석 라우팅 결정."""
    files = _parse_diff(pr_diff or "")
    if not files:
        return AnalysisDecision(skip=True, reason="diff에서 복원된 파일 없음")

    supported = [
        rel for rel in files if Path(rel).suffix.lower() in _SUPPORTED_EXT
    ]
    security_signal = any(_is_dependency_file(rel) for rel in files) or any(
        _has_security_keyword(content) for content in files.values()
    )

    if not supported:
        # 스캔 가능한 소스 파일이 없음 → 도구가 돌 대상이 없어 skip.
        reason = "지원 소스 파일(.py/.js/.ts) 변경 없음"
        if security_signal:
            reason += " (보안 신호는 있으나 스캔 대상 파일 없음)"
        return AnalysisDecision(skip=True, reason=reason, security_signal=security_signal)

    return AnalysisDecision(
        needs_static=True,
        needs_security=True,
        skip=False,
        reason="지원 소스 변경 감지",
        supported_files=supported,
        security_signal=security_signal,
    )
