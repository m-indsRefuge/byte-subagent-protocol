from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import PurePosixPath

from bsap.models import Budget, Event, PermissionSet
from bsap.test_runner import AllowlistedTestRunner, TestRunTimeout


class SandboxError(RuntimeError):
    pass


class ContextAccessDenied(SandboxError):
    pass


class PermissionDenied(SandboxError):
    pass


class BudgetExceeded(SandboxError):
    pass


class ToolTimeout(SandboxError):
    pass


class OutcomeUnknownError(SandboxError):
    pass


class InMemoryWorkspace:
    def __init__(
        self,
        *,
        files: Mapping[str, str],
        allowed_files: tuple[str, ...],
        test_results: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self._files = {self._normalize(path): content for path, content in files.items()}
        self._allowed_files = frozenset(self._normalize(path) for path in allowed_files)
        self._test_results = {name: dict(result) for name, result in (test_results or {}).items()}

    @staticmethod
    def _normalize(path: str) -> str:
        return PurePosixPath(path).as_posix()

    def read(self, path: str) -> str:
        normalized = self._normalize(path)
        if normalized not in self._allowed_files:
            raise ContextAccessDenied(f"Path is outside frozen context: {normalized}")
        try:
            return self._files[normalized]
        except KeyError as exc:
            raise FileNotFoundError(normalized) from exc

    def search(self, query: str) -> tuple[dict[str, object], ...]:
        matches: list[dict[str, object]] = []
        for path in sorted(self._allowed_files):
            content = self._files.get(path)
            if content is None:
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                if query in line:
                    matches.append({"path": path, "line": line_number, "text": line})
        return tuple(matches)

    def is_test_allowed(self, name: str) -> bool:
        return name in self._test_results

    def run_test(self, name: str) -> Mapping[str, object]:
        try:
            return dict(self._test_results[name])
        except KeyError as exc:
            raise KeyError(f"Unknown deterministic test: {name}") from exc


class HostTestWorkspace(InMemoryWorkspace):
    def __init__(
        self,
        *,
        files: Mapping[str, str],
        allowed_files: tuple[str, ...],
        test_runner: AllowlistedTestRunner,
    ) -> None:
        super().__init__(files=files, allowed_files=allowed_files)
        self._test_runner = test_runner

    def is_test_allowed(self, name: str) -> bool:
        return self._test_runner.is_allowed(name)

    def run_test(self, name: str) -> Mapping[str, object]:
        return self._test_runner.run(name)


class BudgetCounter:
    def __init__(self, budget: Budget) -> None:
        self._budget = budget
        self._steps = 0
        self._tool_calls = 0

    @property
    def steps(self) -> int:
        return self._steps

    @property
    def tool_calls(self) -> int:
        return self._tool_calls

    def consume_step(self) -> None:
        if self._steps >= self._budget.max_steps:
            raise BudgetExceeded("BSAP step budget exhausted")
        self._steps += 1

    def consume_tool_call(self) -> None:
        if self._tool_calls >= self._budget.max_tool_calls:
            raise BudgetExceeded("BSAP tool-call budget exhausted")
        self._tool_calls += 1


class ToolDispatcher:
    def __init__(
        self,
        *,
        workspace: InMemoryWorkspace,
        permissions: PermissionSet,
        budget_counter: BudgetCounter,
        emit: Callable[[str, Mapping[str, object]], Event],
    ) -> None:
        self._workspace = workspace
        self._permissions = permissions
        self._budget = budget_counter
        self._emit = emit

    def consume_step(self) -> None:
        try:
            self._budget.consume_step()
        except BudgetExceeded:
            self._emit("budget.exhausted", {"kind": "steps"})
            raise

    def call(self, name: str, arguments: Mapping[str, object]) -> Mapping[str, object]:
        self._emit("tool.requested", {"name": name, "arguments": dict(arguments)})
        if not self._is_allowed(name):
            self._emit("permission.denied", {"name": name})
            raise PermissionDenied(f"Tool is not permitted: {name}")

        if name == "tests.run":
            test_name = str(arguments["name"])
            if not self._workspace.is_test_allowed(test_name):
                self._emit(
                    "permission.denied",
                    {"name": name, "reason": "test_not_allowlisted"},
                )
                raise PermissionDenied(f"Test is not allowlisted: {test_name}")

        try:
            self._budget.consume_tool_call()
        except BudgetExceeded:
            self._emit("budget.exhausted", {"kind": "tool_calls", "name": name})
            raise

        self._emit("tool.started", {"name": name})
        if name == "repository.read":
            result: Mapping[str, object] = {
                "path": str(arguments["path"]),
                "content": self._workspace.read(str(arguments["path"])),
            }
        elif name == "repository.search":
            result = {
                "query": str(arguments["query"]),
                "matches": self._workspace.search(str(arguments["query"])),
            }
        elif name == "tests.run":
            try:
                result = self._workspace.run_test(str(arguments["name"]))
            except TestRunTimeout as exc:
                self._emit("tool.failed", {"name": name, "reason": "timeout"})
                raise ToolTimeout("Approved test timed out") from exc
        else:
            self._emit("permission.denied", {"name": name})
            raise PermissionDenied(f"Unknown tool: {name}")
        self._emit("tool.completed", {"name": name})
        return result

    def _is_allowed(self, name: str) -> bool:
        if name in {"repository.read", "repository.search"}:
            return self._permissions.filesystem_read
        if name == "tests.run":
            return self._permissions.tests_run
        if name == "filesystem.write":
            return self._permissions.filesystem_write
        if name == "network.request":
            return self._permissions.external_network
        if name == "subagent.spawn":
            return self._permissions.spawn_subagents
        return False
