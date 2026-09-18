from datetime import UTC, datetime

import pytest

from bsap.lifecycle import EventLog
from bsap.models import Budget, PermissionSet
from bsap.sandbox import (
    BudgetCounter,
    BudgetExceeded,
    ContextAccessDenied,
    InMemoryWorkspace,
    PermissionDenied,
    ToolDispatcher,
)


def fixed_clock() -> datetime:
    return datetime(2026, 9, 17, 21, 5, tzinfo=UTC)


def build_tools(*, max_tool_calls: int = 5, max_steps: int = 10) -> tuple[ToolDispatcher, EventLog]:
    log = EventLog("BSA-1", clock=fixed_clock)
    workspace = InMemoryWorkspace(
        files={"allowed.py": "needle = 1", "secret.py": "needle = 2"},
        allowed_files=("allowed.py",),
        test_results={"unit": {"exit_code": 1, "stdout": "failed"}},
    )
    dispatcher = ToolDispatcher(
        workspace=workspace,
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget_counter=BudgetCounter(Budget(max_steps=max_steps, max_tool_calls=max_tool_calls)),
        emit=log.emit,
    )
    return dispatcher, log


def test_read_is_limited_to_explicit_context() -> None:
    tools, _ = build_tools()
    assert tools.call("repository.read", {"path": "allowed.py"})["content"] == "needle = 1"
    with pytest.raises(ContextAccessDenied):
        tools.call("repository.read", {"path": "secret.py"})


def test_search_never_returns_excluded_files() -> None:
    tools, _ = build_tools()
    result = tools.call("repository.search", {"query": "needle"})
    assert result["matches"] == ({"path": "allowed.py", "line": 1, "text": "needle = 1"},)


@pytest.mark.parametrize("tool", ["filesystem.write", "network.request", "subagent.spawn"])
def test_denied_capabilities_fail_closed(tool: str) -> None:
    tools, log = build_tools()
    with pytest.raises(PermissionDenied):
        tools.call(tool, {})
    assert log.events[-1].kind == "permission.denied"


def test_tool_budget_blocks_call_before_tool_started() -> None:
    tools, log = build_tools(max_tool_calls=2)
    tools.call("repository.read", {"path": "allowed.py"})
    tools.call("tests.run", {"name": "unit"})
    with pytest.raises(BudgetExceeded):
        tools.call("repository.read", {"path": "allowed.py"})
    kinds = tuple(event.kind for event in log.events)
    assert kinds.count("tool.started") == 2
    assert kinds[-1] == "budget.exhausted"


def test_step_budget_is_enforced_before_consuming_excess_step() -> None:
    counter = BudgetCounter(Budget(max_steps=1, max_tool_calls=10))
    counter.consume_step()
    with pytest.raises(BudgetExceeded):
        counter.consume_step()
