"""prepare/sandbox.py — Docker 격리 실행 래퍼.

어제 발견한 함정 반영:
  1. 컨테이너 종료 전 `rm -f /work/coverage.json` (root 권한 충돌 회피)
  2. coverage JSON은 stdout 마커(@@@DEV3COVJSON@@@)로 회수 (호스트가 직접 기록)
  3. `pytest` → `python -m pytest` 정규화 (cwd import)
  4. 의존성 있으면 --network bridge + pip install, 없으면 --network none

TECH_SPEC §9.2 참조.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from config import settings

_COV_MARKER = "@@@DEV3COVJSON@@@"


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def run_sandbox(
    work_dir: str,
    test_command: str = "pytest --cov=src --cov-report=json",
    image: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Docker 컨테이너 안에서 pytest를 실행하고 결과 dict를 반환한다.

    반환값:
        {
          "returncode": int,
          "stdout": str,
          "coverage": dict | None,   # stdout 마커로 회수한 coverage JSON
        }
    """
    image = image or settings.SANDBOX_IMAGE
    timeout = timeout or settings.COV_TIMEOUT_S

    normalized_cmd = _normalize_test_cmd(test_command)
    install_cmd = _detect_install_cmd(work_dir)
    has_deps = install_cmd is not None

    # coverage JSON을 stdout 마커로 내보내는 sh -c 명령 조립
    # 순서: (pip install &&)? rm -f /work/coverage.json && python -m pytest ... && coverage json -o /dev/stdout
    parts: list[str] = []
    if install_cmd:
        parts.append(install_cmd)
    # root가 쓴 coverage.json이 남아 있으면 호스트가 못 읽으므로 먼저 제거
    parts.append("rm -f /work/coverage.json")
    parts.append(normalized_cmd)
    # coverage.json을 stdout 마커로 내보냄 (실패해도 계속)
    parts.append(
        f"echo '{_COV_MARKER}' && coverage json -o /dev/stdout 2>/dev/null || true"
    )
    # 컨테이너(root)가 마운트 폴더에 만든 모든 파일을 호스트가 지우고 덮어쓸 수 있게 권한 개방
    parts.append("chmod -R 0777 /work 2>/dev/null || true")
    sh_cmd = " && ".join(parts)

    network = "bridge" if has_deps else "none"
    cmd = [
        "docker", "run", "--rm",
        "--network", network,
        "--memory", "512m",
        "--cpus", "1",
        "-v", f"{work_dir}:/work",
        "-w", "/work",
        image,
        "sh", "-c", sh_cmd,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=timeout)

    stdout_str = result.stdout.decode(errors="replace")
    coverage_data = _extract_coverage(stdout_str)

    # 호스트가 직접 coverage.json 기록 (컨테이너 root 권한 충돌 우회)
    if coverage_data is not None:
        cov_path = Path(work_dir) / "coverage.json"
        # 컨테이너가 만든 기존 파일이 있으면 권한 충돌 → 먼저 제거 시도
        if cov_path.exists():
            try:
                import stat
                cov_path.chmod(stat.S_IWRITE | stat.S_IREAD)
                cov_path.unlink()
            except OSError:
                pass
        try:
            cov_path.write_text(json.dumps(coverage_data), encoding="utf-8")
        except PermissionError:
            # 그래도 못 쓰면 coverage_data는 메모리에 있으니 별도 경로에 기록
            alt = Path(work_dir) / "_dev3_coverage.json"
            alt.write_text(json.dumps(coverage_data), encoding="utf-8")
            cov_path = alt

    return {
        "returncode": result.returncode,
        "stdout": stdout_str,
        "coverage": coverage_data,
    }


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _normalize_test_cmd(cmd: str) -> str:
    """pytest → python -m pytest 정규화 + --cov-report=json 자동 보강."""
    # 'pytest'로 시작하면 'python -m pytest'로 교체
    stripped = cmd.strip()
    if stripped.startswith("pytest") and not stripped.startswith("python"):
        cmd = "python -m pytest" + stripped[len("pytest"):]

    # --cov-report=json 없으면 추가
    if "--cov-report=json" not in cmd:
        cmd = cmd.rstrip() + " --cov-report=json"

    return cmd


def _detect_install_cmd(work_dir: str) -> str | None:
    """의존성 파일 유무에 따라 pip install 명령을 반환한다. 없으면 None."""
    base = Path(work_dir)
    if (base / "requirements.txt").exists():
        return "pip install -q -r requirements.txt"
    if (base / "pyproject.toml").exists():
        return "pip install -q -e ."
    if (base / "setup.py").exists():
        return "pip install -q -e ."
    if (base / "setup.cfg").exists():
        return "pip install -q -e ."
    return None


def _extract_coverage(stdout: str) -> dict | None:
    """stdout에서 @@@DEV3COVJSON@@@ 마커 뒤 JSON을 추출한다."""
    marker = _COV_MARKER
    if marker not in stdout:
        return None
    after = stdout.split(marker, 1)[1].strip()
    if not after:
        return None
    # JSON 시작({) 이전의 불필요한 텍스트 제거
    brace_idx = after.find("{")
    if brace_idx == -1:
        return None
    after = after[brace_idx:]
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(after)
        return data
    except (json.JSONDecodeError, ValueError):
        return None
