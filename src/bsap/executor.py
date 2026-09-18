from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from bsap.models import BsapReport, Event, ExecutorInfo, PreparedRequest, ToolCall
from bsap.sandbox import ToolDispatcher


class Executor(Protocol):
    @property
    def info(self) -> ExecutorInfo: ...

    def execute(
        self,
        prepared: PreparedRequest,
        tools: ToolDispatcher,
        emit: Callable[[str, Mapping[str, object]], Event],
    ) -> BsapReport: ...


class ExecutionCancelled(RuntimeError):
    pass


class ScriptedDeterministicExecutor:
    def __init__(
        self,
        *,
        actions: tuple[ToolCall, ...],
        report_builder: Callable[[tuple[Mapping[str, object], ...]], BsapReport],
    ) -> None:
        self._actions = actions
        self._report_builder = report_builder

    @property
    def info(self) -> ExecutorInfo:
        return ExecutorInfo(type="deterministic", version="0.1")

    def execute(
        self,
        prepared: PreparedRequest,
        tools: ToolDispatcher,
        emit: Callable[[str, Mapping[str, object]], Event],
    ) -> BsapReport:
        results: list[Mapping[str, object]] = []
        for action in self._actions:
            tools.consume_step()
            results.append(tools.call(action.name, action.arguments))
        emit("report.started", {})
        report = self._report_builder(tuple(results))
        if report.agent_id != prepared.agent_id:
            report = BsapReport(
                agent_id=prepared.agent_id,
                status=report.status,
                findings=report.findings,
                evidence=report.evidence,
                alternative_hypotheses=report.alternative_hypotheses,
                uncertainties=report.uncertainties,
                recommended_next_action=report.recommended_next_action,
            )
        emit("report.completed", {"finding_count": len(report.findings)})
        return report
