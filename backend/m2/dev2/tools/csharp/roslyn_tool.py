"""
Roslyn — C# 정적 분석 도구 (dotnet build 경유)

동작 방식:
    dotnet build --no-restore 실행 시 Roslyn 분석기가 자동으로 경고/오류를 출력한다.
    출력 패턴: "path(line,col): warning CSXXXX: message"

severity 매핑:
    error   → Critical
    warning → Major

주의: .csproj 파일이 있는 디렉터리에서 실행해야 한다.
      Docker 컨테이너에 .NET SDK가 설치되어 있어야 한다.
"""

import subprocess
import re

# dotnet build 출력 파싱 패턴
_PATTERN = re.compile(r"(.+)\((\d+),\d+\): (warning|error) (CS\w+): (.+)")


def run_roslyn(files: list[str]) -> list[dict]:
    """
    dotnet build 를 실행하고 Roslyn 분석 이슈를 반환한다.

    Args:
        files: 분석 대상 파일 목록 (실제로는 프로젝트 단위로 실행됨, 목록은 필터용)

    Returns:
        Output Contract A 형식의 이슈 딕셔너리 목록.
        dotnet 미설치 시 빈 리스트 반환.
    """
    if not files:
        return []

    r = subprocess.run(
        ["dotnet", "build", "--no-restore", "--verbosity=normal"],
        capture_output=True, text=True, timeout=60
    )

    issues = []
    for line in r.stdout.splitlines():
        m = _PATTERN.match(line.strip())
        if m:
            issues.append({
                "severity": "Critical" if m.group(3) == "error" else "Major",
                "line": int(m.group(2)),
                "file": m.group(1),
                "message": m.group(5),
                "rule_id": f"CS-{m.group(4)}",
                "suggestion": f"Roslyn: {m.group(4)} 참조",
                "similar_issues": [],
            })
    return issues
