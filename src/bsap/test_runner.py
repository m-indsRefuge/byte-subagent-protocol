from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class TestRunTimeout(RuntimeError):
    __test__ = False


@dataclass(frozen=True, slots=True)
class ApprovedTest:
    name: str
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: float = 30.0
    max_output_chars: int = 4000


class AllowlistedTestRunner:
    def __init__(self, *, tests: tuple[ApprovedTest, ...]) -> None:
        registry: dict[str, ApprovedTest] = {}
        for test in tests:
            if test.name in registry:
                raise ValueError(f"Duplicate approved test identifier: {test.name}")
            if not test.command:
                raise ValueError(f"Approved test command is empty: {test.name}")
            if test.timeout_seconds <= 0:
                raise ValueError(f"Approved test timeout must be positive: {test.name}")
            if test.max_output_chars < len("...[truncated]"):
                raise ValueError(f"Approved test max_output_chars is too small: {test.name}")
            registry[test.name] = test
        self._tests = registry

    def is_allowed(self, name: str) -> bool:
        return name in self._tests

    @staticmethod
    def _bound(text: str, maximum: int) -> str:
        marker = "...[truncated]"
        if len(text) <= maximum:
            return text
        return text[: maximum - len(marker)] + marker

    def run(self, name: str) -> Mapping[str, object]:
        try:
            spec = self._tests[name]
        except KeyError as exc:
            raise KeyError(f"Test is not allowlisted: {name}") from exc

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        try:
            completed = subprocess.run(
                spec.command,
                cwd=spec.cwd,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
                timeout=spec.timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise TestRunTimeout(f"Approved test timed out: {name}") from exc

        return {
            "name": name,
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": self._bound(completed.stdout, spec.max_output_chars),
            "stderr": self._bound(completed.stderr, spec.max_output_chars),
            "timed_out": False,
        }
