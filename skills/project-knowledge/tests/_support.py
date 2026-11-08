from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
PROJECT_KNOWLEDGE = SKILL / "scripts/knowledge.py"


def run_command(*args: object, cwd: Path | None = None, expect: int = 0) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if process.returncode != expect:
        raise AssertionError(
            f"command exited {process.returncode}, expected {expect}: {' '.join(map(str, args))}\n{process.stderr}"
        )
    return process


def run_json(*args: object, cwd: Path | None = None) -> dict:
    return json.loads(run_command(*args, cwd=cwd).stdout)
