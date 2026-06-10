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
import sys
from pathlib import Path
from typing import Any

from config import settings
from harness import instrument

_COV_MARKER = "@@@DEV3COVJSON@@@"


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

@instrument("sandbox")
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

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        # 'docker' 명령이 없음 — 예: m3 가 컨테이너 안(docker compose)에서 실행 → docker-in-docker 불가.
        # 격리 샌드박스를 못 띄우므로 work_dir 에서 pytest 를 '직접' 실행해 커버리지를 측정한다.
        # 트레이드오프: PR 테스트가 m3 프로세스 환경에서 직접 돈다(격리 약함). 내/팀 레포 전용이라 허용 —
        # 불특정 외부 PR 서비스가 되면 재검토(범위 밖). 현업 CI(러너 직접 실행)와 동일한 방식.
        return _run_direct(work_dir, normalized_cmd, install_cmd, timeout)

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


def _run_direct(
    work_dir: str,
    normalized_cmd: str,
    install_cmd: str | None,
    timeout: int,
) -> dict[str, Any]:
    """도커 미가용 시 fallback — work_dir 에서 pytest 를 '직접' 실행하고 coverage.json 을 읽어 회수.

    격리 없음(현업 CI 가 깨끗한 러너에서 직접 돌리는 방식과 동일). docker 샌드박스 경로와 반환형 동일:
        {"returncode": int, "stdout": str, "coverage": dict | None}
    """
    # 의존성 설치(있으면) — best-effort. 실패해도 테스트는 시도한다(정직).
    if install_cmd:
        try:
            subprocess.run(install_cmd.split(), cwd=work_dir, capture_output=True, timeout=timeout)
        except Exception:  # noqa: BLE001 — 설치 실패해도 정직하게 진행
            pass

    # 'python -m pytest ...' → 현재 인터프리터로 치환(venv/컨테이너 안정성)
    parts = normalized_cmd.split()
    if parts and parts[0] == "python":
        parts = [sys.executable, *parts[1:]]

    result = subprocess.run(parts, cwd=work_dir, capture_output=True, timeout=timeout)

    # pytest --cov-report=json 이 work_dir 에 남긴 coverage.json 을 읽는다(없으면 None — 가짜 금지).
    coverage_data: dict | None = None
    cov_path = Path(work_dir) / "coverage.json"
    if cov_path.exists():
        try:
            coverage_data = json.loads(cov_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            coverage_data = None

    return {
        "returncode": result.returncode,
        "stdout": result.stdout.decode(errors="replace"),
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
