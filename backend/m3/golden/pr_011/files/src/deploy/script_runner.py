"""배포 스크립트 실행기."""
from __future__ import annotations

import subprocess


def run_migration_script(script_path: str) -> str:
    result = subprocess.run(
        ["python", script_path],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
