from bsap.demo import run_timeout_demo
from bsap.models import ParentDispositionResult, TerminalOutcome


def test_timeout_investigation_runs_end_to_end() -> None:
    result, disposition = run_timeout_demo()

    assert result.terminal_outcome is TerminalOutcome.COMPLETED
    assert result.final_state.value == "TERMINATED"
    assert result.report is not None
    assert result.report.findings[0].id == "F-001"
    assert "conversion" in result.report.findings[0].claim.lower()
    assert result.receipt.request_sha256
    assert result.receipt.context_manifest_sha256
    assert result.receipt.policy_sha256
    assert result.receipt.report_sha256
    assert disposition.result is ParentDispositionResult.ACCEPTED

    sequences = tuple(event.sequence for event in result.events)
    assert sequences == tuple(range(1, len(sequences) + 1))
    assert all(event.kind != "permission.denied" for event in result.events)


def test_importing_package_does_not_eagerly_import_demo() -> None:
    import importlib
    import sys

    sys.modules.pop("bsap.demo", None)
    sys.modules.pop("bsap", None)
    importlib.import_module("bsap")
    assert "bsap.demo" not in sys.modules
