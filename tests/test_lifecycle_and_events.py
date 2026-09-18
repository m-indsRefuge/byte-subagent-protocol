from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from bsap.lifecycle import EventLog, InvalidTransitionError, Lifecycle
from bsap.models import LifecycleState, TerminalOutcome


def fixed_clock() -> datetime:
    return datetime(2026, 9, 17, 21, 0, tzinfo=UTC)


def test_happy_path_preserves_terminal_outcome_after_termination() -> None:
    lifecycle = Lifecycle()
    for state in (
        LifecycleState.PREPARED,
        LifecycleState.RUNNING,
        LifecycleState.REPORTING,
        LifecycleState.COMPLETED,
        LifecycleState.TERMINATED,
    ):
        lifecycle.transition(state)
    assert lifecycle.state is LifecycleState.TERMINATED
    assert lifecycle.terminal_outcome is TerminalOutcome.COMPLETED


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (LifecycleState.REQUESTED, LifecycleState.COMPLETED),
        (LifecycleState.FAILED, LifecycleState.RUNNING),
        (LifecycleState.TERMINATED, LifecycleState.RUNNING),
    ],
)
def test_illegal_transitions_are_rejected(start: LifecycleState, target: LifecycleState) -> None:
    lifecycle = Lifecycle(initial=start)
    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(target)


def test_event_log_sequences_are_contiguous_and_events_are_immutable() -> None:
    log = EventLog("BSA-1", clock=fixed_clock)
    first = log.emit("agent.created", {"role": "investigator"})
    second = log.emit("agent.started", {})
    third = log.emit("finding.recorded", {"id": "F-1"})
    assert tuple(event.sequence for event in log.events) == (1, 2, 3)
    assert (first, second, third) == log.events
    with pytest.raises(FrozenInstanceError):
        first.kind = "rewritten"  # type: ignore[misc]
