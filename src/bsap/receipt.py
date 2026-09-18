from __future__ import annotations

from datetime import datetime

from bsap.canonical import sha256_hex
from bsap.models import BsapReport, Event, ExecutorInfo, PreparedRequest, Receipt, TerminalOutcome


def build_receipt(
    *,
    prepared: PreparedRequest,
    terminal_outcome: TerminalOutcome,
    events: tuple[Event, ...],
    report: BsapReport | None,
    executor_info: ExecutorInfo,
    created_at: datetime,
    started_at: datetime | None,
    finished_at: datetime,
) -> Receipt:
    return Receipt(
        protocol=prepared.protocol,
        version=prepared.version,
        agent_id=prepared.agent_id,
        parent_id=prepared.parent_id,
        request_sha256=prepared.request_sha256,
        context_manifest_sha256=prepared.context_manifest_sha256,
        policy_sha256=prepared.policy_sha256,
        executor=executor_info,
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
        terminal_state=terminal_outcome,
        event_count=len(events),
        report_sha256=None if report is None else sha256_hex(report),
    )
