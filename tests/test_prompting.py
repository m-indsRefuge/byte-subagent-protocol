from bsap.model_transport import ModelMessage
from bsap.models import (
    Budget,
    CompletionContract,
    ContextManifest,
    DelegationReason,
    PermissionSet,
    PreparedRequest,
)
from bsap.prompting import PromptBuilder


def prepared() -> PreparedRequest:
    return PreparedRequest(
        agent_id="BSA-PROMPT",
        parent_id="BYTE",
        role="investigator",
        objective="diagnose timeout conversion",
        delegation_reason=DelegationReason(
            trigger="verification",
            rationale="independent evidence",
            expected_value="root cause",
        ),
        context_manifest=ContextManifest(
            files=("settings.py", "client.py"),
            observations=("timeout=5000",),
            constraints=("read-only",),
            parent_summary=("external ms; internal seconds",),
            excluded=("conversation history", "personal memory"),
        ),
        permissions=PermissionSet(filesystem_read=True, tests_run=True),
        budget=Budget(max_steps=6, max_tool_calls=4),
        completion_contract=CompletionContract(
            require=(
                "findings",
                "evidence",
                "alternative_hypotheses",
                "uncertainties",
                "recommended_next_action",
            )
        ),
        request_sha256="a" * 64,
        context_manifest_sha256="b" * 64,
        policy_sha256="c" * 64,
    )


def test_prompt_construction_is_deterministic() -> None:
    builder = PromptBuilder()
    first = (builder.system_prompt(prepared()), builder.initial_messages(prepared()))
    second = (builder.system_prompt(prepared()), builder.initial_messages(prepared()))
    assert first == second


def test_system_prompt_defines_only_governed_tools_and_denies_forbidden_capabilities() -> None:
    prompt = PromptBuilder().system_prompt(prepared())
    assert "repository.read" in prompt
    assert "repository.search" in prompt
    assert "tests.run" in prompt
    assert "filesystem.write" not in prompt
    assert "network.request" not in prompt
    assert "subagent.spawn" not in prompt
    assert "cannot write files" in prompt
    assert "cannot access the network" in prompt
    assert "cannot spawn agents" in prompt
    assert "exactly one JSON object" in prompt
    assert "hidden reasoning" in prompt


def test_initial_message_contains_only_frozen_assignment_material() -> None:
    messages = PromptBuilder().initial_messages(prepared())
    assert len(messages) == 1
    assert messages[0].role == "user"
    content = messages[0].content
    assert '"objective":"diagnose timeout conversion"' in content
    assert '"files":["settings.py","client.py"]' in content
    assert '"max_steps":6' in content
    assert '"max_tool_calls":4' in content
    assert '"conversation history"' in content
    assert "OPENAI_API_KEY" not in content
    assert "full_chat_history" not in content


def test_tool_result_message_is_deterministic_json() -> None:
    message = PromptBuilder().tool_result_message(
        "repository.read",
        {"path": "settings.py"},
        {"path": "settings.py", "content": "timeout_ms"},
    )
    assert message == ModelMessage(
        role="user",
        content=(
            '{"arguments":{"path":"settings.py"},'
            '"result":{"content":"timeout_ms","path":"settings.py"},'
            '"tool":"repository.read","type":"tool_result"}'
        ),
    )
