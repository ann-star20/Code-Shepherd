"""프레임워크 감지 — Issue.programming_language·framework·framework_version (Dev2 통일).

requirements.txt(없으면 pyproject.toml)를 읽어 파이썬 웹 프레임워크와 핀 버전을
파싱한다. 파일 파싱=사실이라 LLM 없음. 레포 단위 정보 → 모든 이슈에 동일하게 채움.

- 의존성 파일이 없으면 전부 빈 값(안전): programming_language도 채우지 않음.
- 여러 프레임워크가 있으면 우선순위(django > fastapi > flask)로 1개 선택.
"""
from __future__ import annotations

import re
from pathlib import Path

from harness import instrument

# 우선순위 순서 (앞이 우선)
FRAMEWORKS = ["django", "fastapi", "flask"]

_REQ_FILES = ("requirements.txt", "pyproject.toml")


def _read_dependency_text(repo_path: str) -> str | None:
    """requirements.txt(우선) 또는 pyproject.toml 내용. 둘 다 없으면 None."""
    repo = Path(repo_path)
    for name in _REQ_FILES:
        path = repo / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def _parse_framework(text: str) -> tuple[str, str]:
    """의존성 텍스트에서 프레임워크명과 버전을 우선순위로 1개 추출. (framework, version)."""
    for fw in FRAMEWORKS:
        # 줄 시작에서 프레임워크명(대소문자 무시), 선택적으로 '==버전'
        m = re.search(
            rf"(?im)^\s*{re.escape(fw)}\s*(?:==\s*([0-9][\w.\-]*))?",
            text,
        )
        if m:
            return fw, (m.group(1) or "")
    return "", ""


def _has_py_files(repo_path: str) -> bool:
    """레포 루트에 .py 파일이 1개 이상 있으면 True (재귀 탐색 없음 — 루트 직접 자식만)."""
    repo = Path(repo_path)
    return any(repo.glob("*.py")) or any(repo.rglob("*.py"))


def detect(repo_path: str) -> tuple[str, str, str]:
    """(programming_language, framework, framework_version).

    의존성 파일(requirements.txt/pyproject.toml) 있으면 언어+프레임워크+버전 파싱.
    없지만 .py 파일이 있으면 language="python" 폴백(사실), framework/version은 빈값(정직).
    둘 다 없으면 모두 빈 값.
    """
    text = _read_dependency_text(repo_path)
    if text is not None:
        framework, version = _parse_framework(text)
        return "python", framework, version
    if _has_py_files(repo_path):
        return "python", "", ""
    return "", "", ""


@instrument("framework")
def augment_issues(issues: list, repo_path: str) -> None:
    """모든 이슈에 programming_language·framework·framework_version을 채운다(제자리 수정)."""
    language, framework, version = detect(repo_path)
    if not language:
        return
    for issue in issues:
        issue.programming_language = language
        issue.framework = framework
        issue.framework_version = version
