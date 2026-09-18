import json

import pytest

from bsap.model_protocol import (
    ActionParser,
    FinalReportAction,
    ModelProtocolError,
    ToolRequestAction,
)


def valid_report_payload() -> dict[str, object]:
    return {
        "type": "final_report",
        "report": {
            "status": "completed",
            "findings": [{"id": "F-1", "claim": "conversion is missing"}],
            "evidence": [
                {
                    "finding_id": "F-1",
                    "source": "settings.py",
                    "observation": "5000 is copied directly",
                }
            ],
            "alternative_hypotheses": [
                {
                    "claim": "client converts later",
                    "disposition": "rejected",
                    "basis": "client consumes the value directly",
                }
            ],
            "uncertainties": [],
            "recommended_next_action": ["convert milliseconds at the loader boundary"],
        },
    }


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("repository.read", {"path": "settings.py"}),
        ("repository.search", {"query": "timeout"}),
        ("tests.run", {"name": "timeout-conversion"}),
    ],
)
def test_parse_valid_tool_requests(tool: str, arguments: dict[str, str]) -> None:
    action = ActionParser().parse(
        json.dumps({"type": "tool_request", "tool": tool, "arguments": arguments}),
        agent_id="BSA-2",
    )
    assert action == ToolRequestAction(tool=tool, arguments=arguments)


def test_parse_final_report_injects_frozen_agent_id() -> None:
    action = ActionParser().parse(json.dumps(valid_report_payload()), agent_id="BSA-2")
    assert isinstance(action, FinalReportAction)
    assert action.report.agent_id == "BSA-2"
    assert action.report.findings[0].id == "F-1"
    assert action.report.evidence[0].finding_id == "F-1"


def test_prose_wrapped_json_is_rejected() -> None:
    with pytest.raises(ModelProtocolError) as exc_info:
        ActionParser().parse(
            'Here is my answer: {"type":"tool_request","tool":"repository.read","arguments":{"path":"a.py"}}',
            agent_id="BSA-2",
        )
    assert exc_info.value.code == "invalid_json"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"type": "unknown"}, "unknown_type"),
        (
            {
                "type": "tool_request",
                "tool": "filesystem.write",
                "arguments": {"path": "x.py"},
            },
            "unknown_tool",
        ),
        (
            {
                "type": "tool_request",
                "tool": "repository.read",
                "arguments": {"path": "a.py", "extra": "x"},
            },
            "invalid_arguments",
        ),
        (
            {
                "type": "tool_request",
                "tool": "repository.search",
                "arguments": {"query": 1},
            },
            "invalid_arguments",
        ),
        (
            {
                "type": "tool_request",
                "tool": "tests.run",
                "arguments": {},
            },
            "invalid_arguments",
        ),
        (
            {
                "type": "tool_request",
                "tool": "repository.read",
                "arguments": {"path": "a.py"},
                "extra": True,
            },
            "invalid_envelope",
        ),
    ],
)
def test_invalid_tool_envelopes_are_rejected(payload: dict[str, object], code: str) -> None:
    with pytest.raises(ModelProtocolError) as exc_info:
        ActionParser().parse(json.dumps(payload), agent_id="BSA-2")
    assert exc_info.value.code == code


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["report"].update({"unexpected": "x"}),
        lambda payload: payload["report"]["findings"].append({"id": "F-2"}),
        lambda payload: payload["report"]["evidence"].append({"finding_id": "F-1", "source": 3, "observation": "x"}),
        lambda payload: payload["report"]["alternative_hypotheses"].append(
            {"claim": "x", "disposition": "rejected"}
        ),
        lambda payload: payload["report"].update({"uncertainties": [1]}),
        lambda payload: payload["report"].update({"recommended_next_action": "fix"}),
    ],
)
def test_malformed_report_shapes_are_rejected(mutator) -> None:
    payload = valid_report_payload()
    mutator(payload)
    with pytest.raises(ModelProtocolError):
        ActionParser().parse(json.dumps(payload), agent_id="BSA-2")


def test_top_level_json_must_be_object() -> None:
    with pytest.raises(ModelProtocolError) as exc_info:
        ActionParser().parse("[]", agent_id="BSA-2")
    assert exc_info.value.code == "invalid_envelope"
