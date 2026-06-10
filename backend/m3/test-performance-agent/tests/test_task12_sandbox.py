"""Task 12: prepare/sandbox.py — Docker pytest --cov 실행 래퍼 TDD.

어제 발견한 함정 4가지 반영:
  1. 컨테이너 종료 전 `rm -f /work/coverage.json` (root 권한 충돌 회피)
  2. coverage JSON은 stdout 마커(@@@DEV3COVJSON@@@)로 회수 (호스트가 직접 기록)
  3. `pytest` → `python -m pytest` 정규화 (cwd import)
  4. 의존성 있으면 --network bridge + pip install, 없으면 --network none
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from prepare.sandbox import run_sandbox, _normalize_test_cmd, _detect_install_cmd


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

COV_MARKER = "@@@DEV3COVJSON@@@"
SAMPLE_COV = {"totals": {"percent_covered": 20.0}, "files": {}}


def _ok_output(extra: str = "") -> MagicMock:
    """Docker 실행 성공 모킹: stdout에 coverage JSON 마커 포함."""
    cov_json = json.dumps(SAMPLE_COV)
    stdout = f"some test output\n{COV_MARKER}{cov_json}\n{extra}".encode()
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = b""
    return m


def _ok_no_cov() -> MagicMock:
    """Docker 실행 성공 모킹: coverage JSON 마커 없음."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = b"some test output\n"
    m.stderr = b""
    return m


# ──────────────────────────────────────────────
# Test 1: pytest → python -m pytest 정규화
# ──────────────────────────────────────────────

def test_normalize_test_cmd_replaces_pytest():
    """'pytest ...' 명령은 'python -m pytest ...'로 정규화된다."""
    result = _normalize_test_cmd("pytest --cov=src --cov-report=json tests/")
    assert result.startswith("python -m pytest")
    assert "--cov=src" in result


def test_normalize_test_cmd_preserves_python_m_pytest():
    """이미 'python -m pytest'이면 앞부분을 변경하지 않는다 (--cov-report=json은 추가될 수 있음)."""
    cmd = "python -m pytest --cov=src tests/ --cov-report=json"
    assert _normalize_test_cmd(cmd) == cmd


def test_normalize_test_cmd_adds_cov_report_json():
    """--cov-report=json이 없으면 자동 추가된다."""
    result = _normalize_test_cmd("python -m pytest --cov=src tests/")
    assert "--cov-report=json" in result


def test_normalize_test_cmd_no_duplicate_cov_report():
    """--cov-report=json이 이미 있으면 중복 추가하지 않는다."""
    cmd = "python -m pytest --cov=src --cov-report=json tests/"
    result = _normalize_test_cmd(cmd)
    assert result.count("--cov-report=json") == 1


# ──────────────────────────────────────────────
# Test 2: 의존성 감지 (_detect_install_cmd)
# ──────────────────────────────────────────────

def test_detect_install_cmd_requirements_txt(tmp_path):
    """requirements.txt가 있으면 pip install -q -r requirements.txt를 반환한다."""
    (tmp_path / "requirements.txt").write_text("requests\n")
    cmd = _detect_install_cmd(str(tmp_path))
    assert cmd is not None
    assert "requirements.txt" in cmd


