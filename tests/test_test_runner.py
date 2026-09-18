import subprocess
import sys
from pathlib import Path

import pytest

from bsap.sandbox import HostTestWorkspace
from bsap.test_runner import (
    AllowlistedTestRunner,
    ApprovedTest,
    TestRunTimeout,
)


def approved(
    tmp_path: Path,
    *,
    name: str = "unit",
    code: str = "print('PASS-MARKER')",
    timeout_seconds: float = 30.0,
    max_output_chars: int = 4000,
) -> ApprovedTest:
    return ApprovedTest(
        name=name,
        command=(sys.executable, "-c", code),
        cwd=tmp_path,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
    )


def test_approved_test_runs_without_shell(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(tests=(approved(tmp_path),))
    result = runner.run("unit")
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "PASS-MARKER"
    assert result["stderr"] == ""
    assert result["timed_out"] is False


def test_failing_approved_test_returns_nonzero_result(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(
        tests=(approved(tmp_path, code="import sys; print('FAIL'); sys.exit(7)"),)
    )
    result = runner.run("unit")
    assert result["passed"] is False
    assert result["exit_code"] == 7
    assert "FAIL" in result["stdout"]


def test_output_is_bounded_with_visible_truncation_marker(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(
        tests=(
            approved(
                tmp_path,
                code="print('x' * 200)",
                max_output_chars=40,
            ),
        )
    )
    result = runner.run("unit")
    assert len(result["stdout"]) <= 40
    assert result["stdout"].endswith("...[truncated]")


def test_unknown_identifier_is_denied_before_subprocess(tmp_path: Path, monkeypatch) -> None:
    called = False

    def forbidden_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not start")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    runner = AllowlistedTestRunner(tests=())
    with pytest.raises(KeyError):
        runner.run("invented-command")
    assert called is False


def test_timeout_is_classified_without_returning_partial_process_state(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(
        tests=(
            approved(
                tmp_path,
                code="import time; time.sleep(1)",
                timeout_seconds=0.05,
            ),
        )
    )
    with pytest.raises(TestRunTimeout, match="unit"):
        runner.run("unit")


def test_subprocess_is_invoked_with_shell_false(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = AllowlistedTestRunner(tests=(approved(tmp_path),))
    runner.run("unit")
    assert captured["shell"] is False
    assert captured["cwd"] == tmp_path


def test_host_workspace_preserves_frozen_reads_and_runs_allowlisted_test(tmp_path: Path) -> None:
    runner = AllowlistedTestRunner(tests=(approved(tmp_path),))
    workspace = HostTestWorkspace(
        files={"allowed.py": "x = 1", "secret.py": "secret = 1"},
        allowed_files=("allowed.py",),
        test_runner=runner,
    )
    assert workspace.read("allowed.py") == "x = 1"
    assert workspace.run_test("unit")["passed"] is True
    with pytest.raises(Exception) as exc_info:
        workspace.read("secret.py")
    assert type(exc_info.value).__name__ == "ContextAccessDenied"
