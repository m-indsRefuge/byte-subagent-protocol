from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from types import MappingProxyType

from bsap.models import Event, LifecycleState, TerminalOutcome


class InvalidTransitionError(ValueError):
    pass


class EventStoreFailure(RuntimeError):
    pass


_ALLOWED: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.REQUESTED: frozenset({LifecycleState.PREPARED, LifecycleState.CANCELLED}),
    LifecycleState.PREPARED: frozenset({LifecycleState.RUNNING, LifecycleState.CANCELLED}),
    LifecycleState.RUNNING: frozenset(
        {
            LifecycleState.REPORTING,
            LifecycleState.FAILED,
            LifecycleState.CANCELLED,
            LifecycleState.OUTCOME_UNKNOWN,
        }
    ),
    LifecycleState.REPORTING: frozenset(
        {
            LifecycleState.COMPLETED,
            LifecycleState.FAILED,
            LifecycleState.CANCELLED,
            LifecycleState.OUTCOME_UNKNOWN,
        }
    ),
    LifecycleState.COMPLETED: frozenset({LifecycleState.TERMINATED}),
    LifecycleState.FAILED: frozenset({LifecycleState.TERMINATED}),
    LifecycleState.CANCELLED: frozenset({LifecycleState.TERMINATED}),
    LifecycleState.OUTCOME_UNKNOWN: frozenset({LifecycleState.TERMINATED}),
    LifecycleState.TERMINATED: frozenset(),
}

_OUTCOME_FOR_STATE = {
    LifecycleState.COMPLETED: TerminalOutcome.COMPLETED,
    LifecycleState.FAILED: TerminalOutcome.FAILED,
    LifecycleState.CANCELLED: TerminalOutcome.CANCELLED,
    LifecycleState.OUTCOME_UNKNOWN: TerminalOutcome.OUTCOME_UNKNOWN,
}


class Lifecycle:
    def __init__(self, initial: LifecycleState = LifecycleState.REQUESTED) -> None:
        self._state = initial
        self._terminal_outcome = _OUTCOME_FOR_STATE.get(initial)

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def terminal_outcome(self) -> TerminalOutcome | None:
        return self._terminal_outcome

    def transition(self, target: LifecycleState) -> None:
        if target not in _ALLOWED[self._state]:
            raise InvalidTransitionError(f"Illegal BSAP transition: {self._state} -> {target}")
        self._state = target
        if target in _OUTCOME_FOR_STATE:
            self._terminal_outcome = _OUTCOME_FOR_STATE[target]


class EventLog:
    def __init__(
        self,
        agent_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events: list[Event] = []

    def emit(self, kind: str, payload: Mapping[str, object]) -> Event:
        event = Event(
            agent_id=self._agent_id,
            sequence=len(self._events) + 1,
            timestamp=self._clock(),
            kind=kind,
            payload=MappingProxyType(dict(payload)),
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)