def test_detect_install_cmd_pyproject(tmp_path):
    """pyproject.toml이 있으면 pip install -q -e .를 반환한다."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    cmd = _detect_install_cmd(str(tmp_path))
    assert cmd is not None
    assert "-e" in cmd or "pip install" in cmd


def test_detect_install_cmd_none_when_no_deps(tmp_path):
    """의존성 파일이 없으면 None을 반환한다."""
    result = _detect_install_cmd(str(tmp_path))
    assert result is None


# ──────────────────────────────────────────────
# Test 3: 의존성 없음 → --network none
# ──────────────────────────────────────────────

def test_run_sandbox_network_none_when_no_deps(tmp_path):
    """의존성 파일이 없으면 docker 명령에 --network none이 포함된다."""
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_no_cov()) as mock_run:
        run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    docker_cmd = mock_run.call_args[0][0]
    assert "--network" in docker_cmd
    idx = docker_cmd.index("--network")
    assert docker_cmd[idx + 1] == "none"


# ──────────────────────────────────────────────
# Test 4: 의존성 있음 → --network bridge
# ──────────────────────────────────────────────

def test_run_sandbox_network_bridge_when_deps(tmp_path):
    """requirements.txt가 있으면 docker 명령에 --network bridge가 포함된다."""
    (tmp_path / "requirements.txt").write_text("requests\n")
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_no_cov()) as mock_run:
        run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    docker_cmd = mock_run.call_args[0][0]
    assert "--network" in docker_cmd
    idx = docker_cmd.index("--network")
    assert docker_cmd[idx + 1] == "bridge"


# ──────────────────────────────────────────────
# Test 5: rm -f /work/coverage.json 포함 (root 권한 충돌 회피)
# ──────────────────────────────────────────────

def test_run_sandbox_removes_coverage_json_before_exit(tmp_path):
    """컨테이너 sh -c 명령에 'rm -f /work/coverage.json'이 포함된다."""
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_no_cov()) as mock_run:
        run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    docker_cmd = mock_run.call_args[0][0]
    full_cmd = " ".join(docker_cmd)
    assert "rm -f /work/coverage.json" in full_cmd


# ──────────────────────────────────────────────
# Test 6: stdout 마커로 coverage JSON 회수 → 호스트가 파일 기록
# ──────────────────────────────────────────────

def test_run_sandbox_parses_coverage_from_stdout(tmp_path):
    """@@@DEV3COVJSON@@@ 마커 뒤 JSON을 파싱하고 coverage.json을 호스트가 직접 기록한다."""
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_output()):
        result = run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    # 반환값에 coverage dict가 포함되어야 함
    assert result.get("coverage") is not None
    assert "totals" in result["coverage"]

    # 호스트가 {work_dir}/coverage.json을 직접 기록
    cov_path = tmp_path / "coverage.json"
    assert cov_path.exists()
    data = json.loads(cov_path.read_text())
    assert data["totals"]["percent_covered"] == 20.0


# ──────────────────────────────────────────────
# Test 7: 마커 없으면 coverage=None 반환
# ──────────────────────────────────────────────

def test_run_sandbox_returns_none_coverage_when_no_marker(tmp_path):
    """stdout에 마커가 없으면 coverage=None을 반환하고 파일을 만들지 않는다."""
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_no_cov()):
        result = run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    assert result.get("coverage") is None
    assert not (tmp_path / "coverage.json").exists()


# ──────────────────────────────────────────────
# Test 8: docker run에 필수 격리 옵션 포함
# ──────────────────────────────────────────────

def test_run_sandbox_includes_isolation_options(tmp_path):
    """docker run 명령에 --rm, --memory, --cpus, -v, -w 등 격리 옵션이 포함된다."""
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_no_cov()) as mock_run:
        run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    docker_cmd = mock_run.call_args[0][0]
    cmd_str = " ".join(docker_cmd)

    assert "--rm" in docker_cmd
    assert "--memory" in cmd_str
    assert "--cpus" in cmd_str
    assert "-v" in docker_cmd
    assert "-w" in docker_cmd


# ──────────────────────────────────────────────
# Test 9: docker 실패 시 returncode를 결과에 포함
# ──────────────────────────────────────────────

def test_run_sandbox_returns_returncode_on_failure(tmp_path):
    """pytest가 실패(returncode=1)해도 RuntimeError 대신 결과 dict의 returncode로 알린다."""
    fail = MagicMock()
    fail.returncode = 1
    fail.stdout = b"FAILED tests/test_foo.py::test_bar"
    fail.stderr = b""

    with patch("prepare.sandbox.subprocess.run", return_value=fail):
        result = run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    assert result["returncode"] == 1


# ──────────────────────────────────────────────
# Test 10: test_command에 python -m pytest가 최종 명령에 사용됨
# ──────────────────────────────────────────────

def test_run_sandbox_uses_normalized_command_in_docker(tmp_path):
    """'pytest ...' 입력이 최종 docker sh -c 명령에서 'python -m pytest'로 실행된다."""
    with patch("prepare.sandbox.subprocess.run", return_value=_ok_no_cov()) as mock_run:
        run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    docker_cmd = mock_run.call_args[0][0]
    full_cmd = " ".join(docker_cmd)
    assert "python -m pytest" in full_cmd


# ──────────────────────────────────────────────
# Test 11~13: 도커 미가용 → work_dir 에서 pytest 직접 실행 fallback (SESSION E)
#   컨테이너 안(docker compose)에선 'docker' 명령이 없어 샌드박스를 못 띄운다 →
#   격리 없이 work_dir 에서 직접 측정하는 fallback. 현업 CI(러너 직접 실행)와 동일 방식.
# ──────────────────────────────────────────────

def _direct_ok(returncode: int = 0, stdout: bytes = b"direct pytest output") -> MagicMock:
    """fallback(직접 pytest) 실행 성공 모킹."""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = b""
    return m


def test_run_sandbox_falls_back_to_direct_when_docker_missing(tmp_path):
    """docker 명령이 없으면(FileNotFoundError) work_dir 에서 pytest 를 직접 실행하고
    coverage.json 을 읽어 동일 반환형으로 돌려준다(컨테이너 안 docker-in-docker 불가 대응)."""
    # 직접 실행 경로가 읽을 coverage.json 을 미리 둔다(pytest --cov-report=json 이 남기는 파일)
    (tmp_path / "coverage.json").write_text(json.dumps(SAMPLE_COV), encoding="utf-8")

    with patch(
        "prepare.sandbox.subprocess.run",
        side_effect=[FileNotFoundError(2, "No such file or directory", "docker"), _direct_ok()],
    ) as mock_run:
        result = run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    # 1st = docker(없음→FNF), 2nd = 직접 pytest
    assert mock_run.call_count == 2
    direct_cmd = mock_run.call_args_list[1][0][0]
    direct_str = " ".join(direct_cmd) if isinstance(direct_cmd, (list, tuple)) else str(direct_cmd)
    assert "pytest" in direct_str
    assert "-m" in direct_str            # python -m pytest
    assert "docker" not in direct_str    # 도커 안 부름

    # coverage 회수 + 반환형 동일({returncode, stdout, coverage})
    assert result["coverage"] is not None
    assert result["coverage"]["totals"]["percent_covered"] == 20.0
    assert result["returncode"] == 0


def test_run_sandbox_direct_runs_in_work_dir(tmp_path):
    """직접 실행 fallback 은 work_dir(cwd)에서 돈다."""
    with patch(
        "prepare.sandbox.subprocess.run",
        side_effect=[FileNotFoundError(2, "x", "docker"), _direct_ok()],
    ) as mock_run:
        run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    direct_kwargs = mock_run.call_args_list[1][1]
    assert direct_kwargs.get("cwd") == str(tmp_path)


def test_run_sandbox_direct_coverage_none_when_no_file(tmp_path):
    """직접 실행인데 coverage.json 이 없으면 coverage=None(가짜 커버리지 금지) + returncode 전달."""
    with patch(
        "prepare.sandbox.subprocess.run",
        side_effect=[FileNotFoundError(2, "x", "docker"), _direct_ok(returncode=1, stdout=b"FAILED")],
    ):
        result = run_sandbox(str(tmp_path), test_command="pytest --cov=src tests/")

    assert result["coverage"] is None
    assert result["returncode"] == 1
