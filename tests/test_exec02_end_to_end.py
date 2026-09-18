import json

import pytest

from bsap.live_canary import (
    disposition_from_json,
    run_live_canary,
)
from bsap.model_transport import ModelResponse
from bsap.models import (
    ParentDispositionResult,
    TerminalOutcome,
)


class FakeModelTransport:
    def __init__(self, responses: tuple[str, ...]) -> None:
        self._responses = iter(responses)
        self.requests = []

    @property
    def transport_name(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return "fixture-model"

    def send(self, request):
        self.requests.append(request)
        return ModelResponse(next(self._responses))


def final_report() -> str:
    return json.dumps(
        {
            "type": "final_report",
            "report": {
                "status": "completed",
                "findings": [
                    {
                        "id": "F-1",
                        "claim": (
                            "The loader copies milliseconds directly into "
                            "request_timeout_seconds without conversion."
                        ),
                    }
                ],
                "evidence": [
                    {
                        "finding_id": "F-1",
                        "source": "settings.py",
                        "observation": (
                            "request_timeout_ms is parsed with int() and assigned "
                            "directly to request_timeout_seconds."
                        ),
                    },
                    {
                        "finding_id": "F-1",
                        "source": "timeout-conversion",
                        "observation": "The approved test reports expected 5 but got 5000.",
                    },
                ],
                "alternative_hypotheses": [
                    {
                        "claim": "The client converts milliseconds later.",
                        "disposition": "rejected",
                        "basis": "client.py passes request_timeout_seconds directly.",
                    }
                ],
                "uncertainties": [],
                "recommended_next_action": [
                    "Convert milliseconds to seconds in load_http_settings."
                ],
            },
        },
        separators=(",", ":"),
    )


def test_exec02_runs_search_read_real_test_and_report_end_to_end() -> None:
    transport = FakeModelTransport(
        (
            '{"type":"tool_request","tool":"repository.search","arguments":{"query":"request_timeout"}}',
            '{"type":"tool_request","tool":"repository.read","arguments":{"path":"settings.py"}}',
            '{"type":"tool_request","tool":"tests.run","arguments":{"name":"timeout-conversion"}}',
            final_report(),
        )
    )

    manager, result = run_live_canary(transport)

    assert result.terminal_outcome is TerminalOutcome.COMPLETED
    assert result.final_state.value == "TERMINATED"
    assert result.report is not None
    assert result.report.findings[0].id == "F-1"
    assert result.receipt.executor.type == "model"
    assert result.receipt.executor.transport == "fake"
    assert result.receipt.executor.model == "fixture-model"
    assert manager.get_parent_disposition(result.agent_id) is None
    assert len(transport.requests) == 4

    tool_names = tuple(
        event.payload["name"]
        for event in result.events
        if event.kind == "tool.requested"
    )
    assert tool_names == ("repository.search", "repository.read", "tests.run")
    assert all(event.kind != "permission.denied" for event in result.events)
    sequences = tuple(event.sequence for event in result.events)
    assert sequences == tuple(range(1, len(sequences) + 1))

    test_result_message = transport.requests[3].messages[-1].content
    assert '"name":"timeout-conversion"' in test_result_message
    assert '"passed":false' in test_result_message
    assert "expected timeout=5 seconds, got 5000" in test_result_message

    disposition = disposition_from_json(
        manager,
        result,
        json.dumps(
            {
                "result": "accepted",
                "accepted_findings": ["F-1"],
                "rejected_findings": [],
                "rationale": "The frozen source and approved test support the finding.",
            }
        ),
    )
    assert disposition.result is ParentDispositionResult.ACCEPTED
    assert manager.get_parent_disposition(result.agent_id) == disposition
    assert result.terminal_outcome is TerminalOutcome.COMPLETED


def test_parent_disposition_rejects_unknown_finding_ids() -> None:
    transport = FakeModelTransport((final_report(),))
    manager, result = run_live_canary(transport)
    with pytest.raises(ValueError, match="unknown finding"):
        disposition_from_json(
            manager,
            result,
            json.dumps(
                {
                    "result": "accepted",
                    "accepted_findings": ["F-404"],
                    "rejected_findings": [],
                    "rationale": "invalid",
                }
            ),
        )


def test_parent_disposition_requires_completed_report() -> None:
    transport = FakeModelTransport(("not-json",))
    manager, result = run_live_canary(transport)
    assert result.terminal_outcome is TerminalOutcome.FAILED
    with pytest.raises(ValueError, match="completed report"):
        disposition_from_json(
            manager,
            result,
            '{"result":"rejected","accepted_findings":[],"rejected_findings":[],"rationale":"x"}',
        )
